# Copyright 2026 Ronny Trommer <ronny@no42.org>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for rebuilding handover candidates, against throwaway remotes."""

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import handover
import manifest
import rebuild
import state
from tests.gitfixture import Fixture

CONTRIBUTOR = ("Jane Contributor", "jane@example.net")


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.fx = Fixture(Path(tmp.name))
        patcher = mock.patch.dict(os.environ, self.fx.env)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.base = self.rev("upstream/main")

    def rev(self, ref):
        return self.fx.git(self.fx.work, "rev-parse", ref)

    def git(self, *args):
        return self.fx.git(self.fx.work, *args)

    def run_rebuild(self, *chunks):
        loaded = manifest.load(self.fx.manifest(*chunks), self.fx.work)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            result = rebuild.rebuild(loaded, self.fx.work)
        return result, out.getvalue()

    def run_cli(self, *chunks, extra=()):
        path = self.fx.manifest(*chunks)
        out_file = self.fx.root / "out" / "state.json"
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = handover.main(["rebuild", "--manifest", str(path), "--repo", str(self.fx.work),
                                  "--out", str(out_file), *extra])
        return code, out.getvalue(), out_file

    def t1(self, *commits):
        return self.fx.review_branch("review/t1-a", self.base,
                                     *(commits or [("t1", "t1\n", "t1 change")]))


class TestRebuild(Base):
    def test_root_chunk_rebases_onto_new_upstream(self):
        self.t1()
        new = self.fx.upstream_commit("up", "up\n", "upstream moves")
        result, _ = self.run_rebuild(("T1", "a", None))
        t1 = result["T1"]
        self.assertEqual(t1.rebase, "ok")
        self.assertEqual(t1.base, new)
        self.assertEqual(t1.tests, "pending")
        self.assertEqual(self.rev("handover-candidate/t1-a"), t1.candidate)
        self.assertEqual(self.rev(f"{t1.candidate}^"), new)

    def test_child_stacks_on_parent_candidate(self):
        t1_tip = self.t1(("t1", "t1\n", "t1 one"), ("t1b", "t1b\n", "t1 two"))
        self.fx.review_branch("review/f1-b", t1_tip, ("f1", "f1\n", "f1 change"))
        self.fx.upstream_commit("up", "up\n", "upstream moves")
        result, _ = self.run_rebuild(("T1", "a", None), ("F1", "b", "T1"))
        self.assertEqual(result["F1"].rebase, "ok")
        self.assertEqual(result["F1"].base, result["T1"].candidate)
        self.git("merge-base", "--is-ancestor", result["T1"].candidate, result["F1"].candidate)
        subjects = self.git("log", "--format=%s", f"upstream/main..{result['F1'].candidate}")
        self.assertEqual(sorted(subjects.splitlines()), ["f1 change", "t1 one", "t1 two"])

    def test_unchanged_when_base_did_not_move(self):
        t1_tip = self.t1()
        f1_tip = self.fx.review_branch("review/f1-b", t1_tip, ("f1", "f1\n", "f1 change"))
        result, _ = self.run_rebuild(("T1", "a", None), ("F1", "b", "T1"))
        self.assertEqual(result["T1"].rebase, "unchanged")
        self.assertEqual(result["T1"].candidate, t1_tip)
        self.assertEqual(result["T1"].base, self.base)
        self.assertEqual(result["F1"].rebase, "unchanged")
        self.assertEqual(result["F1"].candidate, f1_tip)
        self.assertEqual(result["F1"].base, t1_tip)
        self.assertEqual(self.rev("handover-candidate/t1-a"), t1_tip)

    def test_conflict_is_aborted_and_tree_clean(self):
        self.t1(("shared", "one\nfork\nthree\n", "fork edits two"))
        self.fx.upstream_commit("shared", "one\nupstream\nthree\n", "upstream edits two")
        result, out = self.run_rebuild(("T1", "a", None))
        self.assertEqual(result["T1"].rebase, "conflict")
        self.assertIsNone(result["T1"].candidate)
        self.assertEqual(result["T1"].tests, "none")
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertFalse((self.fx.work / ".git" / "rebase-merge").exists())
        self.assertFalse((self.fx.work / ".git" / "rebase-apply").exists())
        self.assertIn("T1", out)

    def test_child_of_conflict_is_parent_behind(self):
        t1_tip = self.t1(("shared", "one\nfork\nthree\n", "fork edits two"))
        f1_tip = self.fx.review_branch("review/f1-b", t1_tip, ("f1", "f1\n", "f1 change"))
        self.fx.review_branch("review/f2-c", f1_tip, ("f2", "f2\n", "f2 change"))
        self.fx.review_branch("review/u1-d", self.base, ("u1", "u1\n", "u1 change"))
        self.fx.upstream_commit("shared", "one\nupstream\nthree\n", "upstream edits two")
        result, _ = self.run_rebuild(("T1", "a", None), ("F1", "b", "T1"), ("F2", "c", "F1"),
                                     ("U1", "d", None))
        self.assertEqual(result["T1"].rebase, "conflict")
        self.assertEqual(result["F1"].rebase, "parent-behind")
        self.assertEqual(result["F2"].rebase, "parent-behind")
        self.assertIsNone(result["F2"].candidate)
        self.assertEqual(result["F1"].base, t1_tip)
        self.assertEqual(result["U1"].rebase, "ok")

    def test_missing_origin_branch_is_conflict(self):
        self.fx.review_branch("review/f1-b", self.base, ("f1", "f1\n", "f1 change"))
        result, out = self.run_rebuild(("T1", "a", None), ("F1", "b", "T1"))
        self.assertEqual(result["T1"].rebase, "conflict")
        self.assertIn("no origin branch", out)
        self.assertEqual(result["F1"].rebase, "parent-behind")

    def test_authors_preserved(self):
        self.t1(("t1", "t1\n", "contributed", CONTRIBUTOR))
        self.fx.upstream_commit("up", "up\n", "upstream moves")
        result, _ = self.run_rebuild(("T1", "a", None))
        self.assertEqual(result["T1"].rebase, "ok")
        author = self.git("log", "-1", "--format=%an|%ae", result["T1"].candidate)
        self.assertEqual(author, "|".join(CONTRIBUTOR))

    def test_restores_checked_out_branch(self):
        self.t1()
        self.git("checkout", "-q", "-b", "elsewhere")
        self.fx.upstream_commit("up", "up\n", "upstream moves")
        self.run_rebuild(("T1", "a", None))
        self.assertEqual(self.git("symbolic-ref", "--short", "HEAD"), "elsewhere")

    def test_rerun_while_on_candidate_branch(self):
        self.t1()
        self.fx.upstream_commit("up", "up\n", "upstream moves")
        self.run_rebuild(("T1", "a", None))
        self.git("checkout", "-q", "handover-candidate/t1-a")
        result, _ = self.run_rebuild(("T1", "a", None))
        self.assertEqual(result["T1"].rebase, "ok")
        self.assertEqual(self.git("symbolic-ref", "--short", "HEAD"), "handover-candidate/t1-a")


class TestCli(Base):
    def test_exit_code_after_processing_all(self):
        self.t1(("shared", "one\nfork\nthree\n", "fork edits two"))
        t2_tip = self.fx.review_branch("review/t2-b", self.base, ("t2", "t2\n", "t2 change"))
        self.fx.review_branch("review/f1-c", t2_tip, ("f1", "f1\n", "f1 change"))
        self.fx.upstream_commit("shared", "one\nupstream\nthree\n", "upstream edits two")
        code, out, out_file = self.run_cli(("T1", "a", None), ("T2", "b", None), ("F1", "c", "T2"))
        self.assertEqual(code, 1, out)
        saved = json.loads(out_file.read_text())
        self.assertEqual({k: v["rebase"] for k, v in saved.items()},
                         {"T1": "conflict", "T2": "ok", "F1": "ok"})
        self.assertEqual(len([line for line in out.splitlines() if line[:2] in saved]), 3)
        self.assertEqual(saved["T2"]["promoted"], False)
        self.assertEqual(saved["T2"]["landed"], False)
        self.assertIsNone(saved["T2"]["last_good"])

    def test_clean_run_exits_zero(self):
        self.t1()
        code, out, out_file = self.run_cli(("T1", "a", None))
        self.assertEqual(code, 0, out)
        self.assertEqual(state.load(out_file)["T1"].rebase, "unchanged")

    def test_dirty_tree_refused(self):
        self.t1()
        (self.fx.work / "shared").write_text("dirty\n")
        code, out, out_file = self.run_cli(("T1", "a", None))
        self.assertEqual(code, 2)
        self.assertIn("dirty", out)
        self.assertFalse(out_file.exists())
        self.assertEqual(self.git("symbolic-ref", "--short", "HEAD"), "main")

    def test_previous_state_carried_forward(self):
        self.t1()
        self.fx.review_branch("review/t2-b", self.base, ("t2", "t2\n", "t2 change"))
        good = {"upstream": self.base, "date": "2026-10-01"}
        previous = self.fx.root / "previous.json"
        previous.write_text(json.dumps({"T1": {
            "rebase": "ok", "candidate": None, "base": self.base, "tests": "pass",
            "promoted": True, "verified_at": good, "last_good": good, "landed": False}}))
        code, out, out_file = self.run_cli(("T1", "a", None), ("T2", "b", None),
                                           extra=("--previous", str(previous)))
        self.assertEqual(code, 0, out)
        saved = state.load(out_file)
        self.assertEqual(saved["T1"].verified_at, good)
        self.assertEqual(saved["T1"].last_good, good)
        self.assertFalse(saved["T1"].promoted)
        self.assertIsNone(saved["T2"].last_good)
        missing = self.fx.root / "absent.json"
        code, out, out_file = self.run_cli(("T1", "a", None), extra=("--previous", str(missing)))
        self.assertEqual(code, 0, out)
        self.assertIsNone(state.load(out_file)["T1"].last_good)


class TestState(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sub" / "state.json"
            states = {"T1": state.ChunkState(rebase="ok", candidate="a" * 40, base="b" * 40,
                                             tests="pending")}
            state.save(path, states)
            self.assertEqual(state.load(path), states)
            self.assertEqual(list(json.loads(path.read_text())["T1"]),
                             ["rebase", "candidate", "base", "tests", "promoted",
                              "verified_at", "last_good", "landed"])


if __name__ == "__main__":
    unittest.main()
