# Upstream handover: design

Date: 2026-10-28.
Status: draft for review.

## Intent

Upstream `grafana/grafana-ansible-collection` has an active maintainer again: Dominik Süß (`theSuess`), who merged #545 on 2026-10-28.
This fork has diverged a long way during the dormant period: about 158 non-bump commits since the fork point, 207 files, +13,021 / −6,254.

The goal is to make it as cheap as possible for him to decide what to take back upstream, and then to take it.
He gets one web page that he works through on his own, and a set of branches the page points at, each holding one reviewable chunk of the fork's work.

The page is for him alone.
It does not report anything back to the fork's maintainer (Ronny), and it does not need to.

## Who reads it and how

Dominik opens a GitHub Pages URL, `https://no42-org.github.io/grafana-ansible-collection/`, and reads top to bottom at his own pace.
For each chunk he wants to evaluate, he fetches the matching branch and reviews or merges it in his own repository, by his own process.

## Goals

- Show **what the fork changed**, cut into chunks a maintainer can review one at a time.
- Show **how the fork handled his backlog**: which upstream issues it fixed, which upstream PRs it carries, which it judged not applicable or superseded.
- For every chunk, make the code available as a branch that applies to current upstream `main`, together with the chunks it depends on.
- Show provenance per chunk: author, whether that author has signed Grafana's CLA, and the upstream issues or PRs involved.
- Stay current. The page and branches are regenerated as upstream moves, and a chunk upstream has absorbed shows as **landed**.

## Non-goals

- No feedback channel to Ronny. No "copy my decisions", no notes addressed to Ronny, no shared state, no analytics.
- No pull requests opened on upstream by tooling. Dominik pulls; nothing pushes to him.
- No change to how the fork itself is built, tested or released.

## Anti-goals

Any of these makes the result a failure even if it technically works:

- **Any write to upstream.** AGENTS.md section 3 applies without exception: no issue, PR, comment, label, reaction or state change, and no `gh api` with a mutating verb against upstream. The generator and its workflow only read upstream.
- **A branch that silently does not apply.** A `review/*` branch that fails to rebase or merge onto upstream `main` costs his trust faster than anything else. A branch that has fallen behind must say so on its card (see "Settled during review"), never look current.
- **Contaminated chunks.** A chunk that reformats inherited files, mixes purposes, or smuggles in fork-only plumbing (namespace rename, release pipeline, tracker). The fork's existing "adoptable by construction" rule applies to every chunk.
- **Rewriting authorship.** Carried contributions keep their original authors. Never amend a contributor's commit; never add a `Signed-off-by` for someone else (AGENTS.md section 3).
- **Touching `main`'s history.** Branches are rebuilt from `main`'s commits. `main` itself is not rewritten.

## What is known today

From read-only recon on 2026-10-28:

- `make carried-prs` lists 9 carried commits from 8 upstream PRs: #510 (Ronny, closed by him on 2026-09-10, unmerged), #534, #448, #475, #536, #461 (2 commits), #538, #528.
- All 8 pass upstream's `license/cla` status. #510's thread holds a stale "not signed" bot comment; the bot's first comment was edited to "signed" two minutes later and the current status is `success`. The page must show the current status, not the comment.
- #448 was absorbed by upstream's #439 in merge `b2b92c2`, yet `make carried-prs` still lists it because it reads history. The page needs a better "landed" test than that tool provides (see below).
- Fork-origin work, by commit scope, covers: fixes to the `grafana` role, `plugins/` modules, `cloud_plugin`, tempo, mimir, `alert_contact_point`; the role-test and module-test harnesses and `check.yml` dry runs; version-selection fixtures; the uv toolchain, checksum-pinned tools and lint rework; `gate.yml` and SHA-pinned actions; per-role version pins with a weekly bump workflow; removal of `grafana_agent` and `promtail`; and fork-only plumbing.
- The fork's GitHub Project "Upstream tracking" (no42-org/projects/4) has 91 upstream items: about 30 Done, 25 Not applicable, 3 Superseded, 30 Untriaged. `Target release` records the fork version a fix shipped in where set.
- The fork repository is public. GitHub Pages is not enabled yet.

## Decided

### Page shape

A single self-contained HTML page: inline CSS and JS, no external fetches at view time, readable with JavaScript off except for the marking feature.

- **Intro.** Why the fork exists; how chunks are cut and how to consume a branch; the dependency rule (below); the CLA summary; an explicit list of what is fork-only and not offered (namespace rename, release pipeline, upstream tracker, role-bumper app, anything else fork-specific).
- **Overview.** Count of chunks per group and a progress line driven by his own marks.
- **Chunk catalogue.** One card per chunk, grouped. Each card shows:
  - chunk id, group, epic/subsystem, title;
  - what was wrong or missing and what the chunk does, in a few sentences of prose;
  - upstream issues it closes and upstream PRs it carries or supersedes, linked;
  - author(s) and CLA status per author;
  - size: commit count, files, lines;
  - **requires**: the chunks it depends on, linked;
  - status: available, or **landed** upstream;
  - the commit list and touched files behind a fold;
  - the exact command to fetch its branch;
  - take / maybe / skip toggles and a free-text note field, for his own use.
- **Backlog appendix.** A lookup table of every upstream issue and PR on the fork's board: number, title, fork decision, and a link to the card that addresses it, if any.

The marks and notes are stored in the viewer's browser `localStorage` only, keyed per chunk id, wrapped so the page works when storage is unavailable. Nothing is transmitted anywhere.

### Chunks and branches

- A chunk is one purpose. Fixes, harnesses, toolchain, removals and pinning are separate chunks.
- Every offered chunk has a branch `review/<chunk-id>-<slug>` on the fork.
- **Fix chunks depend on the harness that tests them.** A fix ships together with its test, and its branch is stacked on the harness chunk's branch. The card says "requires T1" (or similar).
- **The harness chunk carries only the minimal toolchain it needs to run**: the `uv`/`pyproject.toml`/`uv.lock` pieces and Makefile targets that `role-test` and `module-test` require. The rest of the CI and lint rework is its own optional chunk, so taking a fix does not drag in the whole toolchain overhaul.
- Branches with no dependency are cut directly from upstream `main`. Dependent branches are cut from their parent chunk's branch. The dependency graph must be acyclic.
- Carried upstream PRs whose original PR is still open: the card says plainly that merging the original upstream PR is the cleanest path, because it keeps the contributor's attribution and the PR's history. A branch is still provided, holding the cherry-pick plus any fork follow-up commits.

### Maintained, not a snapshot

- A **chunk manifest** in the tree is the single source of truth: per chunk, its id, group, title, prose, the commits from `main` that compose it, its dependencies, and its upstream references.
- One `make` target regenerates everything from the manifest, git and the board:
  1. fetch upstream;
  2. rebase every `review/*` branch onto current upstream `main` (or its parent chunk), in dependency order;
  3. run each rebased chunk's tests (see below);
  4. detect landed chunks;
  5. render the HTML.
- Pushing the branches and publishing the page is a separate step from rendering, so a local run can render and inspect without publishing.
- A Pages workflow publishes the page. It follows the fork's conventions: actions pinned to a SHA with the full semver in the comment, and the step calls a `make` target, never the tooling directly.
- Enabling GitHub Pages on the fork is a repository setting change and needs Ronny's confirmation at the moment it is done.

### Other constraints

- Every new or edited source file gets an SPDX header (the `source-headers` skill). Repo markdown is one sentence per line.
- The new generator, manifest and workflow are fork infrastructure. They are themselves listed as fork-only on the page, not offered as a chunk.
- AGENTS.md and RELEASING.md say "nothing is submitted upstream (maintainership is dormant)". That is no longer the situation. Both must be updated in the same change to describe the handover: still no writes to upstream, Dominik pulls from `review/*` branches.
- `.superpowers/` must be added to `.gitignore`.

### A rebased branch must pass its tests before it is published

Decided by Ronny.
Applying cleanly is not enough.
After a rebase, a chunk's branch runs the tests that cover it (`make role-test` for the roles and distros it touches, `make module-test` for the modules it touches, plus `make ci-lint` and `make sanity` where the chunk carries them) on the rebased tree, and is pushed only if they pass.
A chunk whose tests fail is treated exactly like one that failed to rebase: its last good branch stays and its card says **behind upstream**.
A passing card says "verified on upstream `main` at <sha>" with the date.
Chunks with no test coverage of their own (documentation, removals) say so on the card instead of claiming verification.
Only chunks whose base moved are re-tested, so the cost tracks what upstream changed.

### Settled during review (designer's calls, not Ronny's)

These were open after the first draft. They are the designer's calls, marked so Ronny can check them.

- **The published `review/*` branches are the source of their own content.** The first build seeds each branch from the manifest's commits on `main`. Later runs rebase the existing branch onto its new base; they do not rebuild it from `main`. Content that exists on `main` only inside merge commits (for example `1a2e164` deleting upstream's workflows, `b2b92c2` changing `roles/grafana/tasks/dashboards.yml`) is authored once as an ordinary commit on the review branch. A rebase conflict is resolved by hand once, on the branch, and stays resolved. The manifest records membership and prose for the page, not the branch's exact commit list.
- **Contributor commits are never split.** A carried commit goes onto its review branch whole, with its original author, per AGENTS.md section 3. If a chunk boundary would cut through one, the boundary moves instead. Only Ronny's own commits may be split, and the split commits are new commits authored by Ronny.
- **A failed rebuild does not stop the other chunks.** Chunks that rebuilt are pushed and the page is published. A chunk that failed keeps its last good branch, not moved. Its card says **behind upstream** with the date and upstream commit it last applied to. Chunks stacked on it get the same status. The run exits non-zero and names the failed chunks, so the failure is visible, but the rest of the handover keeps updating.

## Left to the builder

- The chunk cut itself: which commits go in which chunk, ids, titles and groups. The builder proposes the manifest and Ronny reviews it before any branch is pushed. Original commits on `main` are not touched.
- The landed test. Upstream may merge a chunk with a squash or a rebase, so matching commit hashes is not enough. Reasonable signals: `git cherry`/patch-id equivalence, the chunk's diff applying as empty to upstream `main`, or the carried upstream PR showing merged. Pick what works, and say which on the card.
- Generator language and template approach. The repo already uses bash and Python under `tools/`, with Python run through `uv`.
- How the workflow is triggered (manual dispatch, after `make upstream-sync`, on a schedule), provided it never publishes a branch that failed to rebuild.
- Visual design of the page, within the shape above. It must work at phone width and in light and dark themes.
- Whether `review/*` branches are force-pushed on rebuild (they will be, since they are rebased) and how that is explained on the page so he does not build on top of them.
