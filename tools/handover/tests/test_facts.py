# Copyright 2026 Ronny Trommer <ronny@no42.org>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for chunk facts, landed state, CLA status and the board. No network."""

import contextlib
import dataclasses
import io
import json
import unittest
from unittest import mock

import facts
import handover
import manifest
from tests.test_rebuild import CONTRIBUTOR, Base

PR_PATH = "repos/grafana/grafana-ansible-collection/"


def fake_gh(routes):
    calls = []

    def gh(args):
        calls.append(args)
        key = " ".join(args)
        for needle, body in routes.items():
            if needle in key:
                return body if isinstance(body, str) else json.dumps(body)
        raise AssertionError(f"unexpected gh call {args}")
    gh.calls = calls
    return gh


def pr_routes(n, sha, state, merged=False, authors=(), title="t", pr_state="open"):
    routes = {f"pulls/{n}/commits": [{"commit": {"author": {"name": a, "email": e}}}
                                     for a, e in authors],
              f"pulls/{n}": {"head": {"sha": sha}, "merged": merged, "title": title,
                              "state": pr_state},
              f"commits/{sha}/status": {"state": state or "pending",
                                        "statuses": [{"context": "license/cla", "state": state}]
                                        if state else []}}
    return routes


class TestGit(Base):
    def chunk(self, *chunks, carries=()):
        loaded = manifest.load(self.fx.manifest(*chunks), self.fx.work)
        chunks = tuple(dataclasses.replace(c, carries=tuple(carries)) for c in loaded.chunks)
        return dataclasses.replace(loaded, chunks=chunks)

    def test_chunk_facts_commits_files_and_size(self):
        self.t1(("a.txt", "x\ny\n", "add a", CONTRIBUTOR), ("shared", "one\n", "trim shared"))
        loaded = self.chunk(("T1", "a", None))
        got = facts.chunk_facts(loaded.chunks[0], self.fx.work, loaded)
        self.assertEqual([c["subject"] for c in got.commits], ["add a", "trim shared"])
        self.assertEqual(got.commits[0]["author"], "Jane Contributor")
        self.assertEqual(got.commits[0]["email"], "jane@example.net")
        self.assertEqual(sorted(got.files), ["a.txt", "shared"])
        self.assertEqual((got.insertions, got.deletions), (2, 2))

    def test_child_is_measured_against_its_parent(self):
        self.t1(("a.txt", "x\n", "t1 change"))
        self.fx.review_branch("review/t2-b", "origin/review/t1-a", ("b.txt", "y\n", "t2 change"))
        loaded = self.chunk(("T1", "a", None), ("T2", "b", "T1"))
        got = facts.chunk_facts(loaded.chunks[1], self.fx.work, loaded)
        self.assertEqual([c["subject"] for c in got.commits], ["t2 change"])
        self.assertEqual(got.files, ["b.txt"])

    def test_chunk_without_branch_is_empty_not_a_crash(self):
        loaded = self.chunk(("T1", "a", None))
        got = facts.chunk_facts(loaded.chunks[0], self.fx.work, loaded)
        self.assertEqual((got.commits, got.files, got.found), ([], [], False))

    def test_landed_by_patch_equivalence(self):
        self.t1(("a.txt", "x\n", "add a"))
        loaded = self.chunk(("T1", "a", None))
        self.assertFalse(facts.is_landed(loaded.chunks[0], self.fx.work, set(), loaded))
        self.fx.upstream_commit("a.txt", "x\n", "squash: add a")
        self.assertTrue(facts.is_landed(loaded.chunks[0], self.fx.work, set(), loaded))

    def test_not_landed_when_one_commit_missing(self):
        self.t1(("a.txt", "x\n", "add a"), ("b.txt", "y\n", "add b"))
        loaded = self.chunk(("T1", "a", None))
        self.fx.upstream_commit("a.txt", "x\n", "add a upstream")
        self.assertFalse(facts.is_landed(loaded.chunks[0], self.fx.work, set(), loaded))

    def test_landed_by_multi_commit_squash(self):
        self.t1(("a.txt", "x\n", "add a"), ("b.txt", "y\n", "add b"))
        loaded = self.chunk(("T1", "a", None))
        self.fx.commit(self.fx.up, "a.txt", "x\n", "squash part")
        self.fx.commit(self.fx.up, "b.txt", "y\n", "squash all")
        self.fx.git(self.fx.up, "reset", "-q", "--soft", "HEAD~2")
        self.fx.git(self.fx.up, "commit", "-q", "-m", "squash a and b")
        self.fx.git(self.fx.up, "push", "-q", "origin", "HEAD:main")
        self.fx.git(self.fx.work, "fetch", "-q", "upstream")
        self.assertTrue(facts.is_landed(loaded.chunks[0], self.fx.work, set(), loaded))

    def test_landed_by_merged_pr(self):
        loaded = self.chunk(("T1", "a", None), carries=(528, 529))
        chunk = loaded.chunks[0]
        self.assertFalse(facts.is_landed(chunk, self.fx.work, {528}, loaded))
        self.assertTrue(facts.is_landed(chunk, self.fx.work, {528, 529}, loaded))


class TestGh(unittest.TestCase):
    def test_cla_reads_license_cla_context(self):
        gh = fake_gh({**pr_routes(528, "a" * 40, "success"), **pr_routes(530, "b" * 40, None)})
        self.assertEqual(facts.cla_status(gh, [528, 530]), {528: "success", 530: "unknown"})

    def test_pr_facts_records_open_or_closed(self):
        gh = fake_gh({**pr_routes(528, "a" * 40, "success"),
                      **pr_routes(510, "b" * 40, "success", pr_state="closed")})
        got = facts.pr_facts(gh, [528, 510])
        self.assertEqual((got[528]["state"], got[510]["state"]), ("open", "closed"))

    def test_gh_wrapper_rejects_mutating_flags(self):
        for bad in (["api", "-X", "PATCH", PR_PATH + "issues/1"],
                    ["api", "--method", "POST", PR_PATH + "issues/1"],
                    ["api", PR_PATH + "issues/1", "-f", "state=open"],
                    ["api", PR_PATH + "issues/1", "--input", "x.json"]):
            with self.assertRaises(SystemExit):
                facts.real_gh(bad)

    def test_gh_wrapper_rejects_bundled_and_attached_flags(self):
        p = PR_PATH + "issues/540"
        for bad in (["api", p, "-XPATCH"], ["api", p, "-fa=b"], ["api", p, "-Fk=v"],
                    ["api", p, "--method=PATCH"], ["api", p, "-if"], ["api", p, "--input=x"],
                    ["api", PR_PATH + "../../user"], ["api", "graphql"],
                    ["api", p, "--paginate", "-XPATCH"], facts.BOARD_ARGS + ["--jq", "."]):
            with self.assertRaises(SystemExit, msg=bad):
                facts.real_gh(bad)

    def test_gh_wrapper_accepts_the_two_read_shapes(self):
        done = mock.Mock(returncode=0, stdout="{}", stderr="")
        for ok in (["api", PR_PATH + "pulls/1"], ["api", PR_PATH + "pulls/1", "--paginate"],
                   facts.BOARD_ARGS):
            with mock.patch.object(facts.subprocess, "run", return_value=done) as run:
                self.assertEqual(facts.real_gh(ok), "{}")
            run.assert_called_once()
            self.assertEqual(run.call_args[0][0], ["gh", *ok])

    def test_gh_wrapper_rejects_non_upstream_api_path(self):
        for bad in (["api", "repos/no42-org/grafana-ansible-collection/issues"],
                    ["api", "user"], ["issue", "list"],
                    ["project", "item-list", "5", "--owner", "no42-org"]):
            with self.assertRaises(SystemExit):
                facts.real_gh(bad)

    def test_author_cla_mapping(self):
        prs = {510: {"cla": "success", "merged": False, "title": "", "authors": []},
               528: {"cla": "failure", "merged": False, "title": "",
                     "authors": [("Jane", "jane@example.net")]}}
        self.assertEqual(facts.author_cla("Ronny Trommer", "other@x.org", prs), "success")
        self.assertEqual(facts.author_cla("Someone", "ronny@no42.org", prs), "success")
        self.assertEqual(facts.author_cla("dependabot[bot]", "d@x", prs), "bot")
        self.assertEqual(facts.author_cla("Jane", "JANE@example.net", prs), "failure")
        self.assertEqual(facts.author_cla("Stranger", "s@x.org", prs), "unknown")

    def test_board_truncation_fails(self):
        with self.assertRaises(facts.GhError):
            facts.board_rows(fake_gh({"project item-list": {"totalCount": 1001, "items": []}}))

    def test_board_title_prefix_stripped(self):
        items = [{"title": "[Issue #537] Datasource update 404", "upstream": 537, "kind": "Issue",
                  "fork decision": "Done", "epic": "grafana-api-modules",
                  "target release": "6.3.0"}]
        rows = facts.board_rows(fake_gh({"project item-list": {"totalCount": 1, "items": items}}))
        self.assertEqual(rows, [{"number": 537, "kind": "Issue", "title": "Datasource update 404",
                                 "decision": "Done", "epic": "grafana-api-modules",
                                 "target": "6.3.0"}])


class TestCli(Base):
    def test_facts_command_writes_json_and_sets_landed(self):
        self.t1(("a.txt", "x\n", "add a", CONTRIBUTOR))
        self.fx.upstream_commit("a.txt", "x\n", "squash")
        manifest_path = self.fx.manifest(("T1", "a", None), ("T2", "b", None))
        state_path = self.fx.root / "state.json"
        state_path.write_text(json.dumps({
            cid: {"rebase": "ok", "candidate": None, "base": None, "tests": "none"}
            for cid in ("T1", "T2")}))
        out_file = self.fx.root / "out" / "facts.json"
        gh = fake_gh({**pr_routes(510, "c" * 40, "success"),
                      "project item-list": {"totalCount": 0, "items": []}})
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = handover.main(["facts", "--manifest", str(manifest_path), "--repo",
                                  str(self.fx.work), "--state", str(state_path),
                                  "--out", str(out_file)], gh=gh)
        self.assertEqual(code, 0, out.getvalue())
        data = json.loads(out_file.read_text())
        self.assertEqual(data["upstream"], self.rev("upstream/main"))
        self.assertTrue(data["chunks"]["T1"]["landed"])
        self.assertEqual(data["chunks"]["T2"]["commits"], [])
        self.assertIn("T2", out.getvalue())
        self.assertEqual(data["chunks"]["T1"]["authors"],
                         [{"name": "Jane Contributor", "email": "jane@example.net",
                           "cla": "unknown"}])
        self.assertEqual(data["prs"]["510"]["cla"], "success")
        self.assertEqual(data["prs"]["510"]["state"], "open")
        self.assertTrue(json.loads(state_path.read_text())["T1"]["landed"])

    def test_failed_gh_call_fails_and_writes_nothing(self):
        manifest_path = self.fx.manifest(("T1", "a", None))
        state_path = self.fx.root / "state.json"
        state_path.write_text("{}")
        out_file = self.fx.root / "facts.json"

        def gh(args):
            raise facts.GhError("boom")
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = handover.main(["facts", "--manifest", str(manifest_path), "--repo",
                                  str(self.fx.work), "--state", str(state_path),
                                  "--out", str(out_file)], gh=gh)
        self.assertEqual(code, 1)
        self.assertIn("boom", out.getvalue())
        self.assertFalse(out_file.exists())
