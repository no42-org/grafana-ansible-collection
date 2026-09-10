# AGENTS.md

Curated fork of `grafana/grafana-ansible-collection`, published to Ansible Galaxy as `indigo423.grafana`.

Four things here are non-obvious. Each has already been got wrong at least once.

## 1. The tree says `grafana.grafana`; the artifact says `indigo423.grafana`

The rename happens at **build time**, in a copy under `build/src`. Never rename in the tree — that would conflict on every upstream merge, across 51 files.

`make dist` asserts an **exact count of 83 rewrites** and fails if it moves. If your change adds or removes a fully-qualified collection name, that build failure is the assertion working, not a bug:

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
make ci-lint-release   # the release gate: tools/*.sh + release.yml
make ci-lint           # the full inherited lint set — currently NOT trustworthy, see below
make dist              # rename + build the collection tarball
make role-test ROLE=<role> DISTRO=debian|rhel
ansible-test sanity --docker   # what the release actually gates on
```

## Traps worth knowing

- **The inherited `tools/lint-*.sh` scripts swallow their exit status.** They end on a false `if` with no `exit`, so `make ci-lint-*` returns 0 while the linter reports errors. CI has shown 61 error annotations on a green step. Only `tools/lint-release.sh` gates. Fixing this is the `honest-ci-gates` change.
- **`make install` is fragile.** `Pipfile` pins `python_version = "3.10"`; without that interpreter pipenv fails and every Python linter bails at its guard, which *looks* like failing lint. This caused two wrong conclusions before it was diagnosed.
- **`grafana_dashboards_dir` is a control-node path.** The role's discovery tasks are `delegate_to: localhost`. It must be absolute and fully resolved, because the folder-name derivation strips it as a literal regex prefix.
- **Three roles are broken with default settings**, all inherited: `promtail` (upstream deleted its packages), `tempo` (default config invalid for the version it installs), `loki` on RHEL (upstream renamed the RPMs). They deliberately ship no role test. See `RELEASING.md`.

## Conventions

Conventional commits. `git commit -s` always. AI-assisted commits carry `Assisted-by: <Agent>:<model>`.

Never commit `openspec/`, `.claude/` or `.agent/`.

`RELEASING.md` is the authority on the release process, the divergence accounting and the known breakages. Read it before touching the pipeline.
