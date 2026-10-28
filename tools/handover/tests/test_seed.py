# Copyright 2026 Ronny Trommer <ronny@no42.org>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for seeding review branches, against throwaway remotes."""

import contextlib
import io
import os
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

import handover
from tests.gitfixture import Fixture

JANE = ("Jane Contributor", "jane@example.net")


class TestSeed(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.fx = Fixture(Path(tmp.name))
        patcher = mock.patch.dict(os.environ, self.fx.env)
        patcher.start()
        self.addCleanup(patcher.stop)

    def git(self, *args):
        return self.fx.git(self.fx.work, *args)

    def on_main(self, name, text, message, author=None):
        return self.fx.commit(self.fx.work, name, text, message, author)

    def manifest(self, *chunks):
        """chunks are (id, slug, parent, [shas], notes)."""
        body = ""
        for cid, slug, parent, shas, notes in chunks:
            body += textwrap.dedent(f"""\
              - id: {cid}
                slug: {slug}
                group: harness
                epic: cross-role
                title: Title {cid}
                summary: |
                  Text.
                seed_notes: "{notes}"
                commits: [{", ".join(shas)}]
                requires: [{parent or ""}]
                upstream: {{closes: [], carries: [], supersedes: []}}
                tests: []
            """)
        path = self.fx.root / "chunks.yml"
        path.write_text("fork_only: []\nchunks:\n" + textwrap.indent(body, "  "))
        return path

    def seed(self, path, chunk, *extra):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = handover.main(["seed", "--manifest", str(path), "--repo", str(self.fx.work),
                                  "--chunk", chunk, *extra])
        return code, out.getvalue()

    def test_seed_preserves_author(self):
        sha = self.on_main("a", "a\n", "carried fix", JANE)
        path = self.manifest(("T1", "a", None, [sha], ""))
        code, out = self.seed(path, "T1")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.git("log", "-1", "--format=%an <%ae>", "review/t1-a"),
                         "Jane Contributor <jane@example.net>")
        self.assertEqual(self.git("log", "-1", "--format=%b", "review/t1-a"), "")
        self.assertEqual(self.git("rev-parse", "--abbrev-ref", "HEAD"), "main")
        self.assertIn("review/t1-a", out)
        self.assertIn("1 commit", out)

    def test_seed_stops_on_conflict_and_continues(self):
        self.fx.upstream_commit("shared", "one\n2\nthree\n", "upstream edit")
        sha = self.on_main("shared", "one\nTWO\nthree\n", "conflicting", JANE)
        path = self.manifest(("T1", "a", None, [sha], "drop the TWO hunk"))
        code, out = self.seed(path, "T1")
        self.assertEqual(code, 1, out)
        self.assertIn(sha[:8], out)
        self.assertIn("drop the TWO hunk", out)
        self.assertIn("make handover-seed CHUNK=T1 CONTINUE=1", out)
        self.assertEqual(self.git("rev-parse", "--abbrev-ref", "HEAD"), "review/t1-a")
        (self.fx.work / "shared").write_text("one\nTWO\nthree\n")
        self.git("add", "shared")
        code, out = self.seed(path, "T1", "--continue")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.git("log", "-1", "--format=%an", "review/t1-a"), "Jane Contributor")
        self.assertEqual(self.git("rev-parse", "--abbrev-ref", "HEAD"), "main")
        self.assertIn("1 commit", out)

    def test_seed_refuses_existing_branch(self):
        sha = self.on_main("a", "a\n", "fix")
        path = self.manifest(("T1", "a", None, [sha], ""))
        self.git("branch", "review/t1-a", "upstream/main")
        code, out = self.seed(path, "T1")
        self.assertEqual(code, 2, out)
        self.assertIn("review/t1-a", out)
        self.git("branch", "-D", "review/t1-a")
        self.git("push", "-q", "origin", "main:refs/heads/review/t1-a")
        self.git("fetch", "-q", "origin")
        code, out = self.seed(path, "T1")
        self.assertEqual(code, 2, out)
        self.assertIn("origin/review/t1-a", out)

    def test_seed_child_requires_parent_branch(self):
        s1 = self.on_main("a", "a\n", "one")
        s2 = self.on_main("b", "b\n", "two")
        path = self.manifest(("T1", "a", None, [s1], ""), ("T2", "b", "T1", [s2], ""))
        code, out = self.seed(path, "T2")
        self.assertEqual(code, 2, out)
        self.assertIn("review/t1-a", out)
        self.assertIn("seed", out)
        self.assertEqual(self.seed(path, "T1")[0], 0)
        code, out = self.seed(path, "T2")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.git("rev-list", "--count", "review/t1-a..review/t2-b"), "1")

    def test_seed_refuses_dirty_tree(self):
        sha = self.on_main("a", "a\n", "one")
        path = self.manifest(("T1", "a", None, [sha], ""))
        (self.fx.work / "shared").write_text("dirty\n")
        code, out = self.seed(path, "T1")
        self.assertEqual(code, 2, out)
        self.assertIn("dirty", out)
        self.assertEqual(self.git("branch", "--list", "review/t1-a"), "")

    def test_seed_requires_chunk(self):
        sha = self.on_main("a", "a\n", "one")
        path = self.manifest(("T1", "a", None, [sha], ""))
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = handover.main(["seed", "--manifest", str(path), "--repo", str(self.fx.work)])
        self.assertEqual(code, 2)
        self.assertIn("one chunk", out.getvalue())


if __name__ == "__main__":
    unittest.main()
