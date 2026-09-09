# Releasing

This fork publishes to the [`indigo423`](https://galaxy.ansible.com/ui/namespaces/indigo423/) namespace on Ansible Galaxy, as `indigo423.grafana`.

Upstream is [`grafana/grafana-ansible-collection`](https://github.com/grafana/grafana-ansible-collection), which publishes `grafana.grafana`.

## How the namespace works

The working tree says `grafana.grafana` everywhere, in all 51 files that hold the fully-qualified collection name.
It is renamed to `indigo423.grafana` at build time, in a copy under `build/src`, never in the tree.

That is deliberate.
Every one of those lines is a line upstream also touches, so rewriting them in the tree would make `git merge upstream/main` conflict on roughly 40 files, permanently.
Renaming in a copy pays the cost once.

```
main (grafana.grafana, == upstream)
  │
  ├── git merge upstream/main         clean, nothing to resolve
  │
  └── make dist
        └─ build/src   grafana.grafana → indigo423.grafana
              └─ build/dist/indigo423-grafana-<version>.tar.gz
```

The consequence to keep in mind: local `molecule` and `ansible-test` runs exercise `grafana.grafana`, while consumers install `indigo423.grafana`.
A rename bug would pass every test in the repository.
The release pipeline's smoke job exists to close that gap, by installing the built artifact and resolving the renamed names for real before anything is published.

## Cutting a release

Releases are triggered by pushing a **`v`-prefixed** tag.

```bash
git tag -s v6.1.0 -m "release 6.1.0"
git push origin v6.1.0
```

The prefix is required.
Upstream's tags are bare (`6.0.3` … `6.1.0`), they are already in this fork, and more arrive on every `git fetch upstream --tags`.
The workflow triggers on `v*` so that fetching upstream tags cannot fire a release.

The tag must agree with the `version` field in `galaxy.yml`.
The first job checks this and fails in seconds if it does not, before anything is built or published.

### Pipeline

```
push tag v<version>
  │
  ├─ verify-version   tag minus "v" == galaxy.yml version
  │
  ├─ lint             make ci-lint-release          ┐ parallel
  ├─ sanity           ansible-test sanity           ┘
  │                     stable-2.17, stable-2.18    blocking
  │                     devel                       advisory
  │
  ├─ build            make dist → artifact
  │
  ├─ smoke            install the artifact, resolve indigo423.grafana.*
  │
  ├─ publish          ansible-galaxy collection publish, waits for import
  │
  └─ release          GitHub release, tarball attached
```

## Version policy

Version numbers mirror upstream exactly.
`indigo423.grafana 6.1.0` contains what `grafana.grafana 6.1.0` contains.

Galaxy versions are immutable.
A bad upload cannot be replaced, only superseded, and the bad artifact stays installable.
Everything expensive to get wrong is therefore checked before the publish step.

Mirroring leaves no version number free for a fork-only change between two upstream releases.
The first time that is needed, the policy has to change; it is deliberately not decided in advance.

### Verifying the mirror

Because the tarball contains only collection content, the claim is checkable:

```bash
# our build
make dist
tar -xzf build/dist/indigo423-grafana-6.1.0.tar.gz -C ours/

# upstream's published artifact
curl -sfLO https://galaxy.ansible.com/api/v3/plugin/ansible/content/published/collections/artifacts/grafana-grafana-6.1.0.tar.gz
tar -xzf grafana-grafana-6.1.0.tar.gz -C up/

# undo the rename, then diff
grep -rIli indigo423 ours/ | while IFS= read -r f; do
  perl -pi -e 's/\bindigo423\.grafana\b/grafana.grafana/g;
               s/^namespace: indigo423$/namespace: grafana/;
               s/^title: Indigo423\.Grafana$/title: Grafana.Grafana/' "$f"
done

diff -rq -x MANIFEST.json -x FILES.json up/ ours/
```

`MANIFEST.json` and `FILES.json` are per-build metadata and always differ.
Upstream's tarball additionally ships repository scaffolding (`.github/`, `tools/`, `Makefile`, `Pipfile*`, `package.json`, `yarn.lock`, lint configs) that this fork's `build_ignore` excludes.

Beyond those, this fork carries a known set of intentional differences.
The rename itself contributes none: run against upstream's tree with only the rename applied, the diff is empty.
As of 6.1.0 the deliberate divergences are:

| File | Lines | Why |
|---|---|---|
| `README.md` | 6 | Fork notice |
| `plugins/modules/user.py` | 28 | `ansible-test sanity` fixes |
| `plugins/modules/cloud_stack.py` | 4 | `pep8` E501 |
| `roles/grafana/tasks/install.yml` | 2 | `yamllint` colon spacing |
| `roles/mimir/defaults/main.yml` | 1 | `yamllint` trailing blank line |

Anything outside that table is a bug in the rename or an unintended edit, and the diff is how you find it.

### Why the sanity fixes exist

`ansible-test sanity` fails on upstream 6.1.0 with 3 of 34 tests red (`pep8`, `validate-modules`, `yamllint`), and those failures are inherited, not caused by the rename.
The defects are real, not strictness artifacts: `plugins/modules/user.py` had an unterminated quote making `EXAMPLES` invalid YAML, an `orgid` parameter present in `argument_spec` but absent from the documentation, `state` choices that omitted the implemented `update_password`, and an author field that did not match the `Name (@handle)` form every other module in the collection uses.

They are fixed here so `sanity` can stay a real blocking gate rather than being skipped or ignored.
All four fixes are upstreamable and should be sent to `grafana/grafana-ansible-collection` as a pull request, after which the local divergence can be dropped on the next merge.

## Cutting a version whose upstream tag predates this pipeline

A tag-triggered workflow runs the workflow file **as it exists at the tagged commit**.

Tag `6.1.0` points at `39f1373`, which has no tag-triggered `release.yml`.
Pushing `v6.1.0` at that commit does nothing at all: no run, no error, no notification.

Use a release branch:

```bash
git checkout -b release/6.1.0 39f1373        # the commit tag 6.1.0 points at
git cherry-pick <pipeline commit>            # .github/, tools/, Makefile, galaxy.yml, .gitignore, .yamllint
make dist                                    # verify the mirror as above
git tag -s v6.1.0 -m "release 6.1.0"
git push origin v6.1.0
```

The pipeline commit only touches paths that `build_ignore` excludes, so the shipped content stays identical to upstream's.

Do not cut from `main` when mirroring a version.
At the time of writing, `main` carries `521b006` ("Add more configuration options"), which upstream's `6.1.0` tag does not, and it changes three `roles/loki` files.
Building `6.1.0` from `main` would publish that content under a number that does not contain it.

## After an upstream merge

The rename asserts an exact count, so an upstream change to the FQCN references fails the build rather than silently half-renaming.

```
$ make dist
[error] expected 83 rewrites, performed 85
[error] upstream likely changed the FQCN references; run:
[error]   ./tools/rename-namespace.sh --expected-count
```

Re-derive the number:

```bash
./tools/rename-namespace.sh --expected-count
```

```
total occurrences      : 91
community.grafana.*    : 2  (must remain untouched)
in excluded changelogs : 6  (not rewritten)
expected rewrites      : 83
```

Read the diff before updating `EXPECTED_REWRITES` in `tools/rename-namespace.sh`.
The count moving is the symptom; the cause may need the rewrite rule changed rather than the number bumped.

In particular, watch for new `community.grafana.*` references.
`community.grafana.grafana_datasource` contains `grafana.grafana` as a substring:

```
community.grafana.grafana_datasource
         └──────┬──────┘
        matches "grafana.grafana"
```

A naive substitution turns that into `community.indigo423.grafana_datasource`, a collection that does not exist.
The two current occurrences are in runtime code, `roles/grafana/tasks/datasources.yml` and `dashboards.yml`, where no build step would notice.
The rewrite guards against it with a negative lookbehind, and both the script and the smoke job assert those references survive.

## Linting

`make ci-lint` is **not** a release gate.
It is red on a pristine tree: 62 error-level `yamllint` findings in `roles/`, `changelogs/`, and `galaxy.yml`, plus `ci-lint-editorconfig`, all inherited from upstream, where the Lint workflow has been failing for months.

Bringing it green would mean editing `roles/`, `changelogs/`, and `examples/` — exactly the files this fork keeps identical to upstream so merges stay clean.
That would manufacture the conflicts the build-time rename exists to avoid.

The release gate is `make ci-lint-release`, scoped to what this repository owns:

- `tools/*.sh` under `shellcheck`
- `.github/workflows/release.yml` under `yamllint`, and `actionlint` when installed
- `galaxy.yml` and `.github/dependabot.yml` checked for valid YAML and required fields, not style

`make ci-lint` is unchanged and still runs on pull requests.

## Prerequisites

- The `indigo423` namespace on Galaxy, owned by the publishing account.
- A `GALAXY_API_KEY` repository secret holding a Galaxy API token for that namespace.
  The publish job fails with a clear message if it is missing.

## Deferred

- `meta/runtime.yml` declares `requires_ansible: ">=2.12.0,<3.0.0"` while sanity covers only currently supported branches.
  The claim is inherited from upstream and overstates what is tested.
- Cosign signatures on the GitHub release tarball.
  Galaxy does not consume them, so they would cover the GitHub artifact only.
