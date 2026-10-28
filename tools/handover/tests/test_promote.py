# Copyright 2026 Ronny Trommer <ronny@no42.org>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the test plan, the test runner and promotion, against throwaway remotes."""

import contextlib
import dataclasses
import io
import json
import tempfile
import unittest
from pathlib import Path

import handover
import manifest
import promote
from state import ChunkState
from tests.test_rebuild import Base

TODAY = "2026-10-28"


def with_tests(loaded, **goals):
    chunks = tuple(dataclasses.replace(c, tests=tuple(goals.get(c.id, c.tests)))
                   for c in loaded.chunks)
    return dataclasses.replace(loaded, chunks=chunks)


def st(rebase, **kw):
    fields = dict(candidate="c" * 40, base="b" * 40, tests="pending")
    fields.update(kw)
    return ChunkState(rebase, **fields)


class TestMatrix(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        from tests.gitfixture import Fixture
        fx = Fixture(Path(tmp.name))
        base = fx.git(fx.work, "rev-parse", "HEAD")
        self.loaded = manifest.load(fx.manifest(("T1", "a", None), ("T2", "b", "T1"),
                                                ("T3", "c", None), ("T4", "d", None),
                                                ("T5", "e", None)), fx.work)
        self.loaded = with_tests(self.loaded, T1=["ci-lint", "units"], T2=["sanity"],
                                 T3=["sanity"], T4=["sanity"], T5=["sanity"])
        self.base = base

    def test_matrix_skips_conflict_and_parent_behind(self):
        states = {"T1": st("ok"), "T2": st("parent-behind", candidate=None),
                  "T3": st("conflict", candidate=None), "T4": st("unchanged"),
                  "T5": st("ok")}
        got = promote.matrix(self.loaded, states)
        self.assertEqual(got, [
            {"chunk": "T1", "ref": "handover-candidate/t1-a", "goal": "ci-lint"},
            {"chunk": "T1", "ref": "handover-candidate/t1-a", "goal": "units"},
            {"chunk": "T5", "ref": "handover-candidate/t5-e", "goal": "sanity"},
        ])

    def test_landed_chunk_not_in_matrix_and_not_pushed(self):
        states = {"T1": st("ok", landed=True, tests="none"), "T2": st("ok"),
                  "T3": st("ok"), "T4": st("ok"), "T5": st("ok")}
        self.assertNotIn("T1", {e["chunk"] for e in promote.matrix(self.loaded, states)})


class TestRunTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        (self.dir / "Makefile").write_text(
            "ok:\n\t@echo $(X) > seen\nbad:\n\t@false\n")

    def chunk(self, *goals):
        return manifest.Chunk("T1", "a", "harness", "-", "t", "s", (), None,
                              (), (), (), tuple(goals))

    def test_missing_make_target_fails(self):
        self.assertFalse(promote.run_tests(self.chunk("module-test MODULE=x"), self.dir))

    def test_passing_goal_gets_its_arguments(self):
        self.assertTrue(promote.run_tests(self.chunk("ok X=hello"), self.dir))
        self.assertEqual((self.dir / "seen").read_text().strip(), "hello")

    def test_failing_goal_fails_and_stops(self):
        self.assertFalse(promote.run_tests(self.chunk("bad", "ok X=1"), self.dir))
        self.assertFalse((self.dir / "seen").exists())


class TestPromote(Base):
    def setUp(self):
        super().setUp()
        self.t1 = self.fx.review_branch("review/t1-a", self.base, ("t1", "t1\n", "t1 change"))
        self.t2 = self.fx.review_branch("review/t2-b", self.t1, ("t2", "t2\n", "t2 change"))
        self.fx.upstream_commit("other", "x\n", "upstream moves")
        self.git("fetch", "-q", "origin")

    def build(self, **goals):
        loaded = manifest.load(self.fx.manifest(("T1", "a", None), ("T2", "b", "T1")), self.fx.work)
        states, _ = self.run_rebuild(("T1", "a", None), ("T2", "b", "T1"))
        return with_tests(loaded, **goals), states

    def go(self, loaded, states, results):
        return promote.promote(loaded, states, results, TODAY, "u" * 40, repo=self.fx.work)

    def origin_tip(self, branch):
        return self.fx.git(self.fx.root, "--git-dir", str(self.fx.origin), "rev-parse", branch)

    def test_promote_requires_tests_and_parent(self):
        loaded, states = self.build(T1=["a"], T2=["b"])
        out = self.go(loaded, states, {"T1": False, "T2": True})
        self.assertEqual((out["T1"].tests, out["T1"].promoted), ("fail", False))
        self.assertEqual((out["T2"].tests, out["T2"].promoted), ("pass", False))
        self.assertEqual(self.origin_tip("review/t1-a"), self.t1)
        self.assertEqual(self.origin_tip("review/t2-b"), self.t2)

    def test_promote_pushes_and_records_verification(self):
        loaded, states = self.build(T1=["a"], T2=["b"])
        out = self.go(loaded, states, {"T1": True, "T2": True})
        self.assertTrue(out["T1"].promoted and out["T2"].promoted)
        self.assertEqual(self.origin_tip("review/t1-a"), out["T1"].candidate)
        want = {"upstream": "u" * 40, "date": TODAY}
        self.assertEqual(out["T2"].verified_at, want)
        self.assertEqual(out["T2"].last_good, want)

    def test_no_tests_promotes_without_verified_at(self):
        loaded, states = self.build()
        states["T1"].last_good = {"upstream": "o" * 40, "date": "2026-01-01"}
        out = self.go(loaded, states, {})
        self.assertTrue(out["T1"].promoted)
        self.assertEqual(out["T1"].tests, "none")
        self.assertIsNone(out["T1"].verified_at)
        self.assertEqual(out["T1"].last_good["date"], "2026-01-01")

    def test_missing_result_file_is_failure(self):
        loaded, states = self.build(T1=["a"])
        out = self.go(loaded, states, {})
        self.assertEqual((out["T1"].tests, out["T1"].promoted), ("fail", False))

    def test_failed_chunk_keeps_last_good(self):
        loaded, states = self.build(T1=["a"])
        states["T1"].last_good = {"upstream": "o" * 40, "date": "2026-01-01"}
        out = self.go(loaded, states, {"T1": False})
        self.assertEqual(out["T1"].last_good["date"], "2026-01-01")

    def test_force_with_lease_refuses_moved_remote(self):
        loaded, states = self.build(T1=["a"], T2=["b"])
        # Someone moves origin's T2 branch after the rebuild; T1 stays put.
        self.fx.git(self.fx.work, "checkout", "-q", "--detach", self.t2)
        self.fx.commit(self.fx.work, "late", "late\n", "late push")
        self.git("push", "-q", "origin", "HEAD:refs/heads/review/t2-b")
        self.git("checkout", "-q", "main")
        # Forget the push locally: this is another clone's push, unseen since the rebuild.
        self.git("update-ref", "refs/remotes/origin/review/t2-b", self.t2)
        moved = self.origin_tip("review/t2-b")
        out = self.go(loaded, states, {"T1": True, "T2": True})
        self.assertTrue(out["T1"].promoted)
        self.assertFalse(out["T2"].promoted)
        self.assertEqual(self.origin_tip("review/t2-b"), moved)

    def test_candidates_deleted_after_promote(self):
        loaded, states = self.build()
        self.git("push", "-q", "origin", f"{states['T1'].candidate}:refs/heads/handover-candidate/t1-a")
        self.go(loaded, states, {})
        heads = self.git("ls-remote", "--heads", "origin", "handover-candidate/*")
        self.assertEqual(heads, "")

    def test_landed_chunk_not_in_matrix_and_not_pushed(self):
        loaded, states = self.build()
        states["T1"] = st("ok", candidate=self.t1, tests="none", landed=True)
        states["T2"] = st("unchanged", candidate=self.t2)
        out = self.go(loaded, states, {})
        self.assertFalse(out["T1"].promoted)
        self.assertEqual(self.origin_tip("review/t1-a"), self.t1)
        self.assertEqual(promote.matrix(loaded, states), [])

    def test_child_of_landed_or_unchanged_parent_is_promotable(self):
        for parent in (st("ok", landed=True, tests="none"), st("unchanged")):
            with self.subTest(parent=parent.rebase):
                loaded, states = self.build(T2=["b"])
                states["T1"] = dataclasses.replace(parent, candidate=self.t1)
                out = self.go(loaded, states, {"T2": True})
                self.assertTrue(out["T2"].promoted)
                self.assertFalse(out["T1"].promoted)
                self.fx.review_branch("review/t2-b", self.t1, ("t2", "t2\n", "t2 change"))
                self.git("fetch", "-q", "origin")

    def test_unchanged_chunk_is_not_pushed_or_retested(self):
        loaded, states = self.build(T1=["a"])
        states["T1"] = st("unchanged", candidate=self.t1, tests="pass",
                          verified_at={"upstream": "o" * 40, "date": "2026-01-01"})
        out = self.go(loaded, states, {})
        self.assertEqual(out["T1"].verified_at["date"], "2026-01-01")
        self.assertEqual(out["T1"].tests, "pass")

    def test_refuses_upstream_origin(self):
        loaded, states = self.build()
        self.git("remote", "set-url", "origin", "https://github.com/grafana/grafana-ansible-collection")
        with self.assertRaises(SystemExit):
            self.go(loaded, states, {})


class TestAssertNotUpstream(unittest.TestCase):
    def test_refuses_upstream_url(self):
        for url in ("https://github.com/grafana/grafana-ansible-collection",
                    "https://github.com/grafana/grafana-ansible-collection.git",
                    "git@github.com:Grafana/grafana-ansible-collection.git"):
            with self.subTest(url=url), self.assertRaises(SystemExit):
                promote.assert_not_upstream(url)

    def test_allows_the_fork(self):
        promote.assert_not_upstream("https://github.com/no42-org/grafana-ansible-collection")


class TestCli(Base):
    def test_matrix_and_promote_cli(self):
        t1 = self.t1()
        self.fx.upstream_commit("other", "x\n", "upstream moves")
        self.git("fetch", "-q", "origin")
        code, _, state_file = self.run_cli(("T1", "a", None))
        self.assertEqual(code, 0)
        path = self.fx.manifest(("T1", "a", None))
        common = ["--manifest", str(path), "--repo", str(self.fx.work), "--state", str(state_file)]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(handover.main(["matrix", *common]), 0)
        self.assertEqual(json.loads(out.getvalue()), {"include": []})
        results = self.fx.root / "results"
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(handover.main(["promote", *common, "--results", str(results)]), 0)
        saved = json.loads(state_file.read_text())
        self.assertTrue(saved["T1"]["promoted"])
        self.assertNotEqual(self.fx.git(self.fx.root, "--git-dir", str(self.fx.origin),
                                        "rev-parse", "review/t1-a"), t1)

    def test_test_subcommand_writes_result(self):
        (self.fx.work / "Makefile").write_text("bad:\n\t@false\n")
        path = self.fx.manifest(("T1", "a", None))
        text = path.read_text().replace("tests: []", "tests: [units]")
        path.write_text(text)
        results = self.fx.root / "results"
        (self.fx.work / "Makefile").write_text("units:\n\t@true\n")
        with contextlib.redirect_stdout(io.StringIO()):
            code = handover.main(["test", "--manifest", str(path), "--repo", str(self.fx.work),
                                  "--results", str(results), "--chunk", "T1"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads((results / "T1.json").read_text()),
                         {"chunk": "T1", "passed": True})
