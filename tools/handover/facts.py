# Copyright 2026 Ronny Trommer <ronny@no42.org>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Facts the handover page shows: commits, landed state, CLA status, the board.

Every GitHub call goes through one injected `gh(args) -> str`. The real one
is read-only by construction: it refuses write flags and any `api` path
outside the upstream repository's own routes.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import manifest

REPO_API = "repos/grafana/grafana-ansible-collection/"
BOARD_ARGS = ["project", "item-list", "4", "--owner", "no42-org", "--limit", "1000",
              "--format", "json"]
BOARD_LIMIT = 1000
RONNY_PR = 510
RONNY_EMAIL = "ronny@no42.org"
RONNY_NAME = "Ronny Trommer"
TITLE_PREFIX = re.compile(r"^\[(?:Issue|PR) #\d+\] ")

Gh = Callable[[list[str]], str]


class GhError(Exception):
    pass


def _allowed_api(args: list[str]) -> bool:
    """Only `api <path>` or `api <path> --paginate` on an upstream repository route."""
    if len(args) not in (2, 3) or args[0] != "api" or (len(args) == 3 and args[2] != "--paginate"):
        return False
    path = args[1]
    return (path.startswith(REPO_API) and ".." not in path
            and not re.search(r"\s", path) and not path.startswith("-"))


def real_gh(args: list[str]) -> str:
    if args != BOARD_ARGS and not _allowed_api(args):
        raise SystemExit(f"handover: refusing gh call outside the allowed reads: {args}")
    try:
        done = subprocess.run(["gh", *args], capture_output=True, text=True)
    except FileNotFoundError:
        raise GhError("gh is not installed") from None
    if done.returncode != 0:
        raise GhError(f"gh {' '.join(args)} failed: {done.stderr.strip()}")
    return done.stdout


@dataclass
class ChunkFacts:
    commits: list[dict] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    insertions: int = 0
    deletions: int = 0
    found: bool = False


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return manifest.git(repo, *args)


def branch_ref(repo: Path, branch: str) -> str | None:
    for ref in (branch, f"origin/{branch}"):
        if _git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}").returncode == 0:
            return ref
    return None


def _base_ref(chunk: manifest.Chunk, loaded: manifest.Manifest | None, repo: Path,
              upstream: str) -> str | None:
    if not chunk.requires:
        return upstream
    parent = next((c for c in loaded.chunks if c.id == chunk.requires), None) if loaded else None
    return branch_ref(repo, parent.branch) if parent else None


def chunk_facts(chunk: manifest.Chunk, repo: Path, loaded: manifest.Manifest | None = None,
                upstream: str = "upstream/main") -> ChunkFacts:
    """Commits and diff of the chunk's branch relative to its base.

    A chunk with no local or origin branch yields empty facts with found False.
    """
    ref = branch_ref(repo, chunk.branch)
    base = _base_ref(chunk, loaded, repo, upstream)
    if ref is None or base is None:
        return ChunkFacts()
    facts = ChunkFacts(found=True)
    log = _git(repo, "log", "--reverse", "--format=%H%x1f%s%x1f%an%x1f%ae", f"{base}..{ref}")
    for line in log.stdout.splitlines():
        sha, subject, author, email = line.split("\x1f")
        facts.commits.append({"sha": sha, "subject": subject, "author": author, "email": email})
    for line in _git(repo, "diff", "--numstat", f"{base}...{ref}").stdout.splitlines():
        added, removed, name = line.split("\t", 2)
        facts.files.append(name)
        facts.insertions += int(added) if added.isdigit() else 0
        facts.deletions += int(removed) if removed.isdigit() else 0
    return facts


def is_landed(chunk: manifest.Chunk, repo: Path, merged_prs: set[int],
              loaded: manifest.Manifest | None = None, upstream: str = "upstream/main") -> bool:
    if chunk.carries and all(n in merged_prs for n in chunk.carries):
        return True
    ref = branch_ref(repo, chunk.branch)
    base = _base_ref(chunk, loaded, repo, upstream)
    if ref is None or base is None:
        return False
    cherry = _git(repo, "cherry", upstream, ref, base)
    if cherry.returncode == 0:
        lines = [ln for ln in cherry.stdout.splitlines() if ln.strip()]
        if lines and not any(ln.startswith("+") for ln in lines):
            return True
    # A multi-commit chunk squash-merged upstream has no patch-equivalent commits,
    # but upstream's tree already holds the chunk's final content.
    changed = _git(repo, "diff", "--name-only", f"{base}...{ref}")
    files = changed.stdout.splitlines() if changed.returncode == 0 else []
    return bool(files) and _git(repo, "diff", "--quiet", upstream, ref, "--", *files).returncode == 0


def _json(gh: Gh, args: list[str]):
    try:
        return json.loads(gh(args))
    except json.JSONDecodeError as err:
        raise GhError(f"gh {' '.join(args)} returned invalid JSON: {err}") from None


def pr_facts(gh: Gh, prs: list[int]) -> dict[int, dict]:
    """Per PR: cla (license/cla context of the head), merged, state, title, authors."""
    out = {}
    for n in prs:
        pr = _json(gh, ["api", f"{REPO_API}pulls/{n}"])
        sha = pr["head"]["sha"]
        status = _json(gh, ["api", f"{REPO_API}commits/{sha}/status"])
        cla = next((s.get("state", "unknown") for s in status.get("statuses", [])
                    if s.get("context") == "license/cla"), "unknown")
        commits = _json(gh, ["api", f"{REPO_API}pulls/{n}/commits?per_page=100"])
        authors = [(c["commit"]["author"].get("name", ""), c["commit"]["author"].get("email", ""))
                   for c in commits]
        out[n] = {"cla": cla, "merged": bool(pr.get("merged")), "state": pr.get("state", ""),
                  "title": pr.get("title", ""), "authors": authors}
    return out


def cla_status(gh: Gh, prs: list[int]) -> dict[int, str]:
    return {n: p["cla"] for n, p in pr_facts(gh, prs).items()}


def author_cla(name: str, email: str, prs: dict[int, dict]) -> str:
    """Ronny uses #510's status, a bot is "bot", a carried author uses that PR's, else unknown."""
    if email.lower() == RONNY_EMAIL or name == RONNY_NAME:
        return prs.get(RONNY_PR, {}).get("cla", "unknown")
    if name.endswith("[bot]"):
        return "bot"
    for n, pr in prs.items():
        if n != RONNY_PR and any(e.lower() == email.lower() for _, e in pr["authors"]):
            return pr["cla"]
    return "unknown"


def board_rows(gh: Gh) -> list[dict]:
    data = _json(gh, BOARD_ARGS)
    if data.get("totalCount", 0) > BOARD_LIMIT:
        raise GhError(f"board has {data['totalCount']} items but only {BOARD_LIMIT} were listed; "
                      "raise the limit")
    rows = []
    for item in data.get("items", []):
        title = item.get("title", "")
        number = item.get("upstream")
        if number is None:
            m = re.match(r"^\[(?:Issue|PR) #(\d+)\] ", title)
            if not m:
                continue
            number = m.group(1)
        rows.append({"number": int(number), "kind": item.get("kind", "-"),
                     "title": TITLE_PREFIX.sub("", title),
                     "decision": item.get("fork decision", "-"),
                     "epic": item.get("epic", "-"),
                     "target": item.get("target release", "-")})
    return sorted(rows, key=lambda r: r["number"])
