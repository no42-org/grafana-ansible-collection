# Copyright 2026 Ronny Trommer <ronny@no42.org>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the rendered handover page. Fixtures are plain dicts; no git, no network."""

import contextlib
import io
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import handover
import render
from manifest import Chunk, ForkOnly, Manifest
from state import ChunkState

UP = "a" * 40
OLD = "b" * 40


def chunk(cid, group="fixes", tests=("role-test ROLE=loki DISTRO=debian",), requires=None,
          closes=(), carries=(), supersedes=(), title=None, summary="One.\n\nTwo `x`."):
    return Chunk(id=cid, slug=f"{cid.lower()}-slug", group=group, epic="cross-role",
                 title=title or f"Title {cid}", summary=summary, commits=(),
                 requires=requires, closes=tuple(closes), carries=tuple(carries),
                 supersedes=tuple(supersedes), tests=tuple(tests))


def st(rebase="ok", tests="pass", **kw):
    return ChunkState(rebase, candidate=None, base=UP, tests=tests, **kw)


def facts_for(chunks, board=(), prs=None, subject="subject", unassigned=()):
    per = {}
    for c in chunks:
        per[c.id] = {"commits": [{"sha": "c" * 40, "subject": subject, "author": "Jane",
                                  "email": "jane@example.net"}],
                     "files": ["roles/x/tasks/main.yml"], "insertions": 3, "deletions": 1,
                     "landed": False,
                     "authors": [{"name": "Jane", "email": "jane@example.net",
                                  "cla": "success"}]}
    return {"generated": "2026-10-28", "upstream": UP, "unassigned": list(unassigned),
            "chunks": per, "prs": prs or {}, "board": list(board)}


FORK_ONLY = (ForkOnly("Namespace rename at build time", "Publishes indigo423.grafana.", ()),)


def page(chunks, states=None, **facts_kw):
    m = Manifest(tuple(chunks), FORK_ONLY)
    states = states if states is not None else {c.id: st() for c in chunks}
    return render.render(m, states, facts_for(chunks, **facts_kw), "2026-10-28")


class TestRender(unittest.TestCase):
    def test_escapes_untrusted_text(self):
        board = [{"number": 9, "kind": "Issue", "title": "<script>alert(1)</script>",
                  "decision": "Untriaged", "epic": "-", "target": "-"}]
        out = page([chunk("F1")], board=board, subject='a & b < c > d "q"')
        self.assertNotIn("<script>alert(1)", out)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", out)
        self.assertIn("a &amp; b &lt; c &gt; d &quot;q&quot;", out)
        self.assertNotIn('a & b < c > d "q"', out)

    def test_script_json_cannot_close_tag(self):
        evil = 'x</script><script>alert(1)</script>'
        out = page([chunk("F1", title=evil)],
                   board=[{"number": 5, "kind": "PR", "title": evil, "decision": "-",
                           "epic": "-", "target": "-"}])
        self.assertNotIn("</script><script>alert(1)", out)
        self.assertEqual(out.count("<script"), 1)
        self.assertEqual(out.count("</script>"), 1)

    def test_status_lines(self):
        chunks = [chunk("F1"), chunk("F2"), chunk("F3"), chunk("D1", group="docs", tests=())]
        states = {
            "F1": st(verified_at={"upstream": UP, "date": "2026-10-27"},
                     last_good={"upstream": UP, "date": "2026-10-27"}, promoted=True),
            "F2": st("conflict", "pending", last_good={"upstream": OLD, "date": "2026-10-01"},
                     verified_at={"upstream": OLD, "date": "2026-10-01"}),
            "F3": st(landed=True, tests="none"),
            "D1": st(tests="none", promoted=True),
        }
        out = page(chunks, states)
        self.assertIn("verified on upstream main at aaaaaaa, 2026-10-27", out)
        self.assertIn("behind upstream since 2026-10-01 (last applied to bbbbbbb)", out)
        self.assertIn("landed upstream", out)
        self.assertIn("no tests of its own", out)

    def test_behind_without_history_and_failed_tests(self):
        chunks = [chunk("F1"), chunk("F2", requires="F1"), chunk("F3")]
        states = {
            "F1": st(tests="fail", last_good={"upstream": OLD, "date": "2026-10-01"},
                     verified_at={"upstream": OLD, "date": "2026-10-01"}),
            "F2": st("parent-behind", "pending"),
            "F3": st(tests="pending"),
        }
        out = page(chunks, states)
        cards = out[out.index('id="group-fixes"'):]
        self.assertIn("behind upstream since 2026-10-01 (last applied to bbbbbbb)", cards)
        self.assertEqual(cards.count("behind upstream (never verified)"), 2)
        self.assertNotIn("verified on upstream main", cards)

    def test_rebased_but_not_promoted_is_behind(self):
        good = {"upstream": OLD, "date": "2026-10-01"}
        chunks = [chunk("F1"), chunk("F2"), chunk("D1", group="docs", tests=()),
                  chunk("U1"), chunk("U2", tests=())]
        states = {
            # Tests passed but the push was refused: the old branch stands.
            "F1": st(verified_at=good, last_good=good),
            "F2": st(tests="pass"),
            "D1": st(tests="none"),
            # Unchanged chunks keep their status: the branch is what was published.
            "U1": st("unchanged", verified_at=good, last_good=good),
            "U2": st("unchanged", tests="none"),
        }
        out = page(chunks, states)

        def line(cid):
            card = out[out.index(f'id="card-{cid}"'):]
            return re.search(r'<p class="status [^"]*">([^<]*)</p>', card).group(1)
        self.assertEqual(line("F1"), "behind upstream since 2026-10-01 (last applied to bbbbbbb)")
        self.assertEqual(line("F2"), "behind upstream (never verified)")
        self.assertEqual(line("D1"), "behind upstream (never verified)")
        self.assertEqual(line("U1"), "verified on upstream main at bbbbbbb, 2026-10-01")
        self.assertEqual(line("U2"), "no tests of its own")

    def test_failure_reason_shown_escaped(self):
        chunks = [chunk("F1"), chunk("F2")]
        states = {"F1": st("conflict", "none", reason="rebase failed: fatal: <bad> & co"),
                  "F2": st(promoted=True, verified_at={"upstream": UP, "date": "2026-10-27"},
                           reason="stale")}
        out = page(chunks, states)
        self.assertIn('<p class="status-detail">rebase failed: fatal: &lt;bad&gt; &amp; co</p>',
                      out)
        self.assertNotIn("<bad>", out)
        self.assertNotIn("stale", out)

    def test_landed_from_facts(self):
        chunks = [chunk("F1")]
        m = Manifest(tuple(chunks), FORK_ONLY)
        facts = facts_for(chunks)
        facts["chunks"]["F1"]["landed"] = True
        out = render.render(m, {"F1": st()}, facts, "2026-10-28")
        self.assertIn("landed upstream", out)

    def test_fork_only_listed_and_not_carded(self):
        out = page([chunk("F1")])
        self.assertIn("Namespace rename at build time", out)
        self.assertIn("Publishes indigo423.grafana.", out)
        self.assertEqual(len(re.findall(r'<article class="card"', out)), 1)
        self.assertIn('id="card-F1"', out)

    def test_appendix_links_to_card(self):
        board = [{"number": 537, "kind": "Issue", "title": "PUT removed", "decision": "Fix here",
                  "epic": "grafana-api-modules", "target": "6.3.0"},
                 {"number": 100, "kind": "Issue", "title": "Untouched", "decision": "Untriaged",
                  "epic": "-", "target": "-"}]
        out = page([chunk("F7", closes=[537])], board=board)
        appendix = out[out.index('id="backlog"'):]
        rows = re.findall(r"<tr>.*?</tr>", appendix, re.S)
        row537 = next(r for r in rows if "PUT removed" in r)
        row100 = next(r for r in rows if "Untouched" in r)
        self.assertIn('href="#card-F7"', row537)
        self.assertNotIn("#card-", row100)
        self.assertLess(appendix.index("Untouched"), appendix.index("PUT removed"))
        self.assertIn("https://github.com/grafana/grafana-ansible-collection/issues/537", row537)
        self.assertNotIn("6.3.0", appendix)

    def test_card_fields(self):
        chunks = [chunk("T1", group="harness"),
                  chunk("C1", group="carried", requires="T1", carries=[475], closes=[12],
                        supersedes=[13])]
        out = page(chunks, prs={"475": {"cla": "success", "merged": False, "title": "t"}})
        card = out[out.index('id="card-C1"'):]
        self.assertIn('href="#card-T1"', card)
        for n in (475, 12, 13):
            self.assertIn(f"https://github.com/grafana/grafana-ansible-collection/issues/{n}",
                          card)
        self.assertIn("git fetch https://github.com/no42-org/grafana-ansible-collection "
                      "review/c1-c1-slug", card)
        self.assertIn("<p>Two <code>x</code>.</p>", card)
        linked = page([chunk("F1", summary="Fixes #42, isn't it.")])
        self.assertIn('Fixes <a href="https://github.com/grafana/grafana-ansible-collection/'
                      'issues/42">#42</a>, isn&#x27;t it.', linked)
        self.assertIn("1 commit", card)
        self.assertIn("<details", card)
        self.assertIn('data-chunk="C1"', card)

    def test_open_carried_pr_gets_merge_note(self):
        chunks = [chunk("C1", group="carried", carries=[448]),
                  chunk("C2", group="carried", carries=[510])]
        prs = {"448": {"cla": "success", "merged": False, "state": "open", "title": "t"},
               "510": {"cla": "success", "merged": False, "state": "closed", "title": "t"}}
        out = page(chunks, prs=prs)
        note = ("Merging the original upstream pull request "
                '<a href="https://github.com/grafana/grafana-ansible-collection/issues/448">#448'
                "</a> is the cleanest way to take this, because it keeps the contributor's "
                "attribution and history. This branch holds the cherry-pick plus any fork "
                "follow-up.")
        c1 = out[out.index('id="card-C1"'):out.index('id="card-C2"')]
        c2 = out[out.index('id="card-C2"'):]
        self.assertIn(note, c1)
        self.assertNotIn("cleanest way", c2)
        two = page([chunk("C1", group="carried", carries=[448, 449])],
                   prs={"448": prs["448"], "449": prs["448"]})
        self.assertIn("pull requests <a", two)
        self.assertIn("keeps the contributors' attribution", two)

    def test_intro_names_root_chunks(self):
        chunks = [chunk("P1", group="pinning", tests=()),
                  chunk("T1", group="harness", requires="P1"),
                  chunk("F9")]
        out = page(chunks)
        self.assertIn("Chunks with no parent (P1, F9) are cut directly from upstream main.", out)
        self.assertNotIn("sits at the root", out)

    def test_cla_summary(self):
        chunks = [chunk("C1", carries=[475]), chunk("C2", carries=[461])]
        ok = {"475": {"cla": "success", "merged": False, "title": "t"},
              "461": {"cla": "success", "merged": False, "title": "t"}}
        self.assertIn("All 2 carried pull requests pass license/cla", page(chunks, prs=ok))
        bad = dict(ok, **{"461": {"cla": "pending", "merged": False, "title": "t"}})
        out = page(chunks, prs=bad)
        self.assertIn("1 of 2 carried pull requests pass license/cla", out)
        self.assertIn("#461", out)

    def test_overview_counts_and_unassigned(self):
        chunks = [chunk("F1"), chunk("F2"), chunk("T1", group="harness")]
        out = page(chunks)
        self.assertNotIn("not yet assigned", out)
        out = page(chunks, unassigned=["d" * 40, "e" * 40])
        self.assertIn("2 fork commits are not yet assigned to any chunk", out)
        self.assertIn("generated 2026-10-28 against upstream main aaaaaaa", out)
        self.assertLess(out.index('id="group-fixes"'), out.index('id="group-harness"'))
        self.assertNotIn('id="group-docs"', out)

    def test_no_external_urls_loaded(self):
        out = page([chunk("F1")])
        for needle in ("<script src", '<link rel="stylesheet"', "fetch(", "XMLHttpRequest",
                       "@import", "<iframe", "<img"):
            self.assertNotIn(needle, out)

    def test_storage_access_guarded(self):
        out = page([chunk("F1")])
        self.assertEqual(out.count("localStorage"), 1)
        at = out.index("localStorage")
        before = out[:at]
        self.assertGreater(before.rfind("try {"), before.rfind("}"))
        self.assertIn("catch", out[at:at + 400])

    def test_no_feedback_feature(self):
        out = page([chunk("F1")])
        for needle in ("clipboard", "mailto:", "<form", "action="):
            self.assertNotIn(needle, out)

    def test_starts_with_spdx_comment(self):
        self.assertIn("SPDX-License-Identifier: GPL-3.0-or-later", page([chunk("F1")])[:300])


class TestCommand(unittest.TestCase):
    def run_cmd(self, *argv):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            code = handover.main(list(argv))
        return code, err.getvalue()

    def test_missing_inputs_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            code, err = self.run_cmd("render", "--state", str(tmp / "state.json"),
                                     "--facts", str(tmp / "facts.json"),
                                     "--out", str(tmp / "site"))
            self.assertEqual(code, 2)
            self.assertIn("state.json", err)

    def test_writes_index_and_copies_state(self):
        chunks = [chunk("F1")]
        m = Manifest(tuple(chunks), FORK_ONLY)
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "state.json").write_text(json.dumps(
                {"F1": {"rebase": "ok", "candidate": None, "base": UP, "tests": "pass"}}))
            (tmp / "facts.json").write_text(json.dumps(facts_for(chunks)))
            with mock.patch("manifest.load", return_value=m):
                code, err = self.run_cmd("render", "--state", str(tmp / "state.json"),
                                         "--facts", str(tmp / "facts.json"),
                                         "--out", str(tmp / "site"))
            self.assertEqual(code, 0, err)
            self.assertIn('id="card-F1"', (tmp / "site/index.html").read_text())
            self.assertEqual((tmp / "site/state.json").read_text(),
                             (tmp / "state.json").read_text())


if __name__ == "__main__":
    unittest.main()
