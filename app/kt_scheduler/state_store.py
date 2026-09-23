from __future__ import annotations

import json
from pathlib import Path


class InviteStateStore:
    """Small file-backed state store used to avoid duplicate invitations."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> set[str]:
        if not self.path.exists():
            return set()
        with self.path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, list):
            raise ValueError(f"Invalid scheduler state file format: {self.path}")
        return {str(item) for item in data}

    def add(self, uid: str) -> None:
        sent = self.load()
        sent.add(uid)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(sorted(sent), handle, indent=2)

