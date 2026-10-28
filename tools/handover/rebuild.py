# Copyright 2026 Ronny Trommer <ronny@no42.org>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Rebase every published review branch onto its new base, parents first.

Each chunk's `origin/review/<...>` is copied to a local
`handover-candidate/<...>` and rebased with a plain `git rebase` onto the
upstream tip (a root) or the parent's candidate (a child). Git skips
commits patch-equivalent to ones already in the new base, so a child still
carrying an older copy of its parent drops those copies; a copy that was
altered conflicts instead. `unchanged` means the rebase left the published
tip as it was. A chunk with no commits left over its base has landed.
A child of a chunk that failed does not move at all.

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


def _failure(repo: Path, rebased: subprocess.CompletedProcess) -> str:
    """Why a rebase failed. Only git's own conflict report counts as a conflict.

    Anything else, such as a missing committer identity, is still recorded as
    rebase "conflict", so it fails closed, but with git's message as the reason.
    """
    output = rebased.stdout + rebased.stderr
    unmerged = _git(repo, "diff", "--name-only", "--diff-filter=U", check=False).stdout.strip()
    if "CONFLICT" in output or unmerged:
        return "rebase conflict, aborted"
    lines = [ln.strip() for ln in rebased.stderr.splitlines() if ln.strip()]
    first = next((ln for ln in lines if ln.startswith(("fatal:", "error:"))),
                 lines[0] if lines else f"exit {rebased.returncode}")
    return f"rebase failed: {first}"


def _rebase_one(chunk: manifest.Chunk, parent: ChunkState | None, repo: Path,
                upstream: str, origin: str, by_id: dict) -> tuple[ChunkState, str]:
    published = f"{origin}/{chunk.branch}"
    if parent is not None and parent.rebase in FAILED:
        behind = _rev(repo, f"{origin}/{by_id[chunk.requires].branch}")
        return ChunkState("parent-behind", None, behind, "none"), f"parent {chunk.requires} failed"
    new = parent.candidate if parent is not None else upstream
    tip = _rev(repo, published)
    if tip is None:
        return ChunkState("conflict", None, new, "none"), f"no origin branch {published}"
    _git(repo, "branch", "-f", chunk.candidate, published)
    rebased = _git(repo, "rebase", new, chunk.candidate, check=False)
    if rebased.returncode != 0:
        reason = _failure(repo, rebased)
        # A rebase that failed before it started leaves nothing to abort.
        _git(repo, "rebase", "--abort", check=False)
        _git(repo, "checkout", "-q", "--detach")
        _git(repo, "branch", "-D", chunk.candidate)
        return ChunkState("conflict", None, new, "none", published=tip), reason
    _git(repo, "checkout", "-q", "--detach")
    candidate = _rev(repo, chunk.candidate)
    ahead = _git(repo, "rev-list", "--count", f"{new}..{candidate}").stdout.strip()
    if ahead == "0":
        return ChunkState("ok", candidate, new, "none", landed=True, published=tip), "landed upstream"
    if candidate == tip:
        return ChunkState("unchanged", candidate, new, "none", published=tip), ""
    return ChunkState("ok", candidate, new, "pending", published=tip), ""


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
            if result.rebase in FAILED:
                result.reason = reason
            states[chunk.id] = result
            line = f"{chunk.id} {result.rebase} {result.candidate or '-'}"
            print(f"{line} ({reason})" if reason else line, flush=True)
    finally:
        _git(repo, "checkout", "-q", restore)
    return states
