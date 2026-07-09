from __future__ import annotations

import json
from pathlib import Path

from .models import TraceRecord


class JsonlTraceStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, trace: TraceRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(trace.to_dict(), ensure_ascii=False) + "\n")
