## What does this change?

<!-- One or two sentences. The "why" matters more than the "what". -->

Closes #

## Checklist

- [ ] Commits are signed off (`git commit -s`) — see [CONTRIBUTING.md](../CONTRIBUTING.md)
- [ ] AI-assisted commits carry an `Assisted-by:` trailer
- [ ] One purpose per commit, so this can be adopted independently
- [ ] No reformatting of inherited files, and `roles/*/molecule/` untouched
- [ ] `make ci-lint-release` passes
- [ ] If a role changed: `make role-test ROLE=<role> DISTRO=debian` **and** `DISTRO=rhel`
- [ ] If a module changed: `ansible-test sanity --docker` passes
- [ ] `make dist` succeeds (this also asserts the namespace rewrite count)

## Upstream

<!--
Optional. If this matches an upstream pull request or issue, give its number in backticks, such as `upstream 540`.
Do not link it, and do not write `grafana/grafana-ansible-collection#540`: either one adds an entry to upstream's timeline, and this fork writes nothing upstream.
`make carried-prs` does not read this field; it finds carried upstream pull requests from the `cherry picked from commit` trailer.
-->
