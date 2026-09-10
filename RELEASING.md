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

**Version numbers are this fork's own. They do not correspond to any `grafana.grafana` release.**

`indigo423.grafana 6.2.0` is not upstream's 6.2.0 and is not built from it.
Provenance is carried by the upstream commit each release is built from, which the pipeline records in every GitHub release, not by the version number.

Until 6.1.0 this fork mirrored upstream version numbers exactly.
That policy assumed upstream would merge and the fork would follow.
Upstream merged twice in 2026, the last time on 2026-05-22, while 32 pull requests sat open, so from 6.2.0 the fork carries selected contributions ahead of upstream on its own version line.

There is no technical collision if upstream later publishes the same number.
The namespaces differ, so the two artifacts are unrelated on Galaxy.
The hazard is a reader assuming equivalence, which is what this section and the release notes exist to prevent.

Galaxy versions are immutable.
A bad upload cannot be replaced, only superseded, and the bad artifact stays installable.
Everything expensive to get wrong is therefore checked before the publish step.

### What this fork carries

Run it, do not read it:

```bash
make carried-prs
```

```
  LOCAL     UPSTREAM  PR       AUTHOR                 STATE
  ------------------------------------------------------------------------
  3ca217c8  0be20b4f  #510     Ronny Trommer          open, still carried
  97df8649  5b0a2483  #534     Luc                    open, still carried
  ...
```

The carried set is derived from git history, not maintained as prose, because prose that must be updated by hand is prose that will be wrong.
Every carried commit records its origin through `git cherry-pick -x`, so the set is discoverable and each pull request's current state is checkable.

`make carried-prs` reports the size of the divergence and flags anything upstream has merged as droppable.
If that number never falls, upstream is dead and this fork should be renamed and take its own direction, which is a decision to make explicitly rather than to drift into.

### Carrying an upstream contribution

```bash
git fetch upstream "refs/pull/<N>/head:refs/remotes/upstream/pr/<N>"
git log --no-merges --reverse upstream/main..upstream/pr/<N>   # find the substantive commits
git cherry-pick -x -s <sha>
```

Rules, in order of importance:

1. **Preserve authorship.** `cherry-pick` keeps the contributor as author and makes you the committer. That split is correct: they wrote it, you vouch for it. GitHub attributes by author, so contributors keep visible credit.
2. **Never amend a contributor's commit.** If a contribution fails a gate, fix it in a separate commit of your own. Amending someone's commit while leaving their name on it attributes a change they did not make.
3. **`-x` is required.** The recorded upstream SHA is what makes `make carried-prs` and the drop-on-merge lifecycle work at all.
4. **Sign off only on your own behalf.** `-s` adds *your* `Signed-off-by`, certifying under the DCO that you received the work under a compatible licence and are passing it on with its origin recorded. Never add a `Signed-off-by` for a contributor who did not give one; that trailer is a certification by a named person. Preserve theirs where it exists.
5. **Skip merge commits.** Contributors often sync their branch into the pull request. Use `--no-merges`.
6. **For your own commits that already carry a sign-off, use `-x` alone.** `-s` would duplicate the trailer.
7. **Read the contribution.** Applying cleanly is not evidence of correctness. See the rejected candidates below.

### Ordering that is not obvious

- **`#461`** has two substantive commits that must be applied chronologically (`2f08825`, then `e6cecc1`). Reversed, the second conflicts.
- **`#534` and `#538` conflict in either order.** Both touch the same region of `roles/grafana/tasks/install.yml`: `#538` adds a `module_hotfixes: true` parameter whose diff context includes the `when:` line that `#534` rewrites. Resolve by hand, keeping both changes, and record the resolution in a committer's note on the carried commit.

### After an upstream merge, drop what was absorbed

```bash
git fetch upstream
git merge upstream/main
make carried-prs          # anything reported MERGED upstream is now redundant
git revert <local sha>    # or drop the commit while rebasing
```

This is the loop that keeps the divergence bounded. Skipping it is how a curated downstream becomes an accidental hard fork.

### Verifying the divergence

The tarball contains only collection content, so the divergence is checkable against the upstream commit the release was built from:

```bash
make dist
tar -xzf build/dist/indigo423-grafana-6.2.0.tar.gz -C ours/

git archive <upstream base commit> | tar -x -C up/

# undo the rename, then diff
grep -rIli indigo423 ours/ | while IFS= read -r f; do
  perl -pi -e 's/\bindigo423\.grafana\b/grafana.grafana/g;
               s/^namespace: indigo423$/namespace: grafana/;
               s/^title: Indigo423\.Grafana$/title: Grafana.Grafana/' "$f"
done

diff -rq -x MANIFEST.json -x FILES.json -x galaxy.yml up/ ours/
```

`MANIFEST.json` and `FILES.json` are per-build metadata and always differ.
`galaxy.yml` is excluded because the build consumes it: the tarball carries `MANIFEST.json` instead, so it always shows as present only upstream.

Every differing file must be attributable to a carried contribution or to a documented maintainer change.
Anything else is a bug in the rename or an unintended edit, and this diff is how you find it.

**The rename itself contributes nothing.** Applied to an unmodified upstream tree and then inverted, it produces no difference. That property held through 6.1.0, where the diff against upstream's published artifact was empty, and it is worth re-checking whenever the rewrite rule changes.

### Why the maintainer's own fixes exist

`ansible-test sanity` fails on upstream 6.1.0 with 3 of 34 tests red (`pep8`, `validate-modules`, `yamllint`), inherited rather than caused by the rename.
The defects are real, not strictness artifacts: `plugins/modules/user.py` had an unterminated quote making `EXAMPLES` invalid YAML, an `orgid` parameter present in `argument_spec` but absent from the documentation, `state` choices that omitted the implemented `update_password`, and an author field that did not match the `Name (@handle)` form every other module uses.

They are fixed here so `sanity` can stay a real blocking gate rather than being skipped or suppressed with `tests/sanity/ignore-*.txt`.
All of it is upstreamable and should be sent to `grafana/grafana-ansible-collection`, after which the local divergence can be dropped.

### Candidates that were rejected

Recorded so the reasoning is not repeated:

| PR | Why not |
|---|---|
| `#525` | "Fixes" the dashboards loop by listing a string into its characters. Newest of four competing fixes and the worst. |
| `#504`, `#439` | Correct enough but superseded by `#448`, which fixes the regex explicitly. |
| `#527` | Competes with `#534` on the same `grafana_rhsm_*` conditions; assumes the variables are defined. |
| `#528` | Good idea, broken code: `register`, `retries` and `delay` are indented inside the `uri:` module arguments, and the URL is missing `://`. |
| `#433` | A 1408-line, 25-file new Pyroscope role. That is adopting a feature, not carrying a fix. |
| `#529`, `#462`, `#463` | Features, deferred. Untested for clean application. Candidates for a later release. |

## Releases are cut from `main`

Since 6.2.0 releases are cut from `main`, which carries both the pipeline and the curated contributions.

This was not always true. 6.1.0 mirrored upstream's 6.1.0 and therefore had to be cut from a `release/6.1.0` branch based on tag `6.1.0` (`39f1373`), because a tag-triggered workflow runs the workflow file **as it exists at the tagged commit**, and that commit predated the pipeline entirely: pushing `v6.1.0` there produced no run, no error and no notification.

That constraint disappeared with the mirror policy. It is recorded because the underlying trap has not: **a tag pushed at a commit without a tag-triggered `release.yml` does nothing at all, silently.** If you ever tag an older commit, check that `release.yml` exists there first.

## When the rewrite count changes

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
- A `GALAXY_API_KEY` secret holding a Galaxy API token for that namespace.
  An organisation secret with `visibility: all` works and is what this repository uses; a repository secret works too.
  The publish job fails with a clear message if it is missing.

## Deferred

- The three feature pull requests deferred from 6.2.0 (`#529`, `#462`, `#463`), untested for clean application.
- Cosign signatures on the GitHub release tarball.
  Galaxy does not consume them, so they would cover the GitHub artifact only.
