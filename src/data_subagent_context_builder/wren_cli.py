from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CommandResult:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def to_dict(self) -> dict[str, object]:
        return {
            "args": self.args,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


class WrenCliRunner:
    def __init__(
        self,
        *,
        wren_bin: Path,
        project_dir: Path,
        wren_home: Path,
        timeout_seconds: int = 60,
    ) -> None:
        self.wren_bin = wren_bin
        self.project_dir = project_dir
        self.wren_home = wren_home
        self.timeout_seconds = timeout_seconds

    def run(self, args: list[str]) -> CommandResult:
        env = os.environ.copy()
        env["WREN_HOME"] = str(self.wren_home)
        env["PYTHONIOENCODING"] = "utf-8"
        completed = subprocess.run(
            [str(self.wren_bin), *args],
            cwd=str(self.project_dir),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=self.timeout_seconds,
            check=False,
        )
        return CommandResult(
            args=args,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
