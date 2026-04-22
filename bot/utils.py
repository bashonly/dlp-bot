from __future__ import annotations

import collections.abc
import contextlib
import datetime as dt
import re
import string
import typing
import urllib.request

SHA_PATTERN = r'[0-9a-f]{40}'
SHA_RE = re.compile(SHA_PATTERN)


def is_sha(commitish: str) -> bool:
    return bool(SHA_RE.fullmatch(commitish))


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


def remove_around(data: str, before: str, after: str) -> str:
    return data.removeprefix(before).removesuffix(after)


def parse_owner_and_repo(value: str) -> tuple[str, str]:
    owner, _, rest = value.partition('/')
    # partition again to handle values like 'github/codeql-action/init'
    return owner, rest.partition('/')[0]


def parse_datetime_from_cooldown(cooldown: str) -> dt.datetime:
    UNIX_TIMESTAMP_RE = re.compile(r'[0-9]{10}(?:\.[0-9]+)?')

    if UNIX_TIMESTAMP_RE.fullmatch(cooldown):
        with contextlib.suppress(OSError, OverflowError, ValueError):
            return dt.datetime.fromtimestamp(float(cooldown), tz=dt.UTC)

    with contextlib.suppress(OSError, OverflowError, ValueError):
        return dt.datetime.fromisoformat(cooldown)

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
