# Copyright 2026 Ronny Trommer <ronny@no42.org>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Read and write build/handover/state.json, one object per chunk id."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class ChunkState:
    rebase: str                       # ok | conflict | parent-behind | unchanged
    candidate: str | None
    base: str | None
    tests: str                        # pass | fail | none | pending
    promoted: bool = False
    verified_at: dict | None = None   # {"upstream": sha, "date": "YYYY-MM-DD"}
    last_good: dict | None = None
    landed: bool = False
    published: str | None = None      # origin/<branch> sha seen at rebuild


def load(path: Path) -> dict[str, ChunkState]:
    data = json.loads(Path(path).read_text())
    return {cid: ChunkState(**fields) for cid, fields in data.items()}


def save(path: Path, states: dict[str, ChunkState]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {cid: asdict(s) for cid, s in states.items()}
    path.write_text(json.dumps(data, indent=2) + "\n")
