# Security Policy

## Reporting a vulnerability

**Please do not open a public issue for a security problem.**

Use GitHub's private vulnerability reporting for this repository:

[**Report a vulnerability privately**](https://github.com/no42-org/grafana-ansible-collection/security/advisories/new)

That opens a draft advisory visible only to you and the maintainer. It is the right channel for anything that could be exploited before a fix is available: credential handling, privilege escalation in a role, a template that writes attacker-controlled content, or a dependency advisory that this collection actually reaches.

For anything that is a bug rather than a vulnerability, a normal [issue](https://github.com/no42-org/grafana-ansible-collection/issues) is fine and preferred.

## Supported versions

| Version | Supported |
|---|---|
| latest release | ✅ |
| anything older | ❌ |

This is a small fork maintained by one person. Only the most recent release of `indigo423.grafana` gets fixes; there are no backport branches. If you need a fix on an older version, the answer is to upgrade.

Response is best-effort. There is no service-level commitment.

## Where the problem probably belongs

This repository is a curated fork of [`grafana/grafana-ansible-collection`](https://github.com/grafana/grafana-ansible-collection), and most of the code in it is upstream's.

**If the vulnerability is in role or module behaviour**, it almost certainly affects the upstream collection and everyone using it, not just this fork. Reporting it to upstream as well reaches far more users:

- [Upstream security policy](https://github.com/grafana/grafana-ansible-collection/security)
- [Grafana Labs security](https://grafana.com/security/)

Report it here too, by all means — this fork releases more often at present — but upstream is where the wider fix belongs.

**If the vulnerability is in something this fork owns** — the release pipeline, the build-time namespace rename, the tooling under `tools/`, the role test harness — then here is the only place it exists, and here is where to report it.

## What this fork does about supply chain

Honest inventory, so you can judge the risk yourself rather than infer it:

| | Status |
|---|---|
| Secret scanning + push protection | enabled |
| Dependabot security updates | enabled |
| Private vulnerability reporting | enabled |
| GitHub Actions pinned to commit SHAs | `release.yml` and `role-test.yml` only; the remaining inherited workflows are not yet pinned |
| Signed release artifacts (cosign) | **no** — deferred; Galaxy does not consume signatures, so it would cover the GitHub asset only |
| SBOM | **no** — deferred |
| Build provenance attestation | **no** — deferred |
| Published collection contents | verifiable against the upstream commit each release is built from; see [RELEASING.md](RELEASING.md) |

The deferred items are recorded rather than forgotten. If any of them matters to you, say so in an issue — a stated need is a much better reason to add them than a checklist.

## A note on what gets published

Releases go to [`indigo423.grafana`](https://galaxy.ansible.com/ui/repo/published/indigo423/grafana/) on Ansible Galaxy.

Version numbers are this fork's own and do **not** correspond to upstream releases of the same number. Each GitHub release records the upstream commit it was built from, and the collection's contents can be diffed against that commit — the procedure is in [RELEASING.md](RELEASING.md). If you want to know exactly what you are installing relative to upstream, that diff is the answer.
