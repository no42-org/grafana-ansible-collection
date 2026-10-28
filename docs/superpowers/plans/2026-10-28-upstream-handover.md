# Upstream Handover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish a maintained handover page on the fork's GitHub Pages, backed by one tested `review/*` branch per chunk of fork work, so upstream's maintainer can decide what to take and pull it.

**Architecture:** A chunk manifest (`tools/handover/chunks.yml`) is the source of truth for membership and prose. A Python CLI under `tools/handover/` rebases the existing `review/*` branches onto current upstream in dependency order, runs each chunk's declared tests, promotes the ones that pass, detects chunks upstream has absorbed, and renders one self-contained HTML page. A workflow runs the cycle and deploys the page to Pages. Everything reads upstream; nothing writes to it.

**Tech Stack:** Python 3.12 run through `uv` (`--group ansible` supplies PyYAML), stdlib `unittest`, `git`, `gh` (read-only against upstream), GitHub Actions, GitHub Pages.

**Spec:** `docs/superpowers/specs/2026-10-28-upstream-handover-design.md`

## Global Constraints

- **Never write to `grafana/grafana-ansible-collection`.** Upstream access is `git fetch` and `gh api` with `GET` only. Every push goes to `origin` (`no42-org/grafana-ansible-collection`), and the push code refuses a remote whose URL names the upstream repository (AGENTS.md section 3).
- Contributor commits are cherry-picked whole, author preserved. Never amend, split or re-sign them. Only Ronny's commits may be split.
- `main`'s history is never rewritten. Only `review/*` and `handover-candidate/*` refs are created or force-pushed.
- A `review/*` branch moves only after its rebase succeeded **and** its declared tests passed on the rebased tree. A chunk whose parent did not move does not move either.
- New source files start with an SPDX header after any shebang: `# Copyright 2026 Ronny Trommer <ronny@no42.org>` / `# SPDX-License-Identifier: GPL-3.0-or-later` (HTML: the same in `<!-- -->`). No header on `chunks.yml` data or test fixtures.
- Python runs as `uv run --frozen --group ansible python …`. No new dependency in `pyproject.toml`.
- CI steps call `make` targets only. Actions pinned to a full SHA with the full semver in a trailing comment. `persist-credentials: false` on every checkout.
- Repo Markdown is one sentence per line. No em-dashes in prose.
- YAML folded scalars: every continuation indent is a multiple of two (AGENTS.md, editorconfig trap).
- Enabling GitHub Pages is a repository setting change: ask Ronny at the moment it is done.

### Manifest schema (`tools/handover/chunks.yml`)

```yaml
fork_only:                      # listed on the page, never offered
  - title: Namespace rename at build time
    why: Publishes indigo423.grafana; upstream publishes grafana.grafana.
    commits: [...]              # main commits that are fork-only
chunks:
  - id: T1                      # ^[A-Z]{1,3}[0-9]{1,2}$, unique
    slug: role-test-harness     # ^[a-z0-9]+(-[a-z0-9]+)*$
    group: harness              # fixes | carried | harness | toolchain | pinning | removals | docs
    epic: cross-role            # the board's Epic vocabulary, or "-"
    title: Container role tests replacing Molecule
    summary: |                  # plain paragraphs, blank-line separated; no HTML
      ...
    commits: [3ca217c8, ...]    # on main; used by seed only
    requires: []                # zero or one chunk id: the parent branch
    upstream:
      closes: [537]             # upstream issue numbers
      carries: [528]            # upstream PR numbers whose commits are in this chunk
      supersedes: []            # upstream PR numbers this chunk replaces
    tests:                      # make goals run on the rebased tree
      - role-test ROLE=grafana DISTRO=rhel
```

Branch name: `review/<id lowercased>-<slug>`, for example `review/t1-role-test-harness`. Candidate name: `handover-candidate/<same>`.
Allowed test goals (first word): `role-test`, `module-test`, `ci-lint`, `ci-lint-release`, `sanity`, `units`, `version-select-test`. Arguments must match `^[A-Z_]+=[A-Za-z0-9_.-]+$`.

### State file (`build/handover/state.json`)

One object per chunk id: `{"rebase": "ok"|"conflict"|"parent-behind"|"unchanged", "candidate": sha|null, "base": sha, "tests": "pass"|"fail"|"none"|"pending", "promoted": bool, "verified_at": {"upstream": sha, "date": "YYYY-MM-DD"}|null, "last_good": {"upstream": sha, "date": …}|null, "landed": bool}`.
`last_good` comes from the previous published `state.json`, which the workflow fetches from the deployed page (`state.json` is published next to `index.html`).

## Review Focus

- **Third-party text in the page.** Upstream issue titles, commit subjects and author names are untrusted. Every interpolated value is HTML-escaped; a title containing `<script>` renders as text. Test in Task 6.
- **Storage unavailable.** `localStorage` throws in private windows and file:// previews; the page still renders every card and the toggles simply do not persist. Test in Task 6.
- **A child of a failed chunk.** If T1 fails, every chunk with `requires: [T1]`, transitively, is `parent-behind` and keeps its old branch, even when it would rebase cleanly on its own. Test in Task 3.
- **A conflict mid-rebase.** A failed rebase is aborted and the work tree is clean before the next chunk starts; one conflict never leaves the repository in a rebase state. Test in Task 3.
- **Misaimed push.** A remote URL naming `grafana/grafana-ansible-collection`, by HTTPS or SSH, is refused before any `git push` runs. Test in Task 4.

---

### Task 1: Propose the chunk cut (human gate)

**Files:**

- Create: `tools/handover/chunks.yml`
- Modify: `galaxy.yml` (`build_ignore`: add `docs/superpowers/*`, so the spec and plan never ship in the collection)

**Interfaces:**

- Produces: `chunks.yml` in the schema above, consumed by every later task.

- [ ] **Step 1: Inventory.** List every non-merge commit in `upstream/main..main` (`git log --no-merges --reverse --format='%h %an %s'`), plus the content changes that exist only in merges `b2b92c2`, `1a2e164` and `1a7a20b` (`git diff <merge>^1 <merge>` minus what the second parent brought). Keep the list in the scratchpad, not the tree.
- [ ] **Step 2: Classify each commit** into one group, or `fork_only`. Fork-only for certain: namespace rename (`tools/rename-namespace.sh`, `make dist`), the release pipeline (`release.yml`), the upstream tracker, role-bumper app wiring, the handover tooling itself, `AGENTS.md`/`RELEASING.md` content about the fork.
- [ ] **Step 3: Cut chunks.** One purpose each. The harness chunk(s) carry only the `uv`/`pyproject.toml`/`uv.lock` parts and Makefile targets that `role-test` and `module-test` need; the rest of the toolchain and lint rework is its own optional chunk. Fix chunks that have a harness test set `requires` to that harness chunk and list the test in `tests`. Carried PR commits stay whole and name the PR in `upstream.carries`; if a boundary would split one, move the boundary. Every commit on `main` lands in exactly one chunk or in `fork_only`.
- [ ] **Step 4: Write `summary` prose** for each chunk: what was wrong, what the chunk does, why. Plain sentences. Take upstream numbers from the board (`make upstream-status`) and commit messages.
- [ ] **Step 5: Add the `build_ignore` line**, then run `make dist` and confirm the rename count did not move (`EXPECTED_REWRITES`, 90).
- [ ] **Step 6: STOP. Show Ronny the cut** as a table (id, group, title, commits, requires, tests) and wait for approval. Revise until approved. Do not start Task 8 before this is approved.
- [ ] **Step 7: Commit** `tools/handover/chunks.yml` and `galaxy.yml`: `chore(handover): propose the chunk cut for the upstream handover`.

### Task 2: Manifest loader and `make handover-check`

**Files:**

- Create: `tools/handover/manifest.py`, `tools/handover/handover.py` (CLI, argparse subcommands), `tools/handover/tests/test_manifest.py`
- Modify: `Makefile` (targets `handover-check`, `handover-check-coverage`, `handover-unit`; add all to `.PHONY`), `tools/lint-release.sh` (one check block, same shape as the shipped-manifests block, calling `make handover-check`)

**Interfaces:**

- Produces: `@dataclass(frozen=True) class Chunk: id, slug, group, epic, title, summary, commits: tuple[str,...], requires: str|None, closes: tuple[int,...], carries: tuple[int,...], supersedes: tuple[int,...], tests: tuple[str,...]` with properties `branch -> str` and `candidate -> str`.
- Produces: `load(path: Path, repo: Path) -> Manifest` where `Manifest` has `chunks: tuple[Chunk,...]` in dependency order (parents first, then file order), `fork_only: tuple[ForkOnly,...]`, and `children(id) -> tuple[Chunk,...]` (transitive). Raises `ManifestError(str)` naming the chunk and field.
- CLI: `handover.py check [--manifest PATH]` exits 0 and prints `N chunks, M fork-only` or exits 1 with the error. `check --coverage` additionally lists commits in `upstream/main..main` that are in no chunk and no `fork_only` entry, and exits 1 if there are any. Coverage is not part of `ci-lint-release`: a squash merge changes shas, so a commit cannot list itself. The handover workflow runs it, and its result shows on the page as a count of unassigned commits.

- [ ] **Step 1: Write failing tests** in `test_manifest.py` (fixtures as YAML strings written to a temp dir; a temp git repo for commit checks):
  - `test_orders_parents_first`: chunks listed `F1 requires T1`, then `T1` → order `T1, F1`.
  - `test_rejects_cycle`: `A requires B`, `B requires A` → `ManifestError` containing `cycle`.
  - `test_rejects_two_parents`: `requires: [T1, T2]` → error containing `at most one`.
  - `test_rejects_unknown_parent`, `test_rejects_duplicate_id`, `test_rejects_bad_slug`, `test_rejects_unknown_group`.
  - `test_rejects_test_goal_outside_allowlist`: `tests: ["dist"]` and `tests: ["role-test ROLE=$(rm)"]` → error.
  - `test_rejects_commit_not_on_main`: a sha absent from the repo → error naming the sha.
  - `test_rejects_commit_in_two_chunks` (also across a chunk and a `fork_only` entry).
  - `test_coverage_lists_unassigned_commits`: one main commit in no entry → `check --coverage` exits 1 and prints its sha; plain `check` exits 0.
  - `test_branch_names`: `T1`/`role-test-harness` → `review/t1-role-test-harness`, `handover-candidate/t1-role-test-harness`.
  - `test_children_transitive`: `F1 requires T1`, `F2 requires F1` → `children("T1") == (F1, F2)`.
- [ ] **Step 2: Run** `make handover-unit` → FAIL (module missing). The target runs `uv run --frozen --group ansible python -m unittest discover -s tools/handover/tests -t tools/handover -v`.
- [ ] **Step 3: Implement** `manifest.py` and the `check` subcommand. Commit existence via `git cat-file -e <sha>^{commit}` and `git merge-base --is-ancestor <sha> main`.
- [ ] **Step 4: Run** `make handover-unit` → all pass; `make handover-check` → `N chunks, M fork-only` against Task 1's file; `PATH="$PWD/.venv/bin:$PATH" make ci-lint-release` → `every check ran`.
- [ ] **Step 5: Commit** `feat(handover): load and validate the chunk manifest`.

### Task 3: Rebuild candidates in dependency order

**Files:**

- Create: `tools/handover/rebuild.py`, `tools/handover/state.py`, `tools/handover/tests/test_rebuild.py`, `tools/handover/tests/gitfixture.py` (helper that builds a temp repo with an `upstream` and `origin` bare remote)
- Modify: `Makefile` (`handover-rebuild`)

**Interfaces:**

- Consumes: `load`, `Chunk`, `Manifest.children`.
- Produces: `state.load(path) -> dict[str, ChunkState]`, `state.save(path, dict)`; `ChunkState` dataclass mirroring the state file schema.
- Produces: `rebuild(manifest, repo: Path, upstream_ref="upstream/main", origin="origin") -> dict[str, ChunkState]`. For each chunk in order: new base is `upstream_ref` for a root chunk, the parent's candidate for a child; old base is the merge-base with `upstream_ref` for a root chunk, `origin/<parent.branch>` for a child. Runs `git rebase --onto <new> <old> <candidate>` on a candidate branch created from `origin/<branch>`. `rebase` is `unchanged` when the new base equals the old base, `conflict` after `git rebase --abort`, `parent-behind` when the parent is `conflict` or `parent-behind`.
- CLI: `handover.py rebuild` writes `build/handover/state.json` and prints one line per chunk; exits 1 if any chunk is `conflict`, after processing all of them.

- [ ] **Step 1: Write failing tests:**
  - `test_root_chunk_rebases_onto_new_upstream`: upstream gains a commit; candidate's parent is the new upstream tip; `rebase == "ok"`.
  - `test_child_stacks_on_parent_candidate`: candidate of F1 has T1's candidate as ancestor and contains no T1 commit twice.
  - `test_unchanged_when_base_did_not_move`.
  - `test_conflict_is_aborted_and_tree_clean`: upstream edits the same line → `conflict`; `git status --porcelain` empty; no `.git/rebase-merge` directory.
  - `test_child_of_conflict_is_parent_behind`: F1 `parent-behind`, F2 (child of F1) `parent-behind`, an unrelated root chunk still `ok`.
  - `test_authors_preserved`: a contributor-authored commit keeps `%an`/`%ae` after rebase.
  - `test_exit_code_after_processing_all`: one conflict, three chunks → exit 1 and all three in `state.json`.
- [ ] **Step 2: Run** `make handover-unit` → the new tests FAIL.
- [ ] **Step 3: Implement** `state.py`, `rebuild.py` and the `rebuild` subcommand.
- [ ] **Step 4: Run** `make handover-unit` → pass.
- [ ] **Step 5: Commit** `feat(handover): rebase review branches onto upstream in dependency order`.

### Task 4: Test plan, test runner, promotion

**Files:**

- Create: `tools/handover/promote.py`, `tools/handover/tests/test_promote.py`
- Modify: `tools/handover/handover.py` (subcommands `matrix`, `test`, `promote`), `Makefile` (`handover-matrix`, `handover-test CHUNK=<id>`, `handover-promote`)

**Interfaces:**

- Consumes: `load`, `state.load/save`.
- Produces: `matrix(manifest, states) -> list[dict]` with `{"chunk": id, "ref": candidate, "goal": str}` for every chunk whose `rebase == "ok"`, one entry per test goal. Printed as compact JSON by `handover.py matrix` for the workflow.
- Produces: `run_tests(chunk, repo) -> bool`: runs `make <goal>` for each of the chunk's goals in the checked-out candidate tree, after confirming `make -n <first word>` exists there (a missing target is a failure, never a skip).
- Produces: `promote(manifest, states, results: dict[str, bool], today: str, upstream_sha: str, origin="origin") -> dict[str, ChunkState]`. A chunk is promoted when `rebase == "ok"`, all its tests passed (or it has none), and its parent was promoted or is unchanged. Pushes `<candidate>:refs/heads/<branch>` with `--force-with-lease=<branch>:<old origin sha>`. Sets `verified_at` for promoted chunks with tests, keeps `last_good` otherwise. Deletes `handover-candidate/*` from `origin` at the end.
- Produces: `assert_not_upstream(url: str) -> None`, raising `SystemExit` for any URL containing `grafana/grafana-ansible-collection` (case-insensitive, `.git` suffix optional, HTTPS or `git@github.com:` form).
- The workflow writes each test job's result as `build/handover/results/<chunk>.json` (`{"chunk": id, "passed": bool}`); `handover.py promote` reads that directory. A chunk with tests but no result file counts as failed.

- [ ] **Step 1: Write failing tests:**
  - `test_matrix_skips_conflict_and_parent_behind`.
  - `test_missing_make_target_fails`: goal `module-test MODULE=x` in a tree whose Makefile lacks `module-test` → `run_tests` returns False.
  - `test_promote_requires_tests_and_parent`: parent failed tests → child not promoted even with passing tests.
  - `test_missing_result_file_is_failure`.
  - `test_force_with_lease_refuses_moved_remote`: origin's branch moved after rebuild → push fails, chunk not promoted, others still promoted.
  - `test_refuses_upstream_url`: `https://github.com/grafana/grafana-ansible-collection`, `…collection.git`, `git@github.com:Grafana/grafana-ansible-collection.git` → `SystemExit`; `https://github.com/no42-org/grafana-ansible-collection` passes.
  - `test_candidates_deleted_after_promote`.
- [ ] **Step 2: Run** `make handover-unit` → new tests FAIL.
- [ ] **Step 3: Implement** `promote.py` and the three subcommands. `assert_not_upstream` runs on `git remote get-url origin` before every push and delete.
- [ ] **Step 4: Run** `make handover-unit` → pass.
- [ ] **Step 5: Commit** `feat(handover): run each chunk's tests and promote what passed`.

### Task 5: Facts for the page (git, landed, CLA, board)

**Files:**

- Create: `tools/handover/facts.py`, `tools/handover/tests/test_facts.py`
- Modify: `tools/handover/handover.py` (subcommand `facts`), `Makefile` (`handover-facts`)

**Interfaces:**

- Consumes: `load`, `state.load/save`.
- Produces: `chunk_facts(chunk, repo) -> ChunkFacts` with `commits: list[{sha, subject, author}]`, `files: list[str]`, `insertions: int`, `deletions: int`, taken from `<branch>` relative to its base (upstream/main for roots, the parent branch for children).
- Produces: `is_landed(chunk, repo, merged_prs: set[int]) -> bool`: True when `git cherry upstream/main <branch> <base>` prints no `+` line, or when every PR in `chunk.carries` is in `merged_prs`.
- Produces: `cla_status(gh: Callable[[list[str]], str], prs: list[int]) -> dict[int, str]` returning `success`/`failure`/`pending`/`unknown` from the `license/cla` context of each upstream PR head (`gh api repos/grafana/grafana-ansible-collection/pulls/<n>` then `/commits/<sha>/status`). Ronny's own commits use PR #510's status. Any other author with no carried PR is `unknown`, shown as such.
- Produces: `board_rows(gh) -> list[{number, kind, title, decision, epic, target}]` from `gh project item-list 4 --owner no42-org --limit 1000 --format json`; fails if `totalCount` exceeds the limit (same guard as `upstream-tracker.sh`). Upstream title is the tracking issue title with its `[Issue #NNN]` prefix removed.
- `gh` is injected as a callable so tests never touch the network. The real callable rejects any argument list containing `-X`, `--method`, `-f`, `-F` or `--input` (read-only by construction).
- CLI: `handover.py facts` writes `build/handover/facts.json`, including `unassigned: [sha…]` from Task 2's coverage check; a failed `gh` call fails the command, never yields an empty appendix.

- [ ] **Step 1: Write failing tests:**
  - `test_landed_by_patch_equivalence`: upstream squash-merges the chunk's diff as one commit → landed.
  - `test_not_landed_when_one_commit_missing`.
  - `test_landed_by_merged_pr`.
  - `test_cla_reads_license_cla_context` with a fake `gh` returning recorded JSON for #528 (`success`) and a PR with no status (`unknown`).
  - `test_gh_wrapper_rejects_mutating_flags`: `["api", "-X", "PATCH", …]` → `SystemExit`.
  - `test_board_truncation_fails`: `totalCount` 1001 → error.
  - `test_board_title_prefix_stripped`.
- [ ] **Step 2: Run** `make handover-unit` → new tests FAIL.
- [ ] **Step 3: Implement** `facts.py` and the subcommand.
- [ ] **Step 4: Run** `make handover-unit` → pass; then `make handover-facts` locally with `gh` authenticated and check that `facts.json` holds 8 carried PRs, all `success`.
- [ ] **Step 5: Commit** `feat(handover): gather commits, landed state, CLA and board facts`.

### Task 6: Render the page

**Files:**

- Create: `tools/handover/render.py`, `tools/handover/template.html`, `tools/handover/tests/test_render.py`
- Modify: `tools/handover/handover.py` (subcommand `render`), `Makefile` (`handover-render`)

**Interfaces:**

- Consumes: `Manifest`, `state.json`, `facts.json`.
- Produces: `render(manifest, states, facts, generated: str) -> str` (the full HTML). `handover.py render` writes `build/handover/site/index.html` and copies `state.json` beside it.

Page content (from the spec, in this order): intro (why the fork exists; how chunks are cut; how to fetch and that `review/*` branches are force-pushed on every rebuild, so build on a local copy; the dependency rule; CLA summary; the `fork_only` list), overview (count per group, progress line from his marks, and the number of fork commits not yet assigned to any chunk, from `facts.json`'s `unassigned` list), cards grouped by `group`, backlog appendix (board rows sorted by number, each linking to the card whose `closes`/`carries`/`supersedes` contains it).
Card fields: id, group, epic, title, summary paragraphs, closes/carries/supersedes linked to upstream, authors with CLA status, commits/files/+/−, requires (linked), status (`verified on upstream main at <short sha>, <date>` | `behind upstream since <date> (last applied to <short sha>)` | `landed upstream` | `no tests of its own`), commit list and files in `<details>`, fetch command `git fetch https://github.com/no42-org/grafana-ansible-collection <branch>`, take/maybe/skip toggles and a note field.
Marks: `localStorage` key `handover:<chunk id>` holding `{"mark": "take"|"maybe"|"skip", "note": str}`, every access in try/catch. No network request of any kind from the page. No feedback or export feature.
Visual: single file, inline CSS/JS, light and dark via `prefers-color-scheme`, readable at 400px.

- [ ] **Step 1: Write failing tests** (fixture manifest + states + facts as Python dicts):
  - `test_escapes_untrusted_text`: a board title `<script>alert(1)</script>` and a commit subject with `&<>"` appear only escaped.
  - `test_status_lines`: one chunk each in verified, behind, landed and no-tests states produce the four exact status strings.
  - `test_fork_only_listed_and_not_carded`.
  - `test_appendix_links_to_card`: board row #537 links to `#card-F7` when F7 closes 537; an untouched row has no link.
  - `test_no_external_urls_loaded`: no `<script src`, `<link rel="stylesheet"`, `fetch(` or `XMLHttpRequest` in the output.
  - `test_storage_access_guarded`: every `localStorage` occurrence in the output is inside a `try` block (check by counting `localStorage` uses against a single guarded helper).
  - `test_no_feedback_feature`: output contains no `clipboard`, `mailto:` or form `action`.
- [ ] **Step 2: Run** `make handover-unit` → new tests FAIL.
- [ ] **Step 3: Implement** `render.py` with `string.Template` or `html.escape` plus a small template (no Jinja; `uv` group has no Jinja guarantee), and `template.html` with the SPDX comment at the top.
- [ ] **Step 4: Run** `make handover-unit` → pass. Then `make handover-render` against Task 1's manifest with a hand-written `state.json`, open the file, and check phone width, dark mode, and marks surviving a reload.
- [ ] **Step 5: Commit** `feat(handover): render the handover page`.

### Task 7: Workflow and Pages

**Files:**

- Create: `.github/workflows/handover.yml`
- Modify: `Makefile` (`handover-publish-local`: rebuild + facts + render without pushing, for local inspection)

Jobs, in order:

1. `rebuild` (`contents: write`): checkout with `fetch-depth: 0`, `persist-credentials: false`; add `upstream` remote (fetch only); download the previously deployed `state.json` from the Pages URL (absent on first run is fine); `make handover-check`, `make handover-check-coverage` (recorded, not fatal), `make handover-rebuild`; push `handover-candidate/*` to origin with `GITHUB_TOKEN` passed per command (`git -c http.extraheader=…`), never written to git config; output `make handover-matrix`. Continue on rebuild exit 1 (conflicts are recorded in state, not fatal here); upload `build/handover` as an artifact.
2. `test` (matrix from job 1, `fail-fast: false`, `contents: read`): checkout the candidate ref, `make handover-test CHUNK=<id>`, write and upload its result file. Uses the same docker/uv setup as `role-test.yml` and `module-test.yml`.
3. `publish` (`contents: write`, `pages: write`, `id-token: write`, `environment: github-pages`): download artifacts; `make handover-promote`; `make handover-facts` with `GH_TOKEN: secrets.PROJECTS_TOKEN` (the board is private); `make handover-render`; `actions/upload-pages-artifact` and `actions/deploy-pages`; fail the job at the end if any chunk is `conflict` or failed tests, after deploying.

Triggers: `workflow_dispatch`, and `schedule` weekly on Monday after the upstream tracker (`41 7 * * 1`). `concurrency: handover`, no cancel.

- [ ] **Step 1: Look up action SHAs** read-only (`gh api repos/actions/<name>/releases/latest`, then `git/ref/tags/<tag>`) for `upload-pages-artifact`, `deploy-pages`, `upload-artifact`, `download-artifact`; reuse the checkout and `setup-uv` pins already in `role-test.yml`.
- [ ] **Step 2: Write `handover.yml`.**
- [ ] **Step 3: Run** `PATH="$PWD/.venv/bin:$PATH" make ci-lint-release` → zizmor and actionlint report nothing; `every check ran`.
- [ ] **Step 4: Commit** `ci(handover): rebuild, test and publish the handover`.
- [ ] **Step 5: Ask Ronny** before enabling Pages with source "GitHub Actions" (`gh api -X POST repos/no42-org/grafana-ansible-collection/pages -f build_type=workflow`). This is the fork, never upstream.

### Task 8: Seed the review branches

**Files:**

- Modify: `tools/handover/handover.py` (subcommand `seed [--chunk ID] [--continue]`), `Makefile` (`handover-seed`), `tools/handover/tests/test_seed.py`

**Interfaces:**

- Produces: `seed(chunk, repo)`: creates `<branch>` locally from its base (upstream/main, or the parent's local branch) and runs `git cherry-pick <commits…>` without `-x` (carried commits already carry their origin line). On conflict it stops and prints what to resolve; `--continue` resumes. Refuses to overwrite an existing local or origin branch.

- [ ] **Step 1: Write failing tests** `test_seed_preserves_author`, `test_seed_stops_on_conflict_and_continues`, `test_seed_refuses_existing_branch`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → pass. **Step 5: Commit** `feat(handover): seed review branches from the manifest`.
- [ ] **Step 6: Seed every chunk** in dependency order. Merge-only content (for example `1a2e164`'s workflow deletions) is authored as a new commit by Ronny on the branch. Resolve conflicts by hand; never edit a contributor's commit content, put any fix in a separate commit on the branch.
- [ ] **Step 7: Verify each branch locally**: `make handover-test CHUNK=<id>` for each chunk with tests. Record failures for Ronny instead of forcing them green.
- [ ] **Step 8: STOP. Ask Ronny** before pushing `review/*` to origin. Then push, dispatch the workflow (`gh workflow run handover.yml` on the fork), and confirm the page renders at `https://no42-org.github.io/grafana-ansible-collection/` with every chunk verified or explained.

### Task 9: Update the fork's own docs

**Files:**

- Modify: `AGENTS.md` (section 3), `RELEASING.md` (the section that says nothing is submitted upstream; add a "Handover" section)

- [ ] **Step 1: Rewrite** the "maintainership is dormant" statements: upstream is maintained again; the fork still never writes there; upstream's maintainer pulls from `review/*` branches listed on the handover page. Add the commands (`make handover-check`, `handover-rebuild`, `handover-render`, `handover-seed`) and the rule that `chunks.yml` is updated after a commit lands on `main` (every commit in exactly one chunk or `fork_only`; `make handover-check-coverage` lists what is missing, and the page shows the count).
- [ ] **Step 2: Run** `make ci-lint` → Markdown, text and editorconfig pass.
- [ ] **Step 3: Commit** `docs: describe the upstream handover`.
