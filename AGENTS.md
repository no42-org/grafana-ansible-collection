# AGENTS.md

Curated fork of `grafana/grafana-ansible-collection`, published to Ansible Galaxy as `indigo423.grafana`.

Four things here are non-obvious. Each has already been got wrong at least once.

## 1. The tree says `grafana.grafana`; the artifact says `indigo423.grafana`

The rename happens at **build time**, in a copy under `build/src`. Never rename in the tree — that would conflict on every upstream merge, across 51 files.

`make dist` asserts an **exact count of 72 rewrites** and fails if it moves. If your change adds or removes a fully-qualified collection name, that build failure is the assertion working, not a bug:

```bash
./tools/rename-namespace.sh --expected-count   # re-derive, then read the diff before bumping
```

The rewrite uses a negative lookbehind because `community.grafana.grafana_datasource` *contains* `grafana.grafana`. A naive substitution breaks it in runtime code where nothing would notice.

## 2. Version numbers are this fork's own

`6.2.0` is not upstream's `6.2.0`. Provenance is the upstream base commit recorded in each GitHub release, never the version number. Do not "align versions with upstream".

## 3. Carried contributions keep their authors, and are never submitted

Upstream fixes are cherry-picked with `-x -s`: the contributor stays the author, you become the committer. Never amend a contributor's commit — fix it in a separate commit of your own. Never add a `Signed-off-by` for someone else.

Nothing is submitted upstream (maintainership is dormant), so changes must stay **adoptable by construction**: one purpose per commit, no reformatting of inherited files, `roles/*/molecule/` byte-identical.

### `grafana/grafana-ansible-collection` is read-only, always

**Never write anything to upstream.** No issue, no pull request, no comment, no review, no label, no reaction, and no state change. Read it as much as you like; change nothing.

This is not a style preference, and "it is only a no-op" is not an exception. On 2026-09-20 a tool probing whether a token had write permission sent a `PATCH` to `grafana/grafana-ansible-collection#540` expecting a refusal, and **reopened the issue**. It succeeded because the account authored that issue, and an author may reopen their own issue with no repository permission at all. The intent was a permission check; the effect was an unrequested change in someone else's tracker, visible in their timeline and impossible to erase.

So the rule is about the *request*, not the intent behind it:

- Read-only verbs against upstream are fine: `gh issue view`, `gh pr view`, `gh issue list`, `gh api` with `GET`.
- Anything that mutates is forbidden: `gh issue create|close|reopen|comment|edit`, `gh pr create|review|comment|merge`, and `gh api` with `-X POST|PATCH|PUT|DELETE`.
- Being *able* to do it is not permission to. Author rights and admin rights both make forbidden writes succeed quietly.
- If a task seems to need an upstream write, stop and ask. There is no case where an agent performs one unprompted.

Triage lives on this fork's board and in this fork's issues. `tools/upstream-tracker.sh` refuses to run if its `FORK_REPO` is pointed at the upstream repository, so the one tool that touches both cannot be misaimed by an environment override.

```bash
make carried-prs    # what is carried, and whether upstream merged it
```

That reports upstream-origin commits only. It is not the whole divergence.

The opposite question, what upstream has open that this fork has *not* acted on, is a GitHub Project seeded from upstream:

```bash
make upstream-status   # the board as a table
make upstream-sync     # refresh it from upstream
```

The sync owns four fields. It seeds `Fork decision` to `Untriaged` on creation and never writes it again, and never writes `Epic`, `Change type` or `Target release`. Those four are yours, which is why re-running it cannot destroy triage. Do not confuse the two tools: `carried-prs` reads git history, `upstream-tracker` reads upstream.

`Epic` is by subsystem, not by theme, and it is single-select. The rule that settles every item: a module under `plugins/` is `grafana-api-modules`, a role's tasks belong to that role's epic. `Change type` is `Bug`, `Enhancement` or `Maintenance`, and is not called `Type` because GitHub reserves that name.

### A tracking issue's state is derived, so closing one by hand does not stick

`Fork decision` owns whether the tracking issue is open. The sync closes it once the decision reaches `Done`, `Not applicable` or `Superseded`, and **reopens it** for any other value. So a tracking issue closed by hand, or closed by a `Closes #NN` line in a merged pull request, comes back at the next run with the decision still saying there is work to do.

That is the mechanism working. It happened three times on 2026-09-21, twice within an hour, and the second time only because the first correction was also wrong.

- To close a tracking issue, set `Fork decision` to `Done` and run `make upstream-sync`. Nothing else closes one durably.
- `Closes #NN` in a pull request is still worth writing — it records why the issue closed, and the comment survives the reopen. It is not what closes it.
- Use the **fork's** issue number, never upstream's. Commit `64239f4` wrote `Closes #509`, `#508` and `#331`, which are upstream numbers; fork issues do not run that high, so it closed nothing and three issues sat open for a day.

The same rule explains an issue reopening itself after you thought you had finished with it: the fix shipped, the decision never moved off `Untriaged` or `Fix here`.

## 4. `roles/*/molecule/` is dormant, not live

Those scenarios ship in the collection and are **never invoked**. Role tests are:

```bash
make role-test ROLE=grafana DISTRO=rhel     # converge, idempotence, verify
make role-test-list
```

`DISTRO` is a package family. `rhel` is not optional politeness — the `grafana` role's `yum`/`dnf` block is unreachable on Debian, so a Debian-only pass can hide a broken change.

`ANSIBLE_GROUP=ansible-top` runs the same test on the newest ansible-core inside `requires_ansible`'s range instead of the 2.18 everything else runs on. Both versions are declared once, in `pyproject.toml`, and the harness refuses anything from `PATH`: a local pass and a CI pass are statements about the same engine and the same collections, which they were not before. The log names the engine it ran on. Do not trust a role-test log that does not.

## Commands

```bash
make ci-lint-release   # tools/*.sh + every workflow's hygiene; needs no provisioning
make ci-lint           # the collection: shell, yaml, editorconfig, ansible, markdown, text
make install           # uv + corepack yarn; works without a system Python
make dist              # rename + build the collection tarball
make role-test ROLE=<role> DISTRO=debian|rhel
ansible-test sanity --docker
```

All of the above gate a release, in separate jobs of `.github/workflows/gate.yml`, which `ci.yml` and `release.yml` both call. One definition of what must pass.

## Traps worth knowing

- **A linter that cannot run is not a linter that found nothing.** `make install` used to need Python 3.10 exactly, and without it every Python linter bailed at its guard and *looked* like failing lint — three wrong conclusions before it was pinned down. `uv` provisions its own interpreter now, and the guards print `TOOLCHAIN NOT INSTALLED`. Keep that distinction when adding a gate.
- **A tool that cannot run may still exit 0.** `editorconfig-checker@5.0.1` shipped no `darwin-arm64` binary and exited 0 when it could not find one, so that gate passed without reading a file. Every gating tool is now provisioned and checksum-verified from `tools/includes/`, or from `uv.lock`, and **no workflow names a tool version**. It is one definition per tool because it was two: `yamllint` was pinned to 1.35.1 in `pyproject.toml` and 1.38.0 in `gate.yml`, `shellcheck` ran 0.11.0 locally and 0.9.0 in CI, and neither side could have noticed.
- **A gate that stops early is not a gate that passed.** `make ci-lint-release` used to exit at the first missing tool, abandoning the checks after it in silence: 5 of 10 ran and the output named only the missing tool. A missing tool now skips its own check, the run continues, and the summary names what did not run.
- **Every indent in a YAML folded scalar must be a multiple of two, including the ones that look like alignment.** `.editorconfig` sets `indent_size = 2` for `*.yml`, and `editorconfig-checker` reads that as a hard rule about left padding. Inside a `>-` block the natural thing is to align a continuation under the `{{` or the filter above it, which lands on an odd column and fails. `yamllint` and `ansible-lint` both pass on it, and only `ci-lint-editorconfig` objects — late in `make ci-lint`, after everything else has gone green, which is why it reads as a surprise every time. Three separate commits hit it in one day. Keep every continuation at the same column as the first line of the scalar:

  ```yaml
  msg: >-
    {{ releases
    | map(attribute='tag_name')
    | list }}
  ```

  Indenting those `|` lines three further spaces to sit under the `{{`, which is what reads well and what an editor will offer, puts them on an odd column and fails. There is no counter-example in this file because the check does not know what a fenced code block is: a demonstration of the failing form fails the gate that documents it.

- **A file in the tree is not automatically addressed to a consumer.** `requirements.txt` shipped this repository's linters for years while the one library every module imports was declared nowhere. `tools/check-shipped-manifests.py` derives the answer from `plugins/` and fails in both directions; the second is the one that catches it.
- **Tools install into the working tree, and every one needs excluding four times.** `.ansible/`, `ansible_collections/`, `.venv/`, `tools/bin/`. The same defect was fixed four times before the list moved to `tools/includes/lint-paths.sh`; `.yamllint`, `.ansible-lint` and `tools/rename-namespace.sh` keep their own copies and all four must agree. Un-ignored, they produce findings in other people's code — 4851 once — and take `make dist`'s rename count from 72 to well over double.
- **`grafana_dashboards_dir` is a control-node path.** The role's discovery tasks are `delegate_to: localhost`. It must be absolute and fully resolved, because the folder-name derivation strips it as a literal regular expression prefix.
- **`grafana_agent` and `promtail` are removed from this fork**, though upstream still ships both. The Agent is archived. Promtail went end of life on 2026-03-02. `alloy` replaces both. An upstream merge reintroduces both directories, and the removal has to be reapplied across eleven places, four of them prose that an upstream merge restores; `RELEASING.md` lists them.

- **Every role's version is pinned, and the pin is watched.** `<role>_version` is a concrete version, never `latest`, so a role's behaviour cannot change without a commit. A weekly workflow opens a bump pull request when a pin falls behind, and the role tests verify the bump before it merges — that verification is why pinning is safe rather than a risk moved elsewhere. `grafana` is excluded for a recorded reason. See `RELEASING.md`.

## Conventions

Conventional commits. `git commit -s` always. AI-assisted commits carry `Assisted-by: <Agent>:<model>`.

`main` is protected with **administrator bypass**. Direct pushes work; a pull request is the normal path. See `RELEASING.md`.

Never commit `openspec/`, `.claude/` or `.agent/`.

`RELEASING.md` is the authority on the release process, the divergence accounting and the known breakages. Read it before touching the pipeline.
