# Ansible Collection for Grafana

> **Fork notice.**
> This is a fork of [grafana/grafana-ansible-collection](https://github.com/grafana/grafana-ansible-collection), published to Ansible Galaxy as [`indigo423.grafana`](https://galaxy.ansible.com/ui/repo/published/indigo423/grafana/).
> Version numbers are this fork's own and do not correspond to upstream releases; each release records the upstream commit it was built from.
> It carries selected upstream pull requests that are open and unmerged, with their authors preserved, and drops each one once upstream merges it.
> The source tree keeps upstream's collection name and it is rewritten at build time.
> See [RELEASING.md](https://github.com/no42-org/grafana-ansible-collection/blob/main/RELEASING.md) for the release process.

[![Grafana](https://img.shields.io/badge/grafana-%23F46800.svg?&logo=grafana&logoColor=white)](https://grafana.com)
[![CI](https://github.com/no42-org/grafana-ansible-collection/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/no42-org/grafana-ansible-collection/actions/workflows/ci.yml)
[![Ansible Collection](https://img.shields.io/badge/grafana.grafana-orange)](https://galaxy.ansible.com/ui/repo/published/indigo423/grafana/)
[![GitHub release](https://img.shields.io/github/v/release/no42-org/grafana-ansible-collection.svg)](https://github.com/no42-org/grafana-ansible-collection/releases)
[![GitHub Last Commit](https://img.shields.io/github/last-commit/no42-org/grafana-ansible-collection)](https://github.com/no42-org/grafana-ansible-collection/commits/main)
[![License](https://img.shields.io/github/license/no42-org/grafana-ansible-collection)](LICENSE)

This collection (`grafana.grafana`) contains modules and roles to assist in automating the management of resources in **Grafana**, **OpenTelemetry Collector**, **Loki**, **Mimir**, and **Alloy** with Ansible.

-   [Ansible collection Documentation](https://docs.ansible.com/ansible/latest/collections/grafana/grafana/)
-   [Grafana](https://grafana.com)
-   [Grafana Cloud](https://grafana.com/products/cloud/)

## Ansible version compatibility

This fork declares `requires_ansible: ">=2.17.0,<3.0.0"`, and the claim is tested at both ends rather than asserted.
Every role is executed on `ansible-core` 2.18 on both package families.
A sample of the roles, `grafana` on both families and `alloy` on Debian, is also executed on the newest release inside the range, 2.21.4 at the time of writing.
Static analysis runs on 2.17, 2.18 and `devel`.
The versions executed are declared once, in `pyproject.toml`, and `RELEASING.md` records what the sample omits.
The upstream collection claims `ansible >= 2.9`; that claim was inherited and is not what is tested here.

## Versions the roles install

Every role installs a **pinned** version. None resolves `latest` at run time, so what a role installs cannot change without a commit here — and a passing role test is a statement about a named version rather than about whichever release happened to be current that day.

[![grafana](https://img.shields.io/badge/grafana-13.2.1-informational)](https://github.com/grafana/grafana/releases)
[![loki](https://img.shields.io/badge/loki-3.7.7-informational)](https://github.com/grafana/loki/releases)
[![mimir](https://img.shields.io/badge/mimir-3.2.1-informational)](https://github.com/grafana/mimir/releases)
[![tempo](https://img.shields.io/badge/tempo-3.0.3-informational)](https://github.com/grafana/tempo/releases)
[![alloy](https://img.shields.io/badge/alloy-1.19.2-informational)](https://github.com/grafana/alloy/releases)
[![opentelemetry_collector](https://img.shields.io/badge/opentelemetry__collector-0.160.0-informational)](https://github.com/open-telemetry/opentelemetry-collector-releases/releases)

### How the pins stay current

A weekly workflow compares each pin against the upstream project's latest release and opens a pull request when one falls behind. The bump then runs that role's tests on **both** package families before anyone merges it.

That verification is the point, not a formality. A pin nobody moves is how `opentelemetry_collector` came to sit on a December 2023 release for nearly three years, and an unverified bump is how the `tempo` role came to ship a configuration Tempo rejects. Pinning without both would move the risk rather than remove it.

One role is excluded from tracking, for a reason that will not change on its own:

| Role | Why it is not tracked |
| --- | --- |
| `grafana` | Installs from a package repository, so its version is a package version rather than a release tag. Maintained by hand. |

Any pin can be overridden — set `<role>_version` to install a different version, including `latest` if you would rather track it yourself.

## Installing the collection

Before using the Grafana collection, you need to install it using the below command:

```shell
ansible-galaxy collection install indigo423.grafana
```

You can also include it in a `requirements.yml` file and install it via `ansible-galaxy collection install -r requirements.yml`, using the format:

```yaml
---
collections:
  - name: indigo423.grafana
```

A specific version of the collection can be installed by using the version keyword in the `requirements.yml` file — substitute the version you want, which need not be the one shown:

```yaml
---
collections:
  - name: indigo423.grafana
    version: 7.1.0
```

## Roles included in the collection

This collection includes the following roles to help set up and manage Grafana, Alloy, OpenTelemetry Collector, Loki and Mimir:

- **Grafana**: Installs and configures Grafana on your target hosts.
- **Alloy**: The replacement for Grafana Agent and Promtail. Alloy can be used to collect traces, metrics, and logs.
- **OpenTelemetry Collector**: Sets up and configures the OpenTelemetry Collector, enabling advanced observability features through data collection and transmission.
- **Loki**: Deploy and manage Loki, the log aggregation system.
- **Mimir**: Deploy and manage Mimir, the scalable long-term storage for Prometheus.

## Using this collection

You can call modules by their Fully Qualified Collection Namespace (FQCN), such as `grafana.grafana.cloud_stack`:

```yaml
- name: Using grafana collection
  hosts: localhost
  tasks:
    - name: Create a Grafana Cloud stack
      grafana.grafana.cloud_stack:
        name: mystack
        stack_slug: mystack
        org_slug: myorg
        cloud_api_key: "{{ cloud_api_key }}"
        region: eu
        state: present
```

or you can add full namespace and collection name in the `collections` element in your playbook

```yaml
- name: Using grafana collection
  hosts: localhost
  collection:
    - grafana.grafana
  tasks:
    - name: Create a Grafana Cloud stack
      cloud_stack:
        name: mystack
        stack_slug: mystack
        org_slug: myorg
        cloud_api_key: "{{ cloud_api_key }}"
        region: eu
        state: present
```

## Contributing

We are accepting GitHub pull requests and issues. There are many ways in which you can participate in the project, for example:

-   Submit bugs and feature requests, and help us verify them
-   Submit and review source code changes in GitHub pull requests
-   Add new modules for more Grafana resources

## Testing and Development

If you want to develop new content for this collection or improve what is already
here, the easiest way to work on the collection is to clone it into one of the configured
[`COLLECTIONS_PATHS`](https://docs.ansible.com/ansible/latest/reference_appendices/config.html#collections-paths),
and work on it there.

### Testing with `ansible-test`

We use `ansible-test` for sanity.

## Commands

| Command | Description |
| :--- | :----------- |
| `make setup` | Checks to see if necessary tools are installed |
| `make install` | Installs project dependencies |
| `make lint` | Performs all linting commands |
| `make lint-sh` / `make lint-shell` | Performs shell script linting |
| `make lint-md` / `make lint-markdown` | Performs Markdown linting |
| `make lint-txt` / `make lint-text` | Performs text linting |
| `make lint-yml` / `make lint-yaml` | Performs Yaml linting |
| `make lint-ec` / `make lint-editorconfig` | Performs EditorConfig Checks |
| `make lint-ansible` | Performs Ansible linting |
| `make clean` | Removes the `./node_modules` and `./build` directories |
| `make reinstall` | Shortcut to `make clean` and `make install` |

## Releasing, Versioning and Deprecation

This collection follows [Semantic Versioning](https://semver.org/). More details on versioning can be found [in the Ansible docs](https://docs.ansible.com/ansible/latest/dev_guide/developing_collections.html#collection-versions).

We plan to regularly release new minor or bugfix versions once new features or bugfixes have been implemented.

Releasing the current major version on GitHub happens from the `main` branch by the
[GitHub Release Workflow](https://github.com/grafana/grafana-ansible-collection/blob/main/.github/workflows/release.yml).
Before the [GitHub Release Workflow](https://github.com/grafana/grafana-ansible-collection/blob/main/.github/workflows/release.yml)
is run, Contributors should push the new version on Ansible Galaxy Manually.

To generate changelogs for a new release, Refer [Generating Changelogs](https://docs.ansible.com/ansible/latest/dev_guide/developing_collections_changelogs.html#generating-changelogs) or run `antsibull-changelog generate`and `antsibull-changelog lint-changelog-yaml changelogs/changelog.yaml` to validate the YAML file.

To generate the tarball to be uploaded on Ansible Galaxy, Refer [Building collection tarball](https://docs.ansible.com/ansible/latest/dev_guide/developing_collections_distributing.html#building-your-collection-tarball)

## Code of Conduct

This collection follows the Ansible project's [Code of Conduct](https://docs.ansible.com/ansible/devel/community/code_of_conduct.html).
Please read and familiarize yourself with this doc

## More information

-   [Maintainer guidelines](https://docs.ansible.com/ansible/devel/community/maintainers.html)
-   Subscribe to the [news-for-maintainers](https://github.com/ansible-collections/news-for-maintainers) repository and track announcements there.
-   [Ansible Collection overview](https://github.com/ansible-collections/overview)
-   [Ansible User guide](https://docs.ansible.com/ansible/latest/user_guide/index.html)
-   [Ansible Developer guide](https://docs.ansible.com/ansible/latest/dev_guide/index.html)
-   [Ansible Collection Developer Guide](https://docs.ansible.com/ansible/devel/dev_guide/developing_collections.html)
-   [Ansible Community code of conduct](https://docs.ansible.com/ansible/latest/community/code_of_conduct.html)

## License

GPL-3.0-or-later
