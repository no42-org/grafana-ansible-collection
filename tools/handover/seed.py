# Copyright 2026 Ronny Trommer <ronny@no42.org>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build a chunk's first review branch by cherry-picking its commits.

The branch starts at the upstream ref (a root chunk) or at the parent's local
review branch (a child). Commits are picked in manifest order without -x, so
authorship is kept and the origin line a carried commit already has is not
doubled. Seeding is human-guided: a conflict, or a commit that turns empty,
leaves the cherry-pick in progress on the branch and stops. The human
resolves it and runs `--continue`. Seed notes are printed, never applied.

Nothing is pushed. The branch the user started on is remembered in the git
directory (not in git config) and checked out again when seeding finishes.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import manifest


class SeedError(Exception):
    pass


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    done = subprocess.run(["git", "-c", "core.editor=true", *args], cwd=repo,
                          capture_output=True, text=True,
                          env={**os.environ, "GIT_EDITOR": "true"})
    if check and done.returncode != 0:
        raise SeedError(f"git {' '.join(args)}: {done.stderr.strip()}")
    return done


def _exists(repo: Path, ref: str) -> bool:
    return _git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}",
                check=False).returncode == 0


def _marker(repo: Path, chunk: manifest.Chunk) -> Path:
    path = _git(repo, "rev-parse", "--git-path", f"handover-seed-{chunk.id}").stdout.strip()
    return Path(path) if os.path.isabs(path) else repo / path


def _current(repo: Path) -> str:
    return _git(repo, "symbolic-ref", "-q", "--short", "HEAD", check=False).stdout.strip()


def _picking(repo: Path) -> bool:
    return _git(repo, "rev-parse", "--verify", "--quiet", "CHERRY_PICK_HEAD",
                check=False).returncode == 0


def _in_progress(repo: Path) -> bool:
    """A pick is stopped, or picks remain queued (the human ran `git commit`)."""
    todo = _git(repo, "rev-parse", "--git-path", "sequencer/todo").stdout.strip()
    todo_path = Path(todo) if os.path.isabs(todo) else repo / todo
    return _picking(repo) or todo_path.exists()


def _stopped(chunk: manifest.Chunk, repo: Path) -> int:
    print(f"handover: seeding {chunk.id} stopped on a commit that did not apply cleanly.")
    if _picking(repo):
        head = _git(repo, "rev-parse", "CHERRY_PICK_HEAD").stdout.strip()
        subject = _git(repo, "log", "-1", "--format=%s", head).stdout.strip()
        print(f"  stopped at {head[:12]} {subject}")
    if chunk.seed_notes.strip():
        print(f"seed notes for {chunk.id}:\n{chunk.seed_notes.rstrip()}")
    print("Resolve the files, then:\n"
          "  git add <files>\n"
          f"  make handover-seed CHUNK={chunk.id} CONTINUE=1\n"
          "If the commit became empty, run `git cherry-pick --skip` instead, "
          "then the make command.\n"
          "To give up: git cherry-pick --abort; git checkout <your branch>; "
          f"git branch -D {chunk.branch}")
    return 1


def _finish(chunk: manifest.Chunk, repo: Path, base: str) -> int:
    count = _git(repo, "rev-list", "--count", f"{base}..{chunk.branch}").stdout.strip()
    marker = _marker(repo, chunk)
    origin = marker.read_text().strip() if marker.exists() else ""
    marker.unlink(missing_ok=True)
    if origin and origin != chunk.branch:
        _git(repo, "checkout", "-q", origin)
    if count != str(len(chunk.commits)):
        print(f"warning: {chunk.id} lists {len(chunk.commits)} commits but {chunk.branch} "
              f"has {count} over {base} (skipped or emptied commits are expected)")
    noun = "commit" if count == "1" else "commits"
    print(f"{chunk.branch}: {count} {noun} over {base}")
    return 0


def _base_ref(chunk: manifest.Chunk, loaded: manifest.Manifest, upstream: str,
              repo: Path) -> str:
    if chunk.requires is None:
        if not _exists(repo, upstream):
            raise SeedError(f"{upstream} does not exist")
        return upstream
    parent = next(c for c in loaded.chunks if c.id == chunk.requires)
    if not _exists(repo, f"refs/heads/{parent.branch}"):
        raise SeedError(f"{chunk.id} needs its parent {parent.id}: seed it first "
                        f"(make handover-seed CHUNK={parent.id}); {parent.branch} does not exist")
    return parent.branch


def seed(chunk: manifest.Chunk, loaded: manifest.Manifest, repo: Path,
         upstream: str = "upstream/main", origin: str = "origin",
         resume: bool = False) -> int:
    repo = Path(repo)
    base = _base_ref(chunk, loaded, upstream, repo)
    if resume:
        if _current(repo) != chunk.branch:
            raise SeedError(f"--continue: check out {chunk.branch} first "
                            f"(it is on {_current(repo) or 'a detached HEAD'})")
        if _in_progress(repo):
            done = _git(repo, "cherry-pick", "--continue", check=False)
            if done.returncode != 0 and "no cherry-pick" not in done.stderr.lower():
                print(done.stderr.strip())
                return _stopped(chunk, repo)
        if _in_progress(repo):
            return _stopped(chunk, repo)
        return _finish(chunk, repo, base)
    dirty = _git(repo, "status", "--porcelain").stdout
    if dirty.strip():
        raise SeedError(f"work tree is dirty, seeding switches branches:\n{dirty.rstrip()}")
    for ref in (f"refs/heads/{chunk.branch}", f"refs/remotes/{origin}/{chunk.branch}"):
        if _exists(repo, ref):
            raise SeedError(f"{ref.split('/', 2)[2]} already exists; seeding never overwrites")
    if not chunk.commits:
        raise SeedError(f"{chunk.id} lists no commits")
    print(f"seeding {chunk.branch} from {base}, {len(chunk.commits)} commits")
    if chunk.seed_notes.strip():
        print(f"seed notes for {chunk.id}:\n{chunk.seed_notes.rstrip()}")
    started = _current(repo) or _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "checkout", "-q", "-b", chunk.branch, base)
    _marker(repo, chunk).write_text(started + "\n")
    picked = _git(repo, "cherry-pick", *chunk.commits, check=False)
    if picked.returncode != 0:
        print(picked.stderr.strip())
        return _stopped(chunk, repo)
    return _finish(chunk, repo, base)
