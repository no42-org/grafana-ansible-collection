# Copyright 2026 Ronny Trommer <ronny@no42.org>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Rebase every published review branch onto its new base, parents first.

Each chunk's `origin/review/<...>` is copied to a local
`handover-candidate/<...>` and rebased. A root chunk moves from its
merge-base with upstream to the upstream tip. A child moves from its
parent's published branch to its parent's candidate, so it stacks on what
the parent became. A child of a chunk that failed does not move at all.

Nothing is pushed or fetched here. The work tree must be clean because the
rebase switches branches; the branch that was checked out is restored.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import manifest
from state import ChunkState

FAILED = ("conflict", "parent-behind")


class RebuildError(Exception):
    pass


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    # update-refs would move any local branch inside the rebased range.
    cmd = ["git", "-c", "rebase.updateRefs=false", *args]
    done = subprocess.run(cmd, cwd=repo, capture_output=True, text=True,
                          env={**os.environ, "GIT_EDITOR": "true"})
    if check and done.returncode != 0:
        raise RebuildError(f"git {' '.join(args)}: {done.stderr.strip()}")
    return done


def _rev(repo: Path, ref: str) -> str | None:
    done = _git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", check=False)
    return done.stdout.strip() if done.returncode == 0 else None


def _rebase_one(chunk: manifest.Chunk, parent: ChunkState | None, repo: Path,
                upstream: str, origin: str, by_id: dict) -> tuple[ChunkState, str]:
    published = f"{origin}/{chunk.branch}"
    parent_branch = f"{origin}/{by_id[chunk.requires].branch}" if chunk.requires else None
    if parent is not None and parent.rebase in FAILED:
        old = _rev(repo, parent_branch)
        return ChunkState("parent-behind", None, old, "none"), f"parent {chunk.requires} failed"
    new = parent.candidate if parent is not None else upstream
    if _rev(repo, published) is None:
        return ChunkState("conflict", None, new, "none"), f"no origin branch {published}"
    if parent_branch is None:
        old = _git(repo, "merge-base", upstream, published).stdout.strip()
    else:
        old = _rev(repo, parent_branch)
    _git(repo, "branch", "-f", chunk.candidate, published)
    if new == old:
        return ChunkState("unchanged", _rev(repo, published), old, "none"), ""
    rebased = _git(repo, "rebase", "--onto", new, old, chunk.candidate, check=False)
    if rebased.returncode != 0:
        _git(repo, "rebase", "--abort")
        _git(repo, "checkout", "-q", "--detach")
        _git(repo, "branch", "-D", chunk.candidate)
        return ChunkState("conflict", None, new, "none"), "rebase conflict, aborted"
    _git(repo, "checkout", "-q", "--detach")
    return ChunkState("ok", _rev(repo, chunk.candidate), new, "pending"), ""


def rebuild(loaded: manifest.Manifest, repo: Path, upstream_ref: str = "upstream/main",
            origin: str = "origin") -> dict[str, ChunkState]:
    repo = Path(repo)
    dirty = _git(repo, "status", "--porcelain").stdout
    if dirty.strip():
        raise RebuildError(f"work tree is dirty, rebuild switches branches:\n{dirty.rstrip()}")
    upstream = _rev(repo, upstream_ref)
    if upstream is None:
        raise RebuildError(f"{upstream_ref} does not exist")
    head = _git(repo, "symbolic-ref", "-q", "--short", "HEAD", check=False).stdout.strip()
    restore = head or _rev(repo, "HEAD")
    by_id = {c.id: c for c in loaded.chunks}
    states: dict[str, ChunkState] = {}
    _git(repo, "checkout", "-q", "--detach")
    try:
        for chunk in loaded.chunks:
            parent = states[chunk.requires] if chunk.requires else None
            result, reason = _rebase_one(chunk, parent, repo, upstream, origin, by_id)
            states[chunk.id] = result
            line = f"{chunk.id} {result.rebase} {result.candidate or '-'}"
            print(f"{line} ({reason})" if reason else line, flush=True)
    finally:
        _git(repo, "checkout", "-q", restore)
    return states
