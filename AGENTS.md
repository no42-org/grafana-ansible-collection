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

```bash
make carried-prs    # what is carried, and whether upstream merged it
```

That reports upstream-origin commits only. It is not the whole divergence.

## 4. `roles/*/molecule/` is dormant, not live

Those scenarios ship in the collection and are **never invoked**. Role tests are:

```bash
make role-test ROLE=grafana DISTRO=rhel     # converge, idempotence, verify
make role-test-list
```

`DISTRO` is a package family. `rhel` is not optional politeness — the `grafana` role's `yum`/`dnf` block is unreachable on Debian, so a Debian-only pass can hide a broken change.

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
- **A tool that cannot run may still exit 0.** `editorconfig-checker@5.0.1` shipped no `darwin-arm64` binary and exited 0 when it could not find one, so that gate passed without reading a file. It is a pinned standalone binary now, provisioned by `tools/includes/editorconfig-checker.sh`.
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
