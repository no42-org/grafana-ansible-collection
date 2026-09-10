# Releasing

This fork publishes to the [`indigo423`](https://galaxy.ansible.com/ui/namespaces/indigo423/) namespace on Ansible Galaxy, as `indigo423.grafana`.

Upstream is [`grafana/grafana-ansible-collection`](https://github.com/grafana/grafana-ansible-collection), which publishes `grafana.grafana`.

## How the namespace works

The working tree says `grafana.grafana` everywhere, in all 51 files that hold the fully-qualified collection name.
It is renamed to `indigo423.grafana` at build time, in a copy under `build/src`, never in the tree.

That is deliberate.
Every one of those lines is a line upstream also touches, so rewriting them in the tree would make `git merge upstream/main` conflict on roughly 40 files, permanently.
Renaming in a copy pays the cost once.

```text
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

```text
push tag v<version>
  │
  ├─ verify-version   tag minus "v" == galaxy.yml version
  │
  ├─ gate             .github/workflows/gate.yml    ┐
  │    ├─ lint-release   make ci-lint-release       │ parallel
  │    ├─ lint           make ci-lint-{shell,yaml,  │
  │    │                   editorconfig,ansible}    │
  │    └─ sanity         ansible-test sanity        ┘
  │                        stable-2.17, stable-2.18   blocking
  │                        devel                       advisory
  │
  ├─ build            make dist → artifact
  │
  ├─ smoke            install the artifact, resolve indigo423.grafana.*
  │
  ├─ publish          ansible-galaxy collection publish, waits for import
  │
  └─ release          GitHub release, tarball attached
```

The gate is a `workflow_call` workflow, and `ci.yml` calls the same file on every push and pull request to `main`.
That is deliberate: **"what must pass" has one definition.**
Before it existed, `lint.yaml` gated pull requests while `release.yml` defined its own lint and sanity, and nothing kept them in agreement — the drift that matters being a release publishing through a weaker gate than pull requests enforce.

A reusable workflow does not inherit its caller's `env:`, so the source namespace and collection name arrive as inputs.
`ansible-test` needs the collection at `ansible_collections/<namespace>/<name>`, and the tree is unrenamed at that point, so those are the source names rather than the Galaxy ones.

## Rehearsing the pipeline

The pipeline can be exercised end-to-end on a **prerelease** tag, which costs nothing a user can trip over.

```bash
# on a branch, because main is protected
git switch -c release/6.3.0-rc1
# galaxy.yml: version: 6.3.0-rc1
git commit -s -m "chore(release): v6.3.0-rc1"
gh pr create --fill        # merge once the gate is green
git switch main && git pull
git tag -s v6.3.0-rc1 -m "release 6.3.0-rc1 (pipeline rehearsal)"
git push origin v6.3.0-rc1
```

A SemVer prerelease carries a hyphen after the patch number. `verify-version` derives a `prerelease` output from that, and the release job passes both `prerelease` and `make_latest` to `action-gh-release`, so the RC does not take over **Latest release** on the repository page.

`ansible-galaxy` excludes prereleases from resolution unless `--pre` is passed. Do not trust Galaxy's `highest_version` field for this — it reports the RC. Check the client instead:

```bash
ansible-galaxy collection install indigo423.grafana -p /tmp/x   # -> 6.2.0
ansible-galaxy collection install indigo423.grafana:6.2.1-rc1 -p /tmp/y
```

The rehearsal at `v6.2.1-rc1` is what found the missing `prerelease` input: without it a `v6.3.0-rc1` tag would have created a normal release and moved **Latest release** to a release candidate — the first thing a reader uses to decide what to install. That defect could not have surfaced on a plain version, which is the argument for rehearsing on a throwaway tag rather than letting the next real release be the test.

What it confirmed, in order:

```text
  verify-version   tag == galaxy.yml, prerelease=true
  gate             lint-release, lint, sanity (devel advisory and red)
  build            indigo423-grafana-6.2.1-rc1.tar.gz
  smoke            installed, indigo423.grafana.* resolved
  publish          accepted by Galaxy
  release          GitHub release, marked Pre-release, 6.2.0 still Latest
```

**`galaxy.yml` keeps the last released version between releases**, so it reads `6.2.1-rc1` after a rehearsal. The next real release bumps it to a plain version.

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

```text
  LOCAL     UPSTREAM  PR       AUTHOR                 STATE
  ------------------------------------------------------------------------
  3ca217c8  0be20b4f  #510     Ronny Trommer          open, still carried
  97df8649  5b0a2483  #534     Luc                    open, still carried
  ...
```

The carried set is derived from git history, not maintained as prose, because prose that must be updated by hand is prose that will be wrong.
Every carried commit records its origin through `git cherry-pick -x`, so the set is discoverable and each pull request's current state is checkable.

`make carried-prs` flags anything upstream has merged as droppable.

**It is not the whole inventory.** It enumerates commits carrying a `cherry picked from` line, so it sees upstream-origin work only. Three other kinds of divergence are invisible to it: maintainer fixes to inherited files, fork infrastructure, and contributions that land here with no upstream pull request behind them — which is where contributions now go, since upstream's maintainership is dormant. The total accounting is the file-level diff under **Verifying the divergence** below, where every differing file must map to a carried contribution, a maintainer change, or an accepted fork-origin contribution.

Two signals worth watching, both of which point at the same decision:

- the carried count never falling, because nothing this fork carries is ever merged upstream;
- fork-origin changes coming to outnumber carried ones.

Either means the fork has stopped being a curated view of upstream's queue and become its own project. That is a decision to take explicitly, including renaming it, rather than to drift into.

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
8. **Keep it adoptable.** Nothing here is submitted upstream, so adoptability has to survive by construction: one purpose per commit so each can be taken independently, no reformatting or opportunistic tidying of inherited files, and `roles/*/molecule/` left byte-identical. A change upstream could apply unchanged is the goal; a change bundled with three unrelated edits is not.

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

Every differing file must be attributable to one of exactly three things:

1. a **carried contribution** — an upstream pull request cherry-picked here, listed by `make carried-prs`
2. a **maintainer change** — a fix or infrastructure change made here, documented below
3. an **accepted fork-origin contribution** — a change contributed directly to this repository, with no upstream pull request behind it, which is where contributions now go

Anything else is a bug in the rename or an unintended edit, and this diff is how you find it.
`git log --format='%h %an | %s' <upstream base commit>..HEAD -- <path>` names the commit for each differing file, which is the attribution.

At 6.2.0 the diff was 13 files, every one attributable: 3 to the release commit (`CHANGELOG.rst`, `changelogs/changelog.yaml`, `meta/runtime.yml`), 5 to carried contributions, 5 to maintainer changes, and none to category 3 — nothing has been contributed here yet.
The `Only in up:` entries are the repository-only files `build_ignore` keeps out of the tarball, and are expected.

**When category 3 outnumbers category 1, this is no longer a curated downstream.**
A fork whose divergence is mostly its own work is its own project, and should be named and documented as one rather than continuing to describe itself as a curation of upstream.
That is the signal to watch; it is a rename and a re-framing, not a failure.

**The rename itself contributes nothing.** Applied to an unmodified upstream tree and then inverted, it produces no difference. That property held through 6.1.0, where the diff against upstream's published artifact was empty, and it is worth re-checking whenever the rewrite rule changes.

### Why the maintainer's own fixes exist

`ansible-test sanity` fails on upstream 6.1.0 with 3 of 34 tests red (`pep8`, `validate-modules`, `yamllint`), inherited rather than caused by the rename.
The defects are real, not strictness artifacts: `plugins/modules/user.py` had an unterminated quote making `EXAMPLES` invalid YAML, an `orgid` parameter present in `argument_spec` but absent from the documentation, `state` choices that omitted the implemented `update_password`, and an author field that did not match the `Name (@handle)` form every other module uses.

They are fixed here so `sanity` can stay a real blocking gate rather than being skipped or suppressed with `tests/sanity/ignore-*.txt`.
All of it is written to stay **applicable** upstream, but it is deliberately not submitted.

Upstream's maintainership is dormant: the last merge to `main` was 2026-05-22, the last release 2026-04-27, and 32 pull requests sit open, several for over a year. The community is alive — issues and comments continue — but nobody is draining the queue, so adding to it costs effort and buys nothing.

The posture is therefore *keep it adoptable, do not push it*. Every change stays small, single-purpose and separable; carried commits keep their original authors and a `cherry picked from` line; upstream files are not reformatted; and nothing under `roles/*/molecule/` is touched.

**This policy has a premise, and the premise is checkable.** If `make carried-prs` ever reports something as merged upstream, maintainership has resumed and the decision not to submit should be re-examined rather than inherited. That is the one event that would change the answer.

### Candidates that were rejected

Recorded so the reasoning is not repeated:

| PR | Why not |
| --- | --- |
| `#525` | "Fixes" the dashboards loop by listing a string into its characters. Newest of four competing fixes and the worst. |
| `#504`, `#439` | Correct enough but superseded by `#448`, which fixes the regular expression explicitly. |
| `#527` | Competes with `#534` on the same `grafana_rhsm_*` conditions; assumes the variables are defined. |
| `#528` | Good idea, broken code: `register`, `retries` and `delay` are indented inside the `uri:` module arguments, and the URL is missing `://`. |
| `#433` | A 1408-line, 25-file new Pyroscope role. That is adopting a feature, not carrying a fix. |
| `#529`, `#462`, `#463` | Features, deferred. Untested for clean application. **6.3.0 candidates** — see Deferred. |

## Releases are cut from `main`

Since 6.2.0 releases are cut from `main`, which carries both the pipeline and the curated contributions.
`main` is protected — see [Branch protection on `main`](#branch-protection-on-main) below for what that means for the version-bump commit.

This was not always true. 6.1.0 mirrored upstream's 6.1.0 and therefore had to be cut from a `release/6.1.0` branch based on tag `6.1.0` (`39f1373`), because a tag-triggered workflow runs the workflow file **as it exists at the tagged commit**, and that commit predated the pipeline entirely: pushing `v6.1.0` there produced no run, no error and no notification.

That constraint disappeared with the mirror policy. It is recorded because the underlying trap has not: **a tag pushed at a commit without a tag-triggered `release.yml` does nothing at all, silently.** If you ever tag an older commit, check that `release.yml` exists there first.

## Branch protection on `main`

`main` is protected, with **administrator bypass permitted**.

```text
  required checks     Gate / Lint release machinery
                      Gate / Lint the collection
                      Gate / Sanity (Ⓐstable-2.17)
                      Gate / Sanity (Ⓐstable-2.18)
  enforce_admins      false      ← the bypass
  strict              false      ← branches need not be rebased onto main first
  force pushes        blocked
  deletions           blocked
  conversation resolution  required
```

`Gate / Sanity (Ⓐdevel)` is deliberately **not** required. It is advisory — `continue-on-error: true`, because it tracks unreleased `ansible-core` and breaks for reasons unrelated to this collection — so it reports as a failed check while the workflow succeeds. Requiring it would block every merge on an advisory job.

`strict: false` for the same kind of reason: on a single-maintainer repository, requiring every branch to be rebased onto `main` before merging buys little and costs a rebase for every unrelated push.

### The bypass is a trade, stated

What it buys is that a solo project is never blocked by its own gate being wrong, mis-configured, or slow at an inconvenient moment.
What it gives up is the guarantee: the person most likely to push a broken release is also the person holding the bypass, so protection is a strong default rather than an enforced invariant.

That is acceptable here for two reasons. The gate's value in a solo project is catching mistakes, not preventing deliberate action, and a bypass does not weaken that. And the irreversible step is publishing to Galaxy, which is gated **inside** `release.yml` — `verify-version`, the whole gate, and the smoke test all run before `publish`, and no bypass of branch protection skips any of them.

**Use the bypass visibly, not habitually.** If it becomes the normal path, the protection is decoration and should either be removed or made strict (`enforce_admins: true`).

### The version bump normally lands by pull request

The release procedure's `chore(release): vX.Y.Z` commit is a change to `galaxy.yml` and the changelog, so it goes through a pull request like anything else, and the tag is pushed at the merged commit.

```bash
git switch -c release/6.3.0
# bump galaxy.yml, changelogs/
git commit -s -m "chore(release): v6.3.0"
git push -u origin release/6.3.0
gh pr create --fill
# merge once the gate is green, then
git switch main && git pull
git tag -s v6.3.0 -m "release 6.3.0"
git push origin v6.3.0
```

Direct pushes to `main` still work, because of the bypass. That is the case the bypass exists for — a version bump where a pull request would be pure ceremony — but it should be a decision each time, not the default.

## Role tests

Roles are tested against containers by a harness that depends only on
`ansible-core` and `docker`. Three phases, in order:

```bash
make role-test ROLE=grafana DISTRO=rhel
make role-test-list            # roles and distro families
```

| Phase | What it proves |
| --- | --- |
| converge | the role applies to a fresh container |
| idempotence | applying it again changes nothing |
| verify | the expected end state, asserted in Ansible |

Idempotence is the phase that earns its keep. Converge proves a role runs; idempotence proves it is a correct Ansible role, and it is the one thing converge cannot see. It found a real defect on the first role it ran: `Copy dashboard files` declared `owner: root` while its own handler set `owner: grafana`, so every run reported changes forever.

`DISTRO` is a **family**, not a distribution:

```text
  debian  ->  dokken/ubuntu-22.04
  rhel    ->  dokken/almalinux-9
```

The `rhel` entry is not symmetry. The `grafana` role's `yum`/`dnf` block, and the carried contributions inside it (`#534`, `#538`), sit behind `ansible_facts['pkg_mgr'] in ['yum','dnf']` and are unreachable on Debian. Without it, two of the carried fixes ship unexecuted.

A role may declare a topology in `tests/roles/<role>/topology`:

```text
NODES=3         # how many role containers
NETWORK=1       # a private network so nodes and sidecars resolve by name
```

and start sidecars from `tests/roles/<role>/sidecars.sh`. `mimir` uses both: three nodes with memberlist gossip plus a MinIO object store. Everything a run creates carries one Docker label, so cleanup is exhaustive without enumerating it.

`grafana_dashboards_dir` is a **control-node** path, because the role's discovery tasks are `delegate_to: localhost`. It must be absolute and fully resolved: `#448` strips it as a literal regular expression prefix, so a `..` segment produces folder names like `Users/…/team-a`.

### What is covered

| Role | debian | rhel | Note |
| --- | --- | --- | --- |
| `grafana` | ✅ | ✅ | carries `#510`, `#448`, `#534`, `#538` |
| `opentelemetry_collector` | ✅ | ✅ | carries `#475` |
| `mimir` | ✅ | ✅ | carries `#461`; three nodes plus MinIO |
| `alloy` | ✅ | ✅ | |
| `loki` | ✅ | ✅ | |
| `promtail` | — | — | see below |
| `tempo` | — | — | see below |
| `grafana_agent` | — | — | superseded upstream by `alloy`; never had a scenario |

Two roles still cannot install their software with default settings. Both are inherited, both are the same shape — a role building URLs or config from templates that upstream has since outgrown — and neither was ever executed, which is why neither was noticed. `loki` on RHEL was the third and is now fixed:

- **`loki` on RHEL — fixed.** The role built `loki-<version>.<arch>.rpm`, but Grafana added an RPM release number from **3.7.5** on, so the default `latest` 404s against any current release. `loki_download_url_rpm` now applies the `-1` suffix by version, because pinning an older `loki_version` still needs the old name. The `.deb` assets never changed, which is why only RHEL broke. `loki`/`rhel` is back in the role-test matrix and passes.
- **`promtail`.** Grafana stopped shipping promtail packages after Loki v3.6.0; v3.7.7 has zero promtail assets, so `latest` 404s everywhere. `promtail-molecule.yml` is kept manual-only rather than replaced, because there is nothing to replace it with until the role is fixed or retired.
- **`tempo`.** The role's own default `tempo_metrics_generator` emits a `traces_storage` field that Tempo 3.0.3 rejects (`field traces_storage not found in type generator.Config`), so Tempo crash-loops and the role's own readiness check fails.

None ships a test. A test that cannot pass is worse than no test, and overriding the defaults in a test would hide that the defaults are what is broken.

### The dormant Molecule scenarios

`roles/*/molecule/` is **inherited, shipped, and never invoked.** Those scenarios are byte-identical to upstream and deliberately so: editing them would cost merge surface on every upstream merge, and leaving them untouched means Molecule can be re-adopted without anything having been destroyed.

They are not what runs. `make role-test` is.

Molecule was replaced rather than pinned because pinning would have cost four scenario-file edits — `network` and `network_mode` in `mimir`, `cgroup_parent` in four `opentelemetry_collector` scenarios, and content for two `grafana` scenario files that are empty documents — in exactly the files this fork keeps identical to upstream. The two failures that prompted it were unrelated to each other: Mimir pinned `ansible-core==2.16` against `python-version: '3.x'`, which resolved to Python 3.14 and died at import before reading any config, and the scenario files use platform keys current Molecule rejects.

## When the rewrite count changes

The rename asserts an exact count, so an upstream change to the FQCN references fails the build rather than silently half-renaming.

```text
$ make dist
[error] expected 83 rewrites, performed 85
[error] upstream likely changed the FQCN references; run:
[error]   ./tools/rename-namespace.sh --expected-count
```

Re-derive the number:

```bash
./tools/rename-namespace.sh --expected-count
```

```text
total occurrences      : 91
community.grafana.*    : 2  (must remain untouched)
in excluded changelogs : 6  (not rewritten)
expected rewrites      : 83
```

Read the diff before updating `EXPECTED_REWRITES` in `tools/rename-namespace.sh`.
The count moving is the symptom; the cause may need the rewrite rule changed rather than the number bumped.

In particular, watch for new `community.grafana.*` references.
`community.grafana.grafana_datasource` contains `grafana.grafana` as a substring:

```text
community.grafana.grafana_datasource
          └──────┬──────┘
          matches "grafana.grafana"
```

A naive substitution turns that into `community.indigo423.grafana_datasource`, a collection that does not exist.
The two current occurrences are in runtime code, `roles/grafana/tasks/datasources.yml` and `dashboards.yml`, where no build step would notice.
The rewrite guards against it with a negative lookbehind, and both the script and the smoke job assert those references survive.

## Linting

**The lint gates gate.** That sentence was false until `honest-ci-gates`, and the correction is worth knowing because two wrong conclusions were drawn from it before it was diagnosed.

`tools/lint-yaml.sh` and `tools/lint-ansible.sh` both ended on

```bash
if [[ "$sourced" == "1" ]]; then
  return "$statusCode"
fi
```

`make ci-lint-*` executes these scripts rather than sourcing them, so `sourced=0`, the closing `if` evaluates false, and in bash a false `if` with no `else` yields exit status **0**.
Both reported success while their linter printed errors.
CI run `34446534704` showed **61 error annotations on a step whose conclusion was `success`**.

Two claims previously recorded here were also wrong, and are corrected rather than deleted so they are not reinstated:

| Claim | Why it was wrong |
| --- | --- |
| "62 error-level findings, and the Lint workflow has been failing for months" | The workflow was *passing*, over the findings. The local run that looked red had bailed at the pipenv guard, because `Pipfile` pins `python_version = "3.10"` and that interpreter was absent. |
| "Bringing it green would mean editing the files this fork keeps identical to upstream, manufacturing conflicts" | It cost **four newly-diverging files of whitespace.** 56 of the 61 errors were in files already diverged, 52 of those in `changelogs/changelog.yaml` alone. |

The findings are fixed. On a clean checkout the enabled linters report zero errors: `yamllint` 0, `ansible-lint` 0 failures and 0 warnings on 212 files against the `production` profile, `editorconfig-checker` 0, `shellcheck` clean.

### What each target is for

| Target | Covers | Needs |
| --- | --- | --- |
| `make ci-lint-release` | `tools/*.sh`, every workflow's hygiene, `galaxy.yml`, `dependabot.yml` | `shellcheck`, `yamllint`, `actionlint`, `zizmor` |
| `make ci-lint-{shell,yaml,editorconfig,ansible}` | the collection itself | `make install` — pipenv **and** `node_modules` |
| `make ci-lint` | the above plus the disabled `markdown` and `text` steps | as above |

Both sets gate a release, in separate jobs of `gate.yml`. The split is a division of labour, not a gap: `ci-lint-release` needs no pipenv and no `node_modules`, so it runs in seconds locally and catches the release machinery, while the collection lint set needs the full toolchain.

**Markdown and text linting are enabled**, for the first time. Both were commented out in the workflow `gate.yml` replaced, so until now the prose this fork authors had never been linted — which is most of what it owns.

They are scoped to fork-authored documents. The top-level `README.md` that Galaxy renders, the role READMEs and `examples/` are excluded, and it is the same reasoning that keeps `roles/*/molecule/` untouched: they are upstream's documents, and bringing them to this configuration means 172 findings of table style, fence languages and list spacing across files upstream still edits. That is a whitespace sweep of someone else's prose. The trade is real — those documents ship in the collection and go unlinted — and if upstream maintainership resumes the right move is to offer the fixes there.

Two rules are turned off, both on the rule's merits rather than its count:

| Rule | Why |
| --- | --- |
| `MD013` line-length | This project's Markdown style is one sentence per line, never hard-wrapped at a column. A 150-column limit enforces the opposite, so keeping both would have the gate demand every document be rewritten against its own stated style. 139 findings. |
| `MD041` first-line-h1 | `CLAUDE.md` is one line, `@AGENTS.md`, a tool import directive rather than a document; `.github/pull_request_template.md` renders inside GitHub's own form and starts at h2 by convention. A rule both have to be exempted from is not enforcing anything. |

`MD030` was changed from the inherited `3/2/3/2` to `1/1/1/1`. The file described those values as the defaults and they are not — markdownlint's default is 1 — and the inherited READMEs are themselves mixed, with `README.md` carrying 13 three-space list items and 9 one-space.

`textlint`'s `no-todo` rule and its package are removed: it fired on eight `- [ ]` checkboxes in the pull request template, where an unchecked box is the template working.

### Two linter traps

**`editorconfig-checker@5.0.1` ships no `darwin-arm64` binary and exits 0 when it cannot find one.** `tools/lint-editorconfig.sh` therefore propagated a zero meaning "the tool did not run". Use the standalone Go binary to measure locally.

**`ansible-lint` installs the dependency collections itself, into the tree.** Locally that is `.ansible/collections/`; in CI, because `ansible.cfg` sets `collections_paths = ./`, it is `ansible_collections/` in the repository root. Both are now ignored. Before that, the first honest CI run failed on **4851 findings, every one of them in `ansible.posix` or `community.general`** and none in this repository. `.ansible/` also took `make dist`'s rename count from 83 to 174.

### Two rules are skipped, with reasons

Neither is skipped for producing too many findings, which is not an acceptable reason.

- **`var-naming[no-role-prefix]`**, 22 findings, 20 in `roles/opentelemetry_collector/defaults/main.yml`. The rule wants `otel_collector_receivers` renamed to `opentelemetry_collector_receivers`. Those are the role's **public interface**: renaming breaks every playbook that sets them. That is a major version bump with a deprecation path, not a lint fix.
- **`roles/*/molecule/`**, 2 findings. Byte-identical to upstream by rule — see [The dormant Molecule scenarios](#the-dormant-molecule-scenarios). Editing it to satisfy a linter would break a stated invariant for two cosmetic findings.

`tools/lint-release.sh` also asserts that every `tools/lint-*.sh` exits with its captured status, and names the offender if not. Explicit rather than delegated to `shellcheck`, which has no check for this: the pattern is valid bash doing exactly what it says, and the defect is that what it says is not what the caller needs.

## Prerequisites

### Toolchain

```bash
brew install uv node shellcheck docker
corepack enable          # yarn, at the version package.json pins
make install             # provisions both toolchains
```

| Tool | Provides | Pinned by |
| --- | --- | --- |
| `uv` | `yamllint`, `ansible-lint` | `pyproject.toml` + `uv.lock` |
| `corepack` + `yarn` | `markdownlint-cli2`, `textlint` | `package.json` `packageManager` + `yarn.lock` |
| `shellcheck` | shell linting | version-pinned download in CI; whatever is installed locally |
| `docker` | role tests, `ansible-test sanity --docker` | — |
| downloaded on first use | `editorconfig-checker` | `tools/includes/editorconfig-checker.sh` |

**`make install` no longer depends on a specific Python.** It used to: `Pipfile` pinned `python_version = "3.10"`, and without that exact interpreter pipenv failed, every Python linter bailed at its guard, and the output looked like failing lint. `uv` provisions its own interpreter from `pyproject.toml`'s `requires-python`.

`ansible-core` is pinned to `>=2.18,<2.19` in the lint group on purpose: `ansible-lint` judges a collection against whatever `ansible-core` is installed, and unconstrained `uv` resolved 2.21.4 — four minors past what the release gates on.

### Release

- The `indigo423` namespace on Galaxy, owned by the publishing account.
- A `GALAXY_API_KEY` secret holding a Galaxy API token for that namespace.
  An organisation secret with `visibility: all` works and is what this repository uses; a repository secret works too.
  The publish job fails with a clear message if it is missing.

## Deferred

- **6.3.0 candidates:** the three feature pull requests deferred from 6.2.0 — `#529` (OpenTelemetry Collector extra args), `#462` (Mimir target), `#463` (Mimir multitenancy). None was test-applied, and `#462`/`#463` touch the same Mimir files, so they need sequencing like `#534`/`#538` did.
- Cosign signatures on the GitHub release tarball.
  Galaxy does not consume them, so they would cover the GitHub artifact only.
