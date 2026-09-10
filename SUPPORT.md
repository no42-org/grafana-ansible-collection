# Support

## Where to go

| What you have | Where it goes |
| --- | --- |
| A bug in a role, module or the collection | [Open an issue](https://github.com/no42-org/grafana-ansible-collection/issues) |
| A change you would like to make | [Open an issue or pull request](https://github.com/no42-org/grafana-ansible-collection/issues) — see [CONTRIBUTING.md](CONTRIBUTING.md) |
| A security vulnerability | [Report it privately](https://github.com/no42-org/grafana-ansible-collection/security/advisories/new), never as an issue — see [SECURITY.md](SECURITY.md) |
| A question about Grafana itself | [Grafana community forums](https://community.grafana.com/) — this repository is about the Ansible collection, not the products it installs |

## What to expect

**Best effort, and no more than that.**

This is a fork maintained by one person outside of paid work. There is no service-level commitment, no response-time target, and no guarantee that any particular issue gets fixed. Issues may sit for a while.

What you can rely on:

- Issues are read.
- Security reports are prioritised over everything else.
- Releases happen when there is something worth releasing, not on a schedule.
- If something will not be done, you will be told that rather than left waiting.

That last point is the one worth stating. An unattended tracker that looks like a support channel is worse than an honest one, and this project exists partly because upstream's queue stopped being answered.

## Why this fork exists

[`grafana/grafana-ansible-collection`](https://github.com/grafana/grafana-ansible-collection) has an active community and dormant maintainership: as of September 2026 its last merge was 2026-05-22 and its last release 2026-04-27, with 32 pull requests open, several over a year old.

This fork carries selected fixes from that queue, with their authors preserved, and publishes them as [`indigo423.grafana`](https://galaxy.ansible.com/ui/repo/published/indigo423/grafana/). It is not a competitor and not a takeover attempt — if upstream resumes, this fork drops what upstream merges.

Practically, that means:

- **Role and module behaviour is mostly upstream's code.** A bug you find here probably exists there too. Reporting it upstream as well reaches more people, though you should not wait on it.
- **Version numbers are this fork's own** and do not correspond to upstream releases of the same number. Each release records the upstream commit it was built from.
- **Three roles are known broken with default settings** — `promtail`, `tempo`, and `loki` on the RHEL family — for reasons inherited from upstream. Details in [RELEASING.md](RELEASING.md). If one of those is what you needed, an issue saying so is genuinely useful: a stated need is a much better reason to fix something than a checklist.
