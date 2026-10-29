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
STATUS_LABELS = {"verified": "verified", "behind": "behind upstream",
                 "untested": "no tests", "landed": "landed"}
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
    # A rebased chunk that was not promoted still has its old review branch.
    behind = (s is None or s.rebase in ("conflict", "parent-behind") or s.tests == "fail"
              or (s.rebase == "ok" and not s.promoted))
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


class Tree:
    """The chunks as the stack they form: each has at most one parent."""

    def __init__(self, loaded: manifest.Manifest):
        self.children: dict[str | None, list[str]] = {}
        parent = {}
        for c in loaded.chunks:
            self.children.setdefault(c.requires, []).append(c.id)
            parent[c.id] = c.requires
        self.ancestors: dict[str, list[str]] = {}
        for c in loaded.chunks:
            chain, up = [], parent[c.id]
            while up is not None:
                chain.insert(0, up)
                up = parent[up]
            self.ancestors[c.id] = chain
        self.order: list[str] = []
        self._walk(None)

    def _walk(self, parent: str | None) -> None:
        for cid in self.children.get(parent, []):
            self.order.append(cid)
            self._walk(cid)

    def outline(self, label, parent: str | None = None) -> str:
        """Nested lists, one node per chunk; `label(cid)` gives the node's inner HTML."""
        items = []
        for cid in self.children.get(parent, []):
            items.append(f"<li>{label(cid)}{self.outline(label, cid)}</li>")
        return f"<ul>{''.join(items)}</ul>" if items else ""


def card_link(cid: str) -> str:
    return f'<a href="#card-{esc(cid)}">{esc(cid)}</a>'


def intro(loaded: manifest.Manifest, facts: dict) -> str:
    roots = ", ".join(esc(c.id) for c in loaded.chunks if c.requires is None)
    fork_only = "\n".join(f"<li><strong>{esc(f.title)}.</strong> {esc(f.why)}</li>"
                          for f in loaded.fork_only)
    return f"""<section id="intro">
<p>Upstream went unreviewed for a long time.
This fork kept fixing the roles and modules, and carried pull requests that were waiting for review.
Each chunk below offers one piece of that work back.
Take what you want.</p>

<details>
<summary>How to take a chunk</summary>
<p>Each chunk has one purpose.
Contributor commits keep their original authors.</p>
<p>Chunks stack.
Chunks with no parent ({roots}) are cut directly from upstream main.
A card's <em>Stacks on</em> line lists every chunk beneath it, and fetching a chunk brings all of them along.</p>
<p>Fetch with the command on the card, then work on a local copy: <code>git switch -c my-branch FETCH_HEAD</code>.
The <code>review/*</code> branches are rebased onto upstream main and force-pushed on every rebuild.</p>
</details>

<details>
<summary>What the status means</summary>
<p>A branch moves only after it rebases cleanly and passes its tests.</p>
<ul>
<li><em>verified</em>: rebased and tested at the upstream commit shown.</li>
<li><em>behind upstream</em>: the last rebase or test failed. The branch keeps its last good state.</li>
<li><em>no tests</em>: rebased cleanly, with nothing of its own to test.</li>
<li><em>landed</em>: already on upstream main.</li>
</ul>
</details>

<details>
<summary>Contributor License Agreement</summary>
{cla_summary(loaded, facts.get("prs", {}))}
</details>

<details>
<summary>Not offered ({len(loaded.fork_only)})</summary>
<p>These parts exist only for the fork:</p>
<ul class="fork-only">
{fork_only}
</ul>
</details>
</section>"""


def overview(loaded: manifest.Manifest, states: dict, facts: dict, tree: Tree) -> str:
    per = facts.get("chunks", {})
    rows = []
    for group in GROUP_ORDER:
        n = sum(1 for c in loaded.chunks if c.group == group)
        if n:
            rows.append(f'<li><a href="#group-{group}">{esc(GROUP_LABELS[group])}</a> '
                        f'<span class="count">{n}</span></li>')
    kinds = [status(c, states.get(c.id), bool(per.get(c.id, {}).get("landed")))[0]
             for c in loaded.chunks]
    buttons = [f'<button type="button" data-status="" aria-pressed="true">all '
               f'<span class="count">{len(kinds)}</span></button>']
    for kind, label in STATUS_LABELS.items():
        if kinds.count(kind):
            buttons.append(f'<button type="button" data-status="{kind}" aria-pressed="false">'
                           f'{esc(label)} <span class="count">{kinds.count(kind)}</span></button>')
    by_id = {c.id: c for c in loaded.chunks}
    kind_of = dict(zip((c.id for c in loaded.chunks), kinds))

    def node(cid: str) -> str:
        kind = kind_of[cid]
        return (f'<a class="node node-{kind}" href="#card-{esc(cid)}" '
                f'title="{esc(by_id[cid].title)}">'
                f'<span class="cid">{esc(cid)}</span>'
                f'<span class="ttl">{esc(by_id[cid].title)}</span>'
                f'<span class="pill pill-{kind}">{esc(STATUS_LABELS[kind])}</span></a>')
    missing = len(facts.get("unassigned", []))
    extra = ""
    if missing:
        extra = (f'<p class="warn">{plural(missing, "fork commit")} '
                 f'{"is" if missing == 1 else "are"} not yet assigned to any chunk.</p>')
    return f"""<section id="overview">
<h2>Chunks</h2>
<p>{plural(len(loaded.chunks), "chunk")} in {len(rows)} groups.</p>
<ul class="groups">
{chr(10).join(rows)}
</ul>
<div class="filters" hidden>
<div class="status-filter" role="group" aria-label="Filter by status">
{chr(10).join(buttons)}
</div>
<input type="search" id="search" placeholder="Search ids, titles, files, authors" aria-label="Search chunks">
<button type="button" id="expand">expand all</button>
<div class="view" role="group" aria-label="Order the chunks">
<button type="button" data-view="group" aria-pressed="true">by group</button>
<button type="button" data-view="stack" aria-pressed="false">by stack</button>
</div>
</div>
<details class="tree">
<summary>Dependency tree</summary>
<div class="outline">{tree.outline(node)}</div>
</details>
<p id="shown" class="shown" aria-live="polite"></p>
{extra}
</section>"""


def card(chunk: manifest.Chunk, s: ChunkState | None, f: dict, prs: dict, tree: Tree,
         per: dict) -> str:
    kind, line = status(chunk, s, bool(f.get("landed")))
    detail = ""
    if kind == "behind" and s is not None and s.reason:
        detail = f'<p class="status-detail">{esc(s.reason)}</p>'
    meta = [esc(GROUP_LABELS[chunk.group])]
    if chunk.epic != "-":
        meta.append(esc(chunk.epic))
    facts_rows = []
    for label, numbers in (("Closes", chunk.closes), ("Carries", chunk.carries),
                           ("Supersedes", chunk.supersedes)):
        if numbers:
            facts_rows.append((label, ", ".join(upstream_link(n) for n in numbers)))
    below = tree.ancestors[chunk.id]
    if below:
        extra = sum(len(per.get(a, {}).get("commits", [])) for a in below)
        facts_rows.append(("Stacks on", " → ".join(card_link(a) for a in below)
                           + f' <span class="muted">(fetching brings '
                           f'{plural(extra, "more commit")})</span>'))
    above = tree.children.get(chunk.id, [])
    if above:
        facts_rows.append(("Required by", ", ".join(card_link(a) for a in above)))
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
    depth, order = len(below), tree.order.index(chunk.id)
    return f"""<article class="card" id="card-{cid}" data-chunk="{cid}" data-status="{kind}" \
data-order="{order}" style="--depth: {depth}">
<details class="chunk">
<summary>
<span class="cid">{cid}</span>
<h3>{esc(chunk.title)}</h3>
<span class="pill pill-{kind}">{esc(STATUS_LABELS[kind])}</span>
</summary>
<div class="body">
<p class="meta">{" · ".join(meta)}</p>
<p class="status status-{kind}">{esc(line)}</p>
{detail}
{prose(chunk.summary)}
{merge_note}
<dl>
{dl}
</dl>
{fold}
<pre class="fetch"><code>{esc(fetch)}</code></pre>
</div>
</details>
</article>"""


def groups(loaded: manifest.Manifest, states: dict, facts: dict, tree: Tree) -> str:
    per, prs = facts.get("chunks", {}), facts.get("prs", {})
    out = []
    for group in GROUP_ORDER:
        members = [c for c in loaded.chunks if c.group == group]
        if not members:
            continue
        cards = "\n".join(card(c, states.get(c.id), per.get(c.id, {}), prs, tree, per)
                          for c in members)
        out.append(f'<section class="group" id="group-{group}">\n'
                   f"<h2>{esc(GROUP_LABELS[group])}</h2>\n{cards}\n</section>")
    out.append('<section id="stacks" hidden>\n<h2>Stacks</h2>\n</section>')
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
    tree = Tree(loaded)
    stamp = f"generated {generated} against upstream main {short(facts.get('upstream', ''))}"
    return string.Template(TEMPLATE.read_text()).substitute(
        generated=esc(stamp), intro=intro(loaded, facts),
        overview=overview(loaded, states, facts, tree),
        groups=groups(loaded, states, facts, tree), appendix=appendix(loaded, facts))
