from __future__ import annotations

import collections.abc
import contextlib
import datetime as dt
import json
import re
import string
import sys
import typing
import urllib.error
import urllib.parse
import urllib.request

SHA1_PATTERN = r'[0-9a-f]{40}'
SHA1_RE = re.compile(SHA1_PATTERN)


def is_sha1(commitish: str) -> bool:
    return bool(SHA1_RE.fullmatch(commitish))


class BotError(Exception):
    pass


class VerificationError(BotError):
    pass


class SuccessMessage(BaseException):
    pass


def request(
    url: str,
    *,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    method: str | None = None,
    timeout: int = 60,
):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    return contextlib.closing(urllib.request.urlopen(req, timeout=timeout))


def filter_dict(
    dct: dict[typing.Any, typing.Any],
    /,
    cndn: collections.abc.Callable = lambda _, v: v is not None,
):
    return {k: v for k, v in dct.items() if cndn(k, v)}


class BaseAPICaller:
    def __init__(
        self,
        /,
        base_url: str,
        *,
        retries: int = 3,
        timeout: int = 5,
        verbose: bool = False,
        user_agent: str = 'dlp-bot',
        note_prefix: str = 'bot',
        custom_exception: type[Exception] = BotError,
    ):
        self.base_url = base_url
        self.retries = retries
        self.timeout = timeout
        self.verbose = verbose
        self.user_agent = user_agent
        self._note = note_prefix
        self._exc = custom_exception

    @property
    def headers(self) -> dict[str, str]:
        return {
            'Accept': 'application/json',
            'User-Agent': self.user_agent,
        }

    def _fetch_json(
        self,
        /,
        url_or_path: str,
        *,
        query: dict[str, str | None] | None = None,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        method: str | None = None,
        status_check: list[int] | None = None,
    ):
        url = urllib.parse.urlparse(urllib.parse.urljoin(self.base_url, url_or_path))
        assert url.geturl().startswith(self.base_url), 'Invalid base_url and path combination'
        assert method in {None, 'DELETE', 'GET', 'PATCH', 'POST', 'PUT'}, f'Invalid HTTP method "{method}"'

        qs = urllib.parse.urlencode(
            {
                **urllib.parse.parse_qs(url.query),
                **filter_dict(query or {}),
            },
            doseq=True,
            quote_via=urllib.parse.quote,
        )

        full_url = urllib.parse.urlunparse(url._replace(query=qs))

        for attempt in range(self.retries + 1):
            if self.verbose:
                print(f'[{self._note}] {method or "GET"} {url.path}{"?" if qs else ""}{qs or ""}', file=sys.stderr)
            try:
                with request(full_url, data=data, headers=headers, method=method, timeout=self.timeout) as resp:
                    return json.load(resp)
            except json.JSONDecodeError as error:
                if status_check:
                    return True
                raise self._exc(f'[{type(error).__name__}] {error}')
            except urllib.error.HTTPError as error:
                if status_check and error.code in status_check:
                    return False
                raise self._exc(f'[{type(error).__name__}] {error}')
            except TimeoutError as error:
                if attempt < self.retries:
                    print(
                        f'[{self._note}] operation timed out, retrying ({attempt + 1} of {self.retries})',
                        file=sys.stderr,
                    )
                    continue
                raise self._exc(f'[{type(error).__name__}] {error}')


def remove_around(data: str, before: str, after: str) -> str:
    return data.removeprefix(before).removesuffix(after)


def parse_owner_and_repo(value: str) -> tuple[str, str]:
    owner, _, rest = value.partition('/')
    # partition again to handle values like 'github/codeql-action/init'
    return owner, rest.partition('/')[0]


UNIX_TIMESTAMP_RE = re.compile(r'[0-9]{10}(?:\.[0-9]+)?')

ISO8601_DURATION_RE = re.compile(r"""(?x)
    P(?:(?P<days>\d+\.\d+|\d*)D)?
    T?
        (?:(?P<hours>\d+\.\d+|\d*)H)?
        (?:(?P<minutes>\d+\.\d+|\d*)M)?
        (?:(?P<seconds>\d+\.\d+|\d*)S)?
    """)

NATURAL_LANGUAGE_RE = re.compile(r"""(?x)
    (?:(?P<weeks>\d+)\s*weeks?(?:,\s+)?)?
    (?:(?P<days>\d+)\s*days?(?:,\s+)?)?
    (?:(?P<hours>\d+)\s*hours?(?:,\s+)?)?
    (?:(?P<minutes>\d+)\s*minutes?(?:,\s+)?)?
    (?:(?P<seconds>\d+)\s*seconds?)?
    """)


def parse_datetime_from_cooldown(cooldown: str | None) -> dt.datetime:
    if not cooldown:
        return dt.datetime.now(tz=dt.UTC)

    if UNIX_TIMESTAMP_RE.fullmatch(cooldown):
        with contextlib.suppress(OSError, OverflowError, ValueError):
            return dt.datetime.fromtimestamp(float(cooldown), tz=dt.UTC)

    with contextlib.suppress(OSError, OverflowError, ValueError):
        return dt.datetime.fromisoformat(cooldown)

    mobj = ISO8601_DURATION_RE.fullmatch(cooldown) or NATURAL_LANGUAGE_RE.fullmatch(cooldown)
    if not mobj:
        raise ValueError(f'Unable to parse duration: {cooldown}')

    parts = {k: float(v) for k, v in mobj.groupdict(default='0').items()}
    if weeks := parts.pop('weeks', 0):
        days = parts.pop('days', 0)
        parts['days'] = (weeks * 7) + days

    return dt.datetime.now(tz=dt.UTC) - dt.timedelta(**parts)


def table_a_raza(header: tuple[str, ...], rows: list[tuple[str, ...]]) -> collections.abc.Generator[str]:
    widths = [len(col) for col in header]

    for row in rows:
        for index, (width, col) in enumerate(zip(widths, row, strict=True)):
            if len(col) > width:
                widths[index] = len(col)

    yield ' | '.join(col.ljust(width) for width, col in zip(widths, header, strict=True))
    yield '-|-'.join(''.ljust(width, '-') for width in widths)
    for row in rows:
        yield ' | '.join(col.ljust(width) for width, col in zip(widths, row, strict=True))


class SafeFormatDict(dict):
    def __missing__(self, key):
        return f'{{{key}}}'


class SafeFormatAutomaticTuple(tuple):
    def __getitem__(self, subscript):
        try:
            return super().__getitem__(subscript)
        except IndexError:
            return '{}'


class SafeFormatManualTuple(tuple):
    def __getitem__(self, subscript):
        try:
            return super().__getitem__(subscript)
        except IndexError:
            return f'{{{subscript}}}'


def safe_format(s: str | None, /, *args, **kwargs) -> str | None:
    if not isinstance(s, str):
        return None

    formatter = string.Formatter()

    safe_args: tuple
    if '{}' in s and any(tup[1] == '' for tup in formatter.parse(s)):
        safe_args = SafeFormatAutomaticTuple(args)
    else:
        safe_args = SafeFormatManualTuple(args)

    try:
        return formatter.vformat(s, safe_args, SafeFormatDict(kwargs))
    except (TypeError, ValueError):
        return s
