# Copyright 2026 Ronny Trommer <ronny@no42.org>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Test plan, test runner and promotion of handover candidates.

`matrix` lists the goals CI runs per candidate. `run_tests` runs one chunk's
goals in the checked-out candidate. `promote` force-pushes passing
candidates to their `review/*` branch on origin, never to upstream.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

import manifest
from state import ChunkState

UPSTREAM = "grafana/grafana-ansible-collection"
# A parent in one of these states does not hold its children back.
SETTLED = ("unchanged",)


def assert_not_upstream(url: str) -> None:
    if UPSTREAM in url.lower():
        raise SystemExit(f"handover: refusing to write to upstream remote {url}")


def matrix(loaded: manifest.Manifest, states: dict[str, ChunkState]) -> list[dict]:
    """One entry per test goal of every chunk that rebased and has not landed."""
    out = []
    for chunk in loaded.chunks:
        s = states.get(chunk.id)
        if s is None or s.rebase != "ok" or s.landed:
            continue
        out.extend({"chunk": chunk.id, "ref": chunk.candidate, "goal": g} for g in chunk.tests)
    return out


def run_tests(chunk: manifest.Chunk, repo: Path) -> bool:
    """Run each goal as `make <goal>` in `repo`. A missing target is a failure."""
    for goal in chunk.tests:
        words = shlex.split(goal)
        probe = subprocess.run(["make", "-n", words[0]], cwd=repo, capture_output=True, text=True)
        if probe.returncode != 0:
            print(f"handover: {chunk.id}: no make target {words[0]!r} in this tree")
            return False
        print(f"handover: {chunk.id}: make {goal}", flush=True)
        if subprocess.run(["make", *words], cwd=repo).returncode != 0:
            print(f"handover: {chunk.id}: make {goal} failed")
            return False
    return True


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, env=os.environ)


def _origin_url(repo: Path, origin: str) -> str:
    done = _git(repo, "remote", "get-url", origin)
    if done.returncode != 0:
        raise SystemExit(f"handover: no remote {origin!r}: {done.stderr.strip()}")
    url = done.stdout.strip()
    assert_not_upstream(url)
    return url


def _push(chunk: manifest.Chunk, state: ChunkState, repo: Path, origin: str) -> bool:
    _origin_url(repo, origin)
    seen = _git(repo, "rev-parse", "--verify", "--quiet", f"refs/remotes/{origin}/{chunk.branch}")
    old = seen.stdout.strip() if seen.returncode == 0 else ""
    done = _git(repo, "push", f"--force-with-lease={chunk.branch}:{old}", origin,
                f"{state.candidate}:refs/heads/{chunk.branch}")
    if done.returncode != 0:
        print(f"handover: {chunk.id}: push refused: {done.stderr.strip()}")
    return done.returncode == 0


def _delete_candidates(repo: Path, origin: str) -> None:
    _origin_url(repo, origin)
    listed = _git(repo, "ls-remote", "--heads", origin, "refs/heads/handover-candidate/*")
    refs = [line.split()[1] for line in listed.stdout.splitlines() if line.strip()]
    if refs:
        _origin_url(repo, origin)
        _git(repo, "push", origin, "--delete", *refs)


def promote(loaded: manifest.Manifest, states: dict[str, ChunkState], results: dict[str, bool],
            today: str, upstream_sha: str, origin: str = "origin",
            repo: Path = Path(".")) -> dict[str, ChunkState]:
    repo = Path(repo)
    _origin_url(repo, origin)
    satisfied: set[str] = set()
    for chunk in loaded.chunks:
        s = states[chunk.id]
        if s.landed or s.rebase in SETTLED:
            satisfied.add(chunk.id)
            continue
        if s.rebase != "ok":
            continue
        if chunk.tests:
            passed = results.get(chunk.id, False)
            s.tests = "pass" if passed else "fail"
        else:
            passed = True
            s.tests = "none"
        if not passed or (chunk.requires and chunk.requires not in satisfied):
            continue
        if not _push(chunk, s, repo, origin):
            continue
        s.promoted = True
        satisfied.add(chunk.id)
        if chunk.tests:
            s.verified_at = {"upstream": upstream_sha, "date": today}
            s.last_good = dict(s.verified_at)
    _delete_candidates(repo, origin)
    return states
