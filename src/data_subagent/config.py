from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SubagentConfig:
    project_root: Path
    wren_project_dir: Path
    wren_home: Path
    wren_bin: Path
    trace_path: Path
    deepseek_api_key_file: Path
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_base_url: str = "https://api.deepseek.com"
    max_repair_attempts: int = 2
    query_limit: int = 100
    wren_timeout_seconds: int = 60
    llm_timeout_seconds: int = 90

    @classmethod
    def default(cls, project_root: Path | None = None) -> "SubagentConfig":
        root = (project_root or Path.cwd()).resolve()
        return cls(
            project_root=root,
            wren_project_dir=root / "data" / "wren" / "jaffle_wren_project",
            wren_home=root / "data" / "wren" / "home",
            wren_bin=root / ".venv-wren" / "Scripts" / "wren.exe",
            trace_path=root / "data" / "traces" / "data_subagent.jsonl",
            deepseek_api_key_file=root / "deepseek_apikey.txt",
        )

    def read_deepseek_api_key(self) -> str:
        env_key = os.environ.get("DEEPSEEK_API_KEY")
        if env_key:
            return env_key.strip()
        if self.deepseek_api_key_file.exists():
            return self.deepseek_api_key_file.read_text(encoding="utf-8").strip()
        raise RuntimeError(
            "DeepSeek API key not found. Set DEEPSEEK_API_KEY or create "
            f"{self.deepseek_api_key_file}"
        )
