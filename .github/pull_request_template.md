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
Optional. Most code here is upstream's. If you have also filed this at
grafana/grafana-ansible-collection, link it — it is useful for tracking, and
`make carried-prs` uses that link to notice if upstream ever merges it.
Not a prerequisite: upstream's maintainership is dormant.
-->
