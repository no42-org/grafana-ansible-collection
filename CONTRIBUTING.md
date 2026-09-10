# Contributing

Contributions are welcome, and **they belong here.**

You do not need to open anything upstream first. More on why below, so you can judge for yourself rather than take it on trust.

## Where to send a change

**Here.** Open an issue, or a pull request against `main` of this repository.

A change that lands only here is accepted and expected. It is not provisional, not a holding pattern, and not waiting on anyone else's review. This fork releases; that is what it is for.

**Filing upstream as well is optional and useful.** [`grafana/grafana-ansible-collection`](https://github.com/grafana/grafana-ansible-collection) is where most of this code comes from, and a fix that lands there eventually reaches everyone rather than only users of this fork. If your change is to role or module behaviour, that is a genuinely good thing to do.

But it is your call, not a prerequisite, and here is the situation as of September 2026:

```text
  last merge to upstream main     2026-05-22   (~4 months)
  last upstream release           2026-04-27   6.1.0
  open upstream pull requests      32          several over a year old
  open upstream issues             90
  community                        active — issues and comments continue
```

Upstream's community is alive; its maintainership is dormant. This fork does not submit changes upstream either, for the same reason, so it would be poor form to ask you to file into a queue we decline to file into ourselves. If upstream revives, `make carried-prs` is what notices, and the policy gets revisited.

## Two commit trailers, both required

### Sign-off (DCO)

Every commit needs a `Signed-off-by` line from a real human identity:

```bash
git commit -s -m "fix(grafana): …"
```

That produces:

```text
Signed-off-by: Your Name <you@example.com>
```

It certifies the [Developer Certificate of Origin](https://developercertificate.org/): that you wrote the change, or received it under a compatible licence, and have the right to submit it. This collection is GPL-3.0-or-later.

Sign off **only on your own behalf.** Never add a `Signed-off-by` for someone else — that trailer is a certification by a named person, and a forged one is worse than a missing one.

### AI assistance

If a commit was written with AI assistance, say so:

```text
Assisted-by: ClaudeCode:claude-opus-5
```

Format is `AGENT_NAME:MODEL_VERSION`. Tools used may follow.

This is disclosure, not a warning label — AI-assisted contributions are welcome here. But the human who signs off remains responsible for reviewing the change and for licence compliance. "The model wrote it" is not a defence for a bad patch, and the trailer makes the provenance legible instead of guessable.

## Conventional commits

```text
<type>[optional scope]: <description>
```

`feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`, `ci`, `build`, `revert`. Breaking changes append `!` or add a `BREAKING CHANGE:` footer.

```text
fix(grafana): set chdir so grafana-cli finds its homepath
test: cover the mimir role on both package families
```

## Keep changes adoptable

This is the one convention that is unusual, and it exists because most of the code here is upstream's.

Even though nothing is submitted upstream, changes are written so upstream **could** take them unchanged if its maintainership resumes. In practice:

- **One purpose per commit.** A fix bundled with three unrelated edits cannot be adopted independently.
- **Do not reformat inherited files.** No opportunistic tidying, no whitespace sweeps, no reflowing YAML you happened to be reading. Change what you came to change.
- **Do not touch `roles/*/molecule/`.** Those scenarios are byte-identical to upstream and deliberately dormant. See [RELEASING.md](RELEASING.md).
- **Do not rename the collection.** The working tree says `grafana.grafana` everywhere; the rename to `indigo423.grafana` happens at build time and is asserted by an exact count. If your change alters the number of fully-qualified names, `make dist` will fail and tell you.

## Before you open a pull request

```bash
make ci-lint-release            # lint the release machinery
make role-test ROLE=<role> DISTRO=debian
make role-test ROLE=<role> DISTRO=rhel
make dist                       # build the collection, incl. the rename assertion
```

If you changed a role, run its role test on both package families. `rhel` is not optional politeness — the `grafana` role's `yum`/`dnf` block is unreachable on Debian, so a Debian-only run can pass while the change is broken for half the users.

For module changes, `ansible-test sanity --docker` is what the release gates on.

Prerequisites: `docker`, `shellcheck`, and the Python lint toolchain via `make install`. Be warned that `make install` is currently fragile — see [RELEASING.md](RELEASING.md).

## Reporting bugs

[Open an issue.](https://github.com/no42-org/grafana-ansible-collection/issues) The forms will ask which role or module, which distribution family, and what you expected.

If the bug is in role or module behaviour, mentioning whether you have also checked upstream is helpful but not required.

For security problems, do **not** open an issue — see [SECURITY.md](SECURITY.md).

## What this fork will not take

- **New roles or large features.** This is a curated downstream, not a place to grow the collection. Those belong upstream, even in its current state.
- **Reformatting or style sweeps** of inherited files, for the adoptability reason above.
- **Changes that only make a test pass** by overriding a broken default rather than fixing it. A test that cannot fail is worse than no test; see the three known-broken roles in [RELEASING.md](RELEASING.md) for how that is handled instead.
