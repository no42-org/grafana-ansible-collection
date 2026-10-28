# Copyright 2026 Ronny Trommer <ronny@no42.org>
# SPDX-License-Identifier: GPL-3.0-or-later
"""A throwaway fork layout for handover tests: bare `upstream` and `origin`
remotes, a work clone of both, and an authoring clone of upstream.

Everything lives under one temporary directory. HOME points there too, so
neither the user's git config nor the real repository is read or touched.
"""

from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

TEST_ENV = {
    "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.com",
    "GIT_CONFIG_NOSYSTEM": "1",
}


class Fixture:
    def __init__(self, root: Path):
        self.root = root
        self.env = {**TEST_ENV, "HOME": str(root), "PATH": os.environ.get("PATH", "")}
        self.upstream = root / "upstream.git"
        self.origin = root / "origin.git"
        self.work = root / "work"
        self.up = root / "up"
        self.git(root, "init", "-q", "--bare", "-b", "main", str(self.upstream))
        self.git(root, "init", "-q", "--bare", "-b", "main", str(self.origin))
        self.git(root, "clone", "-q", str(self.upstream), str(self.up))
        self.commit(self.up, "shared", "one\ntwo\nthree\n", "base")
        self.git(self.up, "push", "-q", "origin", "HEAD:refs/heads/main")
        self.git(root, "clone", "-q", "-o", "upstream", str(self.upstream), str(self.work))
        self.git(self.work, "remote", "add", "origin", str(self.origin))
        self.git(self.work, "push", "-q", "origin", "main")
        self.git(self.work, "fetch", "-q", "origin")

    def git(self, repo: Path, *args: str, env: dict | None = None) -> str:
        return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True,
                              text=True, env={**self.env, **(env or {})}).stdout.strip()

    def commit(self, repo: Path, name: str, text: str, message: str,
               author: tuple[str, str] | None = None) -> str:
        (repo / name).write_text(text)
        self.git(repo, "add", name)
        env = {"GIT_AUTHOR_NAME": author[0], "GIT_AUTHOR_EMAIL": author[1]} if author else None
        self.git(repo, "commit", "-q", "-m", message, env=env)
        return self.git(repo, "rev-parse", "HEAD")

    def upstream_commit(self, name: str, text: str, message: str) -> str:
        """Advance upstream/main by one commit and fetch it into the work clone."""
        sha = self.commit(self.up, name, text, message)
        self.git(self.up, "push", "-q", "origin", "HEAD:main")
        self.git(self.work, "fetch", "-q", "upstream")
        return sha

    def review_branch(self, branch: str, base: str, *commits: tuple) -> str:
        """Publish origin/<branch>: `commits` are (file, text, message[, author]) on `base`."""
        self.git(self.work, "checkout", "-q", "--detach", base)
        for entry in commits:
            self.commit(self.work, *entry)
        self.git(self.work, "push", "-q", "-f", "origin", f"HEAD:refs/heads/{branch}")
        self.git(self.work, "fetch", "-q", "origin")
        self.git(self.work, "checkout", "-q", "main")
        return self.git(self.work, "rev-parse", f"origin/{branch}")

    def manifest(self, *chunks: tuple[str, str, str | None]) -> Path:
        """Write a chunks.yml of (id, slug, parent) entries and return its path."""
        body = ""
        for cid, slug, parent in chunks:
            body += textwrap.dedent(f"""\
              - id: {cid}
                slug: {slug}
                group: harness
                epic: cross-role
                title: Title {cid}
                summary: |
                  Text.
                commits: []
                requires: [{parent or ""}]
                upstream: {{closes: [], carries: [], supersedes: []}}
                tests: []
            """)
        path = self.root / "chunks.yml"
        path.write_text("fork_only: []\nchunks:\n" + textwrap.indent(body, "  "))
        return path
