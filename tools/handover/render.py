# Copyright 2026 Ronny Trommer <ronny@no42.org>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Render the handover page from the manifest, state.json and facts.json.

The page is one self-contained file. Commit subjects, author names and board
titles come from third parties, so every interpolated value goes through
`esc`. Nothing from the data is placed inside the page's one <script>; the
script reads chunk ids from data attributes on the cards.
"""

from __future__ import annotations

import html
import re
import string
from pathlib import Path

import manifest
from state import ChunkState

TEMPLATE = Path(__file__).resolve().parent / "template.html"
FORK_URL = "https://github.com/no42-org/grafana-ansible-collection"
UPSTREAM_URL = "https://github.com/grafana/grafana-ansible-collection"
GROUP_ORDER = ("carried", "fixes", "harness", "toolchain", "pinning", "removals", "docs")
GROUP_LABELS = {
    "carried": "Carried pull requests",
    "fixes": "Fixes",
    "harness": "Test harness",
    "toolchain": "Toolchain",
    "pinning": "Version pinning",
    "removals": "Removals",
    "docs": "Documentation",
}
CLA_LABELS = {"success": "CLA signed", "bot": "bot account", "unknown": "CLA unknown",
              "failure": "CLA not signed", "pending": "CLA pending", "error": "CLA check error"}


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def short(sha: str) -> str:
    return sha[:7]


def upstream_link(n: int) -> str:
    return f'<a href="{esc(UPSTREAM_URL)}/issues/{esc(n)}">#{esc(n)}</a>'


def prose(text: str) -> str:
    """Blank-line separated paragraphs. After escaping, `backticks` become <code>
    and #123 becomes a link to that upstream issue or pull request."""
    out = []
    for para in re.split(r"\n\s*\n", text.strip()):
        body = " ".join(line.strip() for line in para.splitlines() if line.strip())
        body = re.sub(r"(?<![\w&])#(\d+)\b", lambda m: upstream_link(int(m.group(1))), esc(body))
        body = re.sub(r"`([^`]+)`", r"<code>\1</code>", body)
        out.append(f"<p>{body}</p>")
    return "\n".join(out)


def status(chunk: manifest.Chunk, s: ChunkState | None, landed: bool) -> tuple[str, str]:
    """(css class, status line). Order: landed, behind, no tests, verified."""
    if landed or (s is not None and s.landed):
        return "landed", "landed upstream"
    behind = s is None or s.rebase in ("conflict", "parent-behind") or s.tests == "fail"
    if behind and s is not None and s.last_good:
        good = s.last_good
        return "behind", (f"behind upstream since {good['date']} "
                          f"(last applied to {short(good['upstream'])})")
    if behind:
        return "behind", "behind upstream (never verified)"
    if not chunk.tests:
        return "untested", "no tests of its own"
    if s.verified_at:
        v = s.verified_at
        return "verified", f"verified on upstream main at {short(v['upstream'])}, {v['date']}"
    return "behind", "behind upstream (never verified)"


def plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def cla_summary(loaded: manifest.Manifest, prs: dict) -> str:
    carried = sorted({n for c in loaded.chunks for n in c.carries})
    if not carried:
        return "<p>No upstream pull requests are carried.</p>"
    failing = [n for n in carried if prs.get(str(n), {}).get("cla") != "success"]
    if not failing:
        head = f"All {len(carried)} carried pull requests pass license/cla."
    else:
        listed = ", ".join(f"{upstream_link(n)} ({esc(prs.get(str(n), {}).get('cla', 'no data'))})"
                           for n in failing)
        head = (f"{len(carried) - len(failing)} of {len(carried)} carried pull requests "
                f"pass license/cla. Not passing: {listed}.")
    ronny = prs.get("510", {}).get("cla")
    tail = ""
    if ronny is not None:
        tail = (" Ronny Trommer's own commits are covered by the license/cla status of his "
                f"pull request {upstream_link(510)}, which is {esc(ronny)}.")
    return f"<p>{head}{tail} Each card lists its authors with their CLA status.</p>"


def intro(loaded: manifest.Manifest, facts: dict) -> str:
    roots = ", ".join(esc(c.id) for c in loaded.chunks if c.requires is None)
    fork_only = "\n".join(f"<li><strong>{esc(f.title)}.</strong> {esc(f.why)}</li>"
                          for f in loaded.fork_only)
    return f"""<section id="intro">
<h2>Why this fork exists</h2>
<p>For a long time nobody reviewed or merged changes in grafana/grafana-ansible-collection.
The fork kept fixing the roles and modules it depends on.
It also carried open upstream pull requests whose authors were still waiting for a review.
This page offers that work back, one chunk at a time.
Take what you want and leave the rest.</p>

<h2>How the work is cut</h2>
<p>Each chunk has one purpose: a fix, a test harness, a toolchain change, version pinning or a removal.
Contributor commits are kept whole, with their original authors.
Only Ronny's own commits were split, where one commit served two purposes.</p>

<h2>Dependency rule</h2>
<p>Chunks stack.
Chunks with no parent ({roots}) are cut directly from upstream main.
The test harness sits on the version pins, and a fix with tests stacks on the harness that runs them.
A card's <em>Requires</em> line names its parent.
Each branch is cut from its parent's branch, so when you fetch a chunk you get its parents too.</p>

<h2>Taking a chunk</h2>
<p>Every chunk has a branch named <code>review/&lt;id&gt;-&lt;slug&gt;</code>, and its card shows the command to fetch it.
The <code>review/*</code> branches are rebased onto upstream main and force-pushed on every rebuild.
Work on a local copy, for example <code>git switch -c my-branch FETCH_HEAD</code>, and do not build on the remote branch.</p>
<p>A branch moves only after it rebased cleanly and its tests passed on the rebased tree.
Each card says where it stands:</p>
<ul>
<li><em>verified on upstream main</em>: rebased and tested at that upstream commit.</li>
<li><em>behind upstream</em>: the last rebase or test run failed, so the branch still holds its last good state.</li>
<li><em>no tests of its own</em>: rebased cleanly, but nothing tests it, for example documentation.</li>
<li><em>landed upstream</em>: its content is already on upstream main.</li>
</ul>

<h2>Contributor License Agreement</h2>
{cla_summary(loaded, facts.get("prs", {}))}

<h2>Not offered</h2>
<p>These parts of the fork exist only for the fork and are not offered as chunks:</p>
<ul class="fork-only">
{fork_only}
</ul>

<h2>Marks</h2>
<p>The take, maybe and skip buttons and the note field on each card are for you alone.
They are kept in this browser's local storage and are never sent anywhere.</p>
</section>"""


def overview(loaded: manifest.Manifest, facts: dict) -> str:
    rows = []
    for group in GROUP_ORDER:
        n = sum(1 for c in loaded.chunks if c.group == group)
        if n:
            rows.append(f'<li><a href="#group-{group}">{esc(GROUP_LABELS[group])}</a> '
                        f'<span class="count">{n}</span></li>')
    missing = len(facts.get("unassigned", []))
    extra = ""
    if missing:
        extra = (f'<p class="warn">{plural(missing, "fork commit")} '
                 f'{"is" if missing == 1 else "are"} not yet assigned to any chunk.</p>')
    return f"""<section id="overview">
<h2>Overview</h2>
<p>{plural(len(loaded.chunks), "chunk")} in {len(rows)} groups.</p>
<ul class="groups">
{chr(10).join(rows)}
</ul>
<p id="progress" class="progress" hidden></p>
{extra}
</section>"""


def card(chunk: manifest.Chunk, s: ChunkState | None, f: dict, prs: dict) -> str:
    kind, line = status(chunk, s, bool(f.get("landed")))
    detail = ""
    if kind == "behind" and s is not None and s.reason:
        detail = f'<p class="status-detail">{esc(s.reason)}</p>'
    meta = [esc(chunk.id), esc(GROUP_LABELS[chunk.group])]
    if chunk.epic != "-":
        meta.append(esc(chunk.epic))
    facts_rows = []
    for label, numbers in (("Closes", chunk.closes), ("Carries", chunk.carries),
                           ("Supersedes", chunk.supersedes)):
        if numbers:
            facts_rows.append((label, ", ".join(upstream_link(n) for n in numbers)))
    if chunk.requires:
        facts_rows.append(("Requires", f'<a href="#card-{esc(chunk.requires)}">'
                                       f'{esc(chunk.requires)}</a>'))
    authors = f.get("authors", [])
    if authors:
        facts_rows.append(("Authors", ", ".join(
            f'{esc(a["name"])} <span class="cla cla-{esc(a["cla"])}">'
            f'{esc(CLA_LABELS.get(a["cla"], "CLA " + a["cla"]))}</span>' for a in authors)))
    commits, files = f.get("commits", []), f.get("files", [])
    if commits:
        size = (f'{plural(len(commits), "commit")}, {plural(len(files), "file")}, '
                f'+{esc(f.get("insertions", 0))} / −{esc(f.get("deletions", 0))}')
    else:
        size = "no commits recorded"
    facts_rows.append(("Size", size))
    dl = "\n".join(f"<dt>{label}</dt><dd>{value}</dd>" for label, value in facts_rows)
    open_prs = [n for n in chunk.carries if prs.get(str(n), {}).get("state") == "open"
                and not prs.get(str(n), {}).get("merged")]
    merge_note = ""
    if open_prs:
        many = len(open_prs) > 1
        prs_word = "pull requests" if many else "pull request"
        whose = "contributors'" if many else "contributor's"
        merge_note = (
            f'<p class="note">Merging the original upstream {prs_word} '
            f'{", ".join(upstream_link(n) for n in open_prs)} is the cleanest way to take this, '
            f"because it keeps the {whose} attribution and history. "
            "This branch holds the cherry-pick plus any fork follow-up.</p>")
    fold = ""
    if commits or files:
        commit_items = "\n".join(
            f'<li><code>{esc(short(c["sha"]))}</code> {esc(c["subject"])} '
            f'<span class="author">{esc(c["author"])}</span></li>' for c in commits)
        file_items = "\n".join(f"<li><code>{esc(p)}</code></li>" for p in files)
        fold = f"""<details>
<summary>Commits and files</summary>
<ol class="commits">
{commit_items}
</ol>
<ul class="files">
{file_items}
</ul>
</details>"""
    fetch = f"git fetch {FORK_URL} {chunk.branch}"
    cid = esc(chunk.id)
    return f"""<article class="card" id="card-{cid}" data-chunk="{cid}">
<header>
<p class="meta">{" · ".join(meta)}</p>
<h3>{esc(chunk.title)}</h3>
<p class="status status-{kind}">{esc(line)}</p>
{detail}
</header>
{prose(chunk.summary)}
{merge_note}
<dl>
{dl}
</dl>
{fold}
<pre class="fetch"><code>{esc(fetch)}</code></pre>
<div class="marks" hidden>
<div class="toggles" role="group" aria-label="Your mark for {cid}">
<button type="button" data-mark="take" aria-pressed="false">take</button>
<button type="button" data-mark="maybe" aria-pressed="false">maybe</button>
<button type="button" data-mark="skip" aria-pressed="false">skip</button>
</div>
<label>Note <textarea rows="2" aria-label="Note for {cid}"></textarea></label>
</div>
</article>"""


def groups(loaded: manifest.Manifest, states: dict, facts: dict) -> str:
    per, prs = facts.get("chunks", {}), facts.get("prs", {})
    out = []
    for group in GROUP_ORDER:
        members = [c for c in loaded.chunks if c.group == group]
        if not members:
            continue
        cards = "\n".join(card(c, states.get(c.id), per.get(c.id, {}), prs) for c in members)
        out.append(f'<section class="group" id="group-{group}">\n'
                   f"<h2>{esc(GROUP_LABELS[group])}</h2>\n{cards}\n</section>")
    return "\n".join(out)


def appendix(loaded: manifest.Manifest, facts: dict) -> str:
    addressed: dict[int, list[str]] = {}
    for c in loaded.chunks:
        for n in (*c.closes, *c.carries, *c.supersedes):
            addressed.setdefault(n, []).append(c.id)
    rows = []
    for row in sorted(facts.get("board", []), key=lambda r: int(r["number"])):
        n = int(row["number"])
        cards = ", ".join(f'<a href="#card-{esc(cid)}">{esc(cid)}</a>'
                          for cid in addressed.get(n, []))
        rows.append(f"<tr><td>{upstream_link(n)}</td><td>{esc(row['kind'])}</td>"
                    f"<td>{esc(row['title'])}</td><td>{esc(row['decision'])}</td>"
                    f"<td>{cards}</td></tr>")
    return f"""<section id="backlog">
<h2>Backlog appendix</h2>
<p>Every upstream issue and pull request on the fork's board, with the fork's decision and the card that addresses it.</p>
<div class="table">
<table>
<thead><tr><th>Upstream</th><th>Kind</th><th>Title</th><th>Fork decision</th><th>Card</th></tr></thead>
<tbody>
{chr(10).join(rows)}
</tbody>
</table>
</div>
</section>"""


def render(loaded: manifest.Manifest, states: dict[str, ChunkState], facts: dict,
           generated: str) -> str:
    stamp = f"generated {generated} against upstream main {short(facts.get('upstream', ''))}"
    return string.Template(TEMPLATE.read_text()).substitute(
        generated=esc(stamp), intro=intro(loaded, facts), overview=overview(loaded, facts),
        groups=groups(loaded, states, facts), appendix=appendix(loaded, facts))
