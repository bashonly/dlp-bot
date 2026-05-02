from __future__ import annotations

import pathlib

from bot.deps.common import DependenciesUpdateResult
from bot.deps.python import (
    PythonDependenciesUpdater,
    get_extras,
    get_groups,
)

REQS_OUTPUT_TMPL = '{}.txt'


class DLPBotDependenciesUpdater(PythonDependenciesUpdater):
    def __init__(self, /, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._requirements_path = self.project_path / 'requirements'

    def _post_upgrade(
        self,
        _,
        /,
        *,
        updated_paths: set[pathlib.Path],
        all_updates: DependenciesUpdateResult,
        env: dict[str, str] | None,
        upgrade_arg: str,
        upgrade_only: str | None,
        verify: bool,
    ):
        pyproject_toml = self.load_pyproject_toml()

        for extra in get_extras(pyproject_toml, resolve=False):
            requirements_txt_path = self._requirements_path / REQS_OUTPUT_TMPL.format(extra)
            self.uv_export(
                extras=[extra],
                output_file=requirements_txt_path,
            )
            updated_paths.add(requirements_txt_path)

        for group in get_groups(pyproject_toml, resolve=False):
            requirements_txt_path = self._requirements_path / REQS_OUTPUT_TMPL.format(group)
            self.uv_export(
                groups=[group],
                output_file=requirements_txt_path,
            )
            updated_paths.add(requirements_txt_path)
