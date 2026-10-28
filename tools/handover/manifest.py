# Copyright 2026 Ronny Trommer <ronny@no42.org>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Load and validate tools/handover/chunks.yml.

Every later handover step imports this, so the rules live here once: the
shape of a chunk, which make goals a chunk may run, that chunks stack in a
tree (at most one parent), and that no commit is claimed twice.

Test goals are checked against an allowlist because they reach `make` as
words. A goal like `role-test ROLE=$(rm)` must be rejected before anything
sees it.

Plain stdlib plus PyYAML, which ansible-core brings in.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import yaml

GROUPS = ("fixes", "carried", "harness", "toolchain", "pinning", "removals", "docs")
GOALS = ("role-test", "module-test", "ci-lint", "ci-lint-release", "sanity", "units",
         "version-select-test")
ID_RE = re.compile(r"^[A-Z]{1,3}[0-9]{1,2}$")
SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
ARG_RE = re.compile(r"^[A-Z_]+=[A-Za-z0-9_.-]+$")


class ManifestError(Exception):
    pass


@dataclass(frozen=True)
class Chunk:
    id: str
    slug: str
    group: str
    epic: str
    title: str
    summary: str
    commits: tuple[str, ...]
    requires: str | None
    closes: tuple[int, ...]
    carries: tuple[int, ...]
    supersedes: tuple[int, ...]
    tests: tuple[str, ...]
    seed_notes: str = ""

    @property
    def branch(self) -> str:
        return f"review/{self.id.lower()}-{self.slug}"

    @property
    def candidate(self) -> str:
        return f"handover-candidate/{self.id.lower()}-{self.slug}"


@dataclass(frozen=True)
class ForkOnly:
    title: str
    why: str
    commits: tuple[str, ...]


@dataclass(frozen=True)
class Manifest:
    chunks: tuple[Chunk, ...]
    fork_only: tuple[ForkOnly, ...]

    def children(self, id: str) -> tuple[Chunk, ...]:
        """Every chunk below `id`, transitively, in dependency order."""
        below = {id}
        found = []
        for chunk in self.chunks:
            if chunk.requires in below:
                below.add(chunk.id)
                found.append(chunk)
        return tuple(found)

    def all_commits(self) -> set[str]:
        shas = {sha for c in self.chunks for sha in c.commits}
        return shas | {sha for f in self.fork_only for sha in f.commits}


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def _text(entry: dict, key: str, where: str) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{where}: {key} must be a non-empty string")
    return value


def _list(entry: dict, key: str, where: str) -> list:
    value = entry.get(key, [])
    if not isinstance(value, list):
        raise ManifestError(f"{where}: {key} must be a list")
    return value


def _numbers(entry: dict, key: str, where: str) -> tuple[int, ...]:
    values = _list(entry, key, where)
    if not all(isinstance(v, int) and not isinstance(v, bool) for v in values):
        raise ManifestError(f"{where}: {key} must list numbers")
    return tuple(values)


def _resolve(repo: Path, main: str, sha: object, where: str) -> str:
    if not isinstance(sha, str) or len(sha) < 8:
        raise ManifestError(f"{where}: commit {sha!r} must be a quoted sha of 8+ characters")
    found = git(repo, "rev-parse", "--verify", f"{sha}^{{commit}}")
    if found.returncode != 0:
        raise ManifestError(f"{where}: commit {sha} does not exist")
    full = found.stdout.strip()
    if git(repo, "merge-base", "--is-ancestor", full, main).returncode != 0:
        raise ManifestError(f"{where}: commit {sha} is not on {main}")
    return full


def _check_goal(goal: object, where: str) -> str:
    words = goal.split(" ") if isinstance(goal, str) else []
    if not words or words[0] not in GOALS or not all(ARG_RE.match(w) for w in words[1:]):
        raise ManifestError(f"{where}: tests entry {goal!r} is not an allowed make goal")
    return goal


def _parse_chunk(raw: object, index: int, repo: Path, main: str) -> Chunk:
    if not isinstance(raw, dict):
        raise ManifestError(f"chunks[{index}]: must be a mapping")
    cid = raw.get("id")
    if not isinstance(cid, str) or not ID_RE.match(cid):
        raise ManifestError(f"chunks[{index}]: id {cid!r} must match {ID_RE.pattern}")
    where = f"chunk {cid}"
    slug = _text(raw, "slug", where)
    if not SLUG_RE.match(slug):
        raise ManifestError(f"{where}: slug {slug!r} must match {SLUG_RE.pattern}")
    group = raw.get("group")
    if group not in GROUPS:
        raise ManifestError(f"{where}: group {group!r} must be one of {', '.join(GROUPS)}")
    requires = raw.get("requires", [])
    if isinstance(requires, str):
        requires = [requires]
    if not isinstance(requires, list):
        raise ManifestError(f"{where}: requires must be a list")
    if len(requires) > 1:
        raise ManifestError(f"{where}: requires names at most one parent, got {requires}")
    upstream = raw.get("upstream") or {}
    if not isinstance(upstream, dict):
        raise ManifestError(f"{where}: upstream must be a mapping")
    notes = raw.get("seed_notes", "")
    if not isinstance(notes, str):
        raise ManifestError(f"{where}: seed_notes must be a string")
    return Chunk(
        id=cid, slug=slug, group=group, epic=_text(raw, "epic", where),
        title=_text(raw, "title", where), summary=_text(raw, "summary", where),
        commits=tuple(_resolve(repo, main, s, where) for s in _list(raw, "commits", where)),
        requires=requires[0] if requires else None,
        closes=_numbers(upstream, "closes", f"{where} upstream"),
        carries=_numbers(upstream, "carries", f"{where} upstream"),
        supersedes=_numbers(upstream, "supersedes", f"{where} upstream"),
        tests=tuple(_check_goal(g, where) for g in _list(raw, "tests", where)),
        seed_notes=notes,
    )


def _order(chunks: list[Chunk]) -> tuple[Chunk, ...]:
    by_id = {}
    for chunk in chunks:
        if chunk.id in by_id:
            raise ManifestError(f"chunk {chunk.id}: duplicate id")
        by_id[chunk.id] = chunk
    for chunk in chunks:
        if chunk.requires is not None and chunk.requires not in by_id:
            raise ManifestError(f"chunk {chunk.id}: requires unknown chunk {chunk.requires}")
    ordered: list[Chunk] = []
    done: set[str] = set()
    visiting: list[str] = []

    def visit(chunk: Chunk) -> None:
        if chunk.id in done:
            return
        if chunk.id in visiting:
            ring = visiting[visiting.index(chunk.id):] + [chunk.id]
            raise ManifestError(f"chunk {chunk.id}: requires cycle {' -> '.join(ring)}")
        visiting.append(chunk.id)
        if chunk.requires is not None:
            visit(by_id[chunk.requires])
        visiting.pop()
        done.add(chunk.id)
        ordered.append(chunk)

    for chunk in chunks:
        visit(chunk)
    return tuple(ordered)


def load(path: Path, repo: Path, main: str = "main") -> Manifest:
    try:
        data = yaml.safe_load(Path(path).read_text())
    except (OSError, yaml.YAMLError) as err:
        raise ManifestError(f"{path}: {err}") from err
    if not isinstance(data, dict):
        raise ManifestError(f"{path}: top level must be a mapping")
    raw_chunks, raw_fork = data.get("chunks"), data.get("fork_only", [])
    if not isinstance(raw_chunks, list):
        raise ManifestError("chunks must be a list")
    if not isinstance(raw_fork, list):
        raise ManifestError("fork_only must be a list")
    chunks = [_parse_chunk(c, i, repo, main) for i, c in enumerate(raw_chunks)]
    fork_only = []
    for i, raw in enumerate(raw_fork):
        if not isinstance(raw, dict):
            raise ManifestError(f"fork_only[{i}]: must be a mapping")
        where = f"fork_only[{i}]"
        commits = tuple(_resolve(repo, main, s, where) for s in _list(raw, "commits", where))
        fork_only.append(ForkOnly(_text(raw, "title", where), _text(raw, "why", where), commits))
    owner: dict[str, str] = {}
    entries = [(f"chunk {c.id}", c.commits) for c in chunks]
    entries += [(f"fork_only {f.title!r}", f.commits) for f in fork_only]
    for name, commits in entries:
        for sha in commits:
            if sha in owner:
                raise ManifestError(f"{name}: commit {sha[:8]} is already in {owner[sha]}")
            owner[sha] = name
    return Manifest(_order(chunks), tuple(fork_only))
