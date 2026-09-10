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
make ci-lint-release   # tools/*.sh + every workflow's hygiene; needs no pipenv
make ci-lint-yaml      # the collection; needs `make install`, which is fragile locally
make dist              # rename + build the collection tarball
make role-test ROLE=<role> DISTRO=debian|rhel
ansible-test sanity --docker
```

All of the above gate a release, in separate jobs of `.github/workflows/gate.yml`, which `ci.yml` and `release.yml` both call. One definition of what must pass.

## Traps worth knowing

- **`make install` is fragile locally, and never in CI.** `Pipfile` pins `python_version = "3.10"`; without that interpreter pipenv fails and every Python linter bails at its guard, which *looks* like failing lint. This caused three wrong conclusions before it was pinned down — twice reading a guard bail as a red gate, once inferring that the pipenv chain was too fragile for the release path. CI's `setup-python` supplies 3.10 and `make install` has succeeded on every run.
- **A linter that cannot run may still exit 0.** `editorconfig-checker@5.0.1` ships no `darwin-arm64` binary and exits 0 when it cannot find one. Measure with the standalone Go binary locally.
- **`ansible-lint` installs the dependency collections into the tree.** `.ansible/collections/` locally, `ansible_collections/` in CI (`ansible.cfg` sets `collections_paths = ./`). Both are gitignored and excluded now. Un-ignored, they produce 4851 findings in other people's code and take `make dist`'s rename count from 83 to 174.
- **`grafana_dashboards_dir` is a control-node path.** The role's discovery tasks are `delegate_to: localhost`. It must be absolute and fully resolved, because the folder-name derivation strips it as a literal regex prefix.
- **Three roles are broken with default settings**, all inherited: `promtail` (upstream deleted its packages), `tempo` (default config invalid for the version it installs), `loki` on RHEL (upstream renamed the RPMs). They deliberately ship no role test. See `RELEASING.md`.

## Conventions

Conventional commits. `git commit -s` always. AI-assisted commits carry `Assisted-by: <Agent>:<model>`.

`main` is protected with **administrator bypass**. Direct pushes work; a pull request is the normal path. See `RELEASING.md`.

Never commit `openspec/`, `.claude/` or `.agent/`.

`RELEASING.md` is the authority on the release process, the divergence accounting and the known breakages. Read it before touching the pipeline.
