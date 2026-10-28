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
    """One entry per chunk with tests, among chunks that rebased and has not landed."""
    out = []
    for chunk in loaded.chunks:
        s = states.get(chunk.id)
        if s is None or s.rebase != "ok" or s.landed:
            continue
        if chunk.tests:
            out.append({"chunk": chunk.id, "ref": chunk.candidate, "goals": list(chunk.tests)})
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


def _push_url(repo: Path, origin: str) -> str:
    """Resolve origin once, refuse upstream in any URL, and return the one push URL.

    Every later write goes to this URL, never the remote name, so pushurl or
    pushInsteadOf cannot redirect it after the check.
    """
    urls = []
    for flags in ((), ("--push",)):
        done = _git(repo, "remote", "get-url", *flags, "--all", origin)
        if done.returncode != 0:
            raise SystemExit(f"handover: no remote {origin!r}: {done.stderr.strip()}")
        found = done.stdout.split()
        urls.append(found)
        for url in found:
            assert_not_upstream(url)
    if len(urls[1]) != 1:
        raise SystemExit(f"handover: {origin!r} must have exactly one push URL, has {len(urls[1])}")
    return urls[1][0]


def _push(chunk: manifest.Chunk, state: ChunkState, repo: Path, url: str) -> bool:
    old = state.published or ""
    done = _git(repo, "push", f"--force-with-lease={chunk.branch}:{old}", url,
                f"{state.candidate}:refs/heads/{chunk.branch}")
    if done.returncode != 0:
        print(f"handover: {chunk.id}: push refused: {done.stderr.strip()}")
    return done.returncode == 0


def _delete_candidates(repo: Path, url: str) -> None:
    """Best effort: a cleanup failure is reported but never undoes a promotion."""
    listed = _git(repo, "ls-remote", "--heads", url, "refs/heads/handover-candidate/*")
    if listed.returncode != 0:
        print(f"handover: cannot list candidates: {listed.stderr.strip()}")
        return
    prefix = "refs/heads/handover-candidate/"
    refs = [r for r in (line.split()[1] for line in listed.stdout.splitlines() if line.strip())
            if r.startswith(prefix)]
    if refs:
        done = _git(repo, "push", url, "--delete", *refs)
        if done.returncode != 0:
            print(f"handover: cannot delete candidates: {done.stderr.strip()}")


def promote(loaded: manifest.Manifest, states: dict[str, ChunkState], results: dict[str, bool],
            today: str, upstream_sha: str, origin: str = "origin",
            repo: Path = Path(".")) -> dict[str, ChunkState]:
    repo = Path(repo)
    url = _push_url(repo, origin)
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
        if not _push(chunk, s, repo, url):
            continue
        s.promoted = True
        satisfied.add(chunk.id)
        if chunk.tests:
            s.verified_at = {"upstream": upstream_sha, "date": today}
            s.last_good = dict(s.verified_at)
    _delete_candidates(repo, url)
    return states
