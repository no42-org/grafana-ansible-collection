# Copyright 2026 Ronny Trommer <ronny@no42.org>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the handover manifest loader, against a throwaway git repository."""

import contextlib
import io
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

import handover
import manifest


def git(repo, *args):
    env = {
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.org",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.org",
        "HOME": str(repo), "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
    }
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True, text=True, env=env).stdout.strip()


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        self.repo = self.dir / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "main")
        self.shas = []
        self.commit("base")
        git(self.repo, "update-ref", "refs/remotes/upstream/main", "HEAD")
        self.commit("one")
        self.commit("two")
        self.commit("three")
        git(self.repo, "checkout", "-q", "-b", "side", "HEAD~3")
        self.commit("side")
        self.side = self.shas[-1]
        git(self.repo, "checkout", "-q", "main")

    def commit(self, name):
        (self.repo / name).write_text(name)
        git(self.repo, "add", name)
        git(self.repo, "commit", "-q", "-m", name)
        self.shas.append(git(self.repo, "rev-parse", "HEAD"))

    def chunk(self, id, slug="s", requires="[]", commits="[]", extra=""):
        return textwrap.dedent(f"""\
          - id: {id}
            slug: {slug}
            group: harness
            epic: cross-role
            title: Title {id}
            summary: |
              Text.
            commits: {commits}
            requires: {requires}
            upstream: {{closes: [], carries: [], supersedes: []}}
            tests: []
        """) + extra

    def doc(self, *chunks, fork_only="[]"):
        body = "".join(textwrap.indent(c, "  ") for c in chunks)
        return f"fork_only: {fork_only}\nchunks:\n{body}"

    def load(self, text):
        path = self.dir / "chunks.yml"
        path.write_text(text)
        return manifest.load(path, self.repo)

    def fails(self, text, *needles):
        with self.assertRaises(manifest.ManifestError) as cm:
            self.load(text)
        for needle in needles:
            self.assertIn(needle, str(cm.exception))


class TestManifest(Base):
    def test_orders_parents_first(self):
        m = self.load(self.doc(self.chunk("F1", "f", "[T1]"), self.chunk("T1", "t")))
        self.assertEqual([c.id for c in m.chunks], ["T1", "F1"])

    def test_rejects_cycle(self):
        self.fails(self.doc(self.chunk("A1", "a", "[B1]"), self.chunk("B1", "b", "[A1]")), "cycle")

    def test_rejects_two_parents(self):
        self.fails(self.doc(self.chunk("T1", "t"), self.chunk("T2", "u"),
                            self.chunk("F1", "f", "[T1, T2]")), "at most one", "F1")

    def test_rejects_unknown_parent(self):
        self.fails(self.doc(self.chunk("F1", "f", "[Z9]")), "Z9", "F1")

    def test_rejects_duplicate_id(self):
        self.fails(self.doc(self.chunk("T1", "a"), self.chunk("T1", "b")), "duplicate", "T1")

    def test_rejects_bad_slug(self):
        self.fails(self.doc(self.chunk("T1", "Bad_Slug")), "slug", "T1")

    def test_rejects_unknown_group(self):
        text = self.doc(self.chunk("T1")).replace("group: harness", "group: nonsense")
        self.fails(text, "group", "T1")

    def test_rejects_test_goal_outside_allowlist(self):
        for goal in ("dist", "role-test ROLE=$(rm)"):
            text = self.doc(self.chunk("T1")).replace("tests: []", f'tests: ["{goal}"]')
            self.fails(text, "tests", "T1")

    def test_rejects_goal_with_trailing_newline(self):
        for goal in ("role-test ROLE=x\\n", "sanity\\n"):
            text = self.doc(self.chunk("T1")).replace("tests: []", f'tests: ["{goal}"]')
            self.fails(text, "tests", "T1")

    def test_rejects_slug_and_id_with_trailing_newline(self):
        self.fails(self.doc(self.chunk("T1", "ok\\n")).replace("slug: ok\\n", 'slug: "ok\\n"'), "slug")

    def test_accepts_allowed_goals(self):
        text = self.doc(self.chunk("T1")).replace(
            "tests: []", 'tests: ["role-test ROLE=grafana DISTRO=rhel", "sanity"]')
        self.assertEqual(len(self.load(text).chunks[0].tests), 2)

    def test_rejects_commit_not_on_main(self):
        self.fails(self.doc(self.chunk("T1", commits=f'["{self.side[:10]}"]')),
                   self.side[:10], "main")

    def test_rejects_unknown_commit(self):
        self.fails(self.doc(self.chunk("T1", commits='["deadbeef"]')), "deadbeef")

    def test_rejects_commit_in_two_chunks(self):
        sha = self.shas[1][:8]
        self.fails(self.doc(self.chunk("T1", "a", commits=f'["{sha}"]'),
                            self.chunk("T2", "b", commits=f'["{sha}"]')), sha)

    def test_rejects_commit_in_chunk_and_fork_only(self):
        sha = self.shas[1][:8]
        fo = f'[{{title: X, why: Y, commits: ["{sha}"]}}]'
        self.fails(self.doc(self.chunk("T1", commits=f'["{sha}"]'), fork_only=fo), sha)

    def test_seed_notes_and_full_sha(self):
        sha = self.shas[1]
        extra = "  seed_notes: |\n    keep it\n"
        text = self.doc(self.chunk("T1", commits=f'["{sha[:8]}"]', extra=extra))
        c = self.load(text).chunks[0]
        self.assertEqual(c.commits, (sha,))
        self.assertEqual(c.seed_notes, "keep it\n")

    def test_branch_names(self):
        c = self.load(self.doc(self.chunk("T1", "role-test-harness"))).chunks[0]
        self.assertEqual(c.branch, "review/t1-role-test-harness")
        self.assertEqual(c.candidate, "handover-candidate/t1-role-test-harness")

    def test_children_transitive(self):
        m = self.load(self.doc(self.chunk("F2", "b", "[F1]"), self.chunk("F1", "a", "[T1]"),
                               self.chunk("T1", "t")))
        self.assertEqual([c.id for c in m.children("T1")], ["F1", "F2"])


class TestCli(Base):
    def run_cli(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = handover.main(["check", "--manifest", str(self.dir / "chunks.yml"),
                                  "--repo", str(self.repo), *args])
        return code, out.getvalue()

    def test_coverage_lists_unassigned_commits(self):
        covered = ",".join(f'"{s[:8]}"' for s in self.shas[1:3])
        (self.dir / "chunks.yml").write_text(self.doc(self.chunk("T1", commits=f"[{covered}]")))
        code, out = self.run_cli()
        self.assertEqual(code, 0, out)
        self.assertIn("1 chunks, 0 fork-only", out)
        code, out = self.run_cli("--coverage")
        self.assertEqual(code, 1)
        self.assertIn(self.shas[3], out)
        self.assertNotIn(self.shas[1], out)

    def test_error_exits_one(self):
        (self.dir / "chunks.yml").write_text("chunks: nope")
        code, out = self.run_cli()
        self.assertEqual(code, 1)
        self.assertIn("chunks", out)


if __name__ == "__main__":
    unittest.main()
