================================
Indigo423.Grafana Release Notes
================================

.. contents:: Topics

v7.4.0
======

Release Summary
---------------

Two test harnesses this collection never had, and the defects that existed because it never had
them. A plugin module's whole behaviour is which HTTP route it builds, so make module-test now runs
one against a running Grafana on the version the grafana role pins. The alloy role validates its
configuration with alloy validate before writing it and confirms the service is still running after
the restart, and its role test applies a configuration Alloy rejects. Both were built around a
defect each had let through: the datasource module could not update a data source on any Grafana 13,
which removed the route its update path built, and the alloy role reported success for a
configuration Alloy cannot run, because a readiness check that cannot fail on the first attempt
cannot tell a healthy service from one systemd is respawning ten times a second. The grafana role
pin moves to 13.2.2. Version numbers are this fork's own and do not correspond to any
grafana.grafana release; the upstream commit this release is built from is recorded in its GitHub
release notes.

Minor Changes
-------------

- The alloy role gains alloy_validate_config (default true), alloy_validate_extra_args and
  alloy_restart_settle_seconds (default 10). Validation carries over --stability.level and
  --feature.community-components.enabled from alloy_env_file_vars.CUSTOM_ARGS, because alloy
  validate defaults to generally-available with community components off and would otherwise reject
  a configuration that runs. It is skipped, never failed, when alloy_version predates 1.9.0, the
  release that introduced the subcommand, or the binary is not yet on the host.
- The grafana role pin moves to 13.2.2, verified by that role's tests on both package families
  before merging.
- A module test harness runs a plugin module against a running Grafana, on the version the grafana
  role pins: make module-test MODULE=datasource. A module's whole behaviour is which HTTP route it
  builds, so only a running Grafana can judge it, and nothing in this repository had ever done so.
  MODULE_TEST_GRAFANA_VERSION runs the same scenario against another version, which is how a route
  removal gets dated.
- make ci-lint-versions compares the versions the documentation claims with the versions the roles
  pin, and fails in both directions. A pin is written down three times -- defaults/main.yml, the
  root README badge and the role README -- and only the first moved on a bump, so six claims across
  three roles had gone stale, including a role README that still documented loki_version: latest.
  tools/bump-role-versions.sh now rewrites the documentation as part of the bump.
- make sanity runs ansible-test sanity staged the way CI stages the tree, and the test workflows
  filter on everything their harnesses read rather than on roles/ alone.
- Every role's version pin is compared against the source that role installs from, rather than
  against a GitHub release for all of them. grafana installs from apt.grafana.com and
  rpm.grafana.com, so it was excluded and became the one pin nothing watched: 13.2.2 was released on
  2026-09-15 and this collection stayed on 13.2.1 with nothing to say so. A package repository has
  an index, and the index is the list of versions that are installable. A release whose .rpm, .deb
  or .tar.gz has not finished uploading is held rather than proposed, because proposing it opens a
  pull request whose role test cannot pass.

Bugfixes
--------

- The datasource module updates an existing data source through PUT /api/datasources/uid/<uid>
  rather than PUT /api/datasources/<id>, which Grafana 13.0 removed. Measured against the real API,
  one container per version: the numeric-id route answers on 10.4.19, 11.6.7 and 12.3.0 and returns
  404 on 13.0.1, 13.1.0 and 13.2.1, while the uid route answers on all six. The uid is resolved from
  the data source list by the name that collided, so uid stays optional for consumers who never set
  one, and a 409 with no matching data source now fails with a message quoting Grafana rather than
  raising KeyError. Addresses grafana/grafana-ansible-collection#537.
- The alloy role validates the configuration with alloy validate before writing it and before
  restarting the service, so a configuration Alloy rejects fails the play and never replaces the
  file on disk. The readiness check could not do this: Ansible applies retries only after a failed
  attempt, so a first-try 200 from /-/ready ends the task. Addresses grafana/grafana-ansible-
  collection#535.
- The alloy role confirms the service is still running after it restarts it, by comparing the
  systemd unit's NRestarts across a settle window. The packaged unit is Restart=always with the
  default RestartSec of 100ms, so a configuration that loads and then crashes is respawned about ten
  times a second and still answers /-/ready from ActiveState=active. Only NRestarts separates the
  two.
- Release notes list the upstream contributions a release newly carried rather than every one
  carried since the fork diverged, which repeated the same list under every version number. The
  cumulative count is stated in one line instead.
- tools/check-shipped-manifests.py imports ElementTree in the form ansible-test sanity's pylint
  requires. Missed locally because the sanity tree was staged with the distribution exclude list,
  which drops /tools; CI checks out the whole repository, so it lints files that staging had
  removed.

Known Issues
------------

- A playbook whose alloy configuration Alloy cannot load now fails where it previously reported
  success. That is the defect being fixed, but it is a run that changes colour without the playbook
  changing. alloy_validate_config: false and alloy_restart_settle_seconds: 0 restore the previous
  behaviour.

v7.3.0
======

Release Summary
---------------

Four defects in the grafana role and one shared across five roles, all of them cases where the
collection had drifted behind what it installs. Plugin installation was broken outright on Grafana
13, which removed the grafana-cli binary the role invoked; booleans in grafana_ini reached
grafana.ini capitalised, which Grafana's own documentation says they must not be; a fresh install
could restart Grafana while its database migrations were still running, leaving a database no later
start recovers; and every role that resolves <role>_version: latest could adopt a release tag that
was never a version, because the expression that was meant to filter them could only substitute. No
variable or interface is removed, and one is added. An existing deployment rewrites grafana.ini on
its first converge and restarts Grafana once -- see the upgrade note below. Version numbers are
this fork's own and do not correspond to any grafana.grafana release; the upstream commit this
release is built from is recorded in its GitHub release notes.

Minor Changes
-------------

- The grafana role gains grafana_ini.paths.plugins, derived from paths.data when unset and rendered
  into grafana.ini. Both the Grafana server and the plugin CLI read this one value, so they cannot
  disagree about where plugins live.
- The alloy and opentelemetry_collector roles default their GitHub API endpoint to the releases
  list rather than releases/latest, because the newest release in those repositories is not
  reliably a version of the software. alloy_github_api_url and otel_collector_latest_url keep their
  names, and a releases/latest URL set by a consumer still resolves.
- The loki role pin moves to 3.7.8 and the opentelemetry_collector role pin to 0.161.0, each
  verified by that role's tests on both package families before merging.
- The grafana role test asserts the rendered grafana.ini contains no capitalised boolean, that the
  database is ready after a converge, and that a plugin installs into the configured directory
  owned by grafana. The version selection gains a suite of its own, run by make version-select-test
  against recorded GitHub payloads, because no role test can reach the latest path while every role
  pins its version.

Bugfixes
--------

- The grafana role installs plugins again on Grafana 13, which removed the grafana-cli binary the
  role invoked. The plugin CLI form is now selected at run time by probing for the grafana cli
  subcommand, so the role works from Grafana 5.1 through 13.x and emits no deprecation warning on
  current versions. Addresses grafana/grafana-ansible-collection#509.
- The grafana role installs plugins as the grafana user rather than root. Extracted as root, a
  plugin directory is one the Grafana server cannot replace, so updating that plugin from the user
  interface fails. Addresses grafana/grafana-ansible-collection#508.
- The grafana role resolves one plugin directory for both the server and the plugin CLI. The role
  computed the CLI's --pluginsDir from paths.data while leaving paths.plugins out of grafana.ini
  entirely, so the server fell back to its own default and the two disagreed whenever paths.data
  was overridden. Addresses grafana/grafana-ansible-collection#331.
- The grafana role renders booleans in grafana.ini as true and false rather than Python's True and
  False. Ansible resolves a YAML true to a Python bool and Jinja stringifies it capitalised;
  Grafana documents the lowercase form, and for auth.ldap.enabled the difference is silent -- the
  server enables LDAP but the login page never offers it. Values the user wrote as strings are
  untouched, so quoting remains a valid escape hatch. Addresses
  grafana/grafana-ansible-collection#417.
- The grafana role waits for Grafana to report its database ready before flushing handlers. On a
  first install the service start begins the database migrations and the queued restart handler
  could terminate Grafana part way through them, leaving a database that no later start recovers
  and that has to be wiped by hand. Carries grafana/grafana-ansible-collection#528 by Dmitriy
  Rabotyagov, with the corrections needed to make it run.
- The alloy, loki, mimir, tempo and opentelemetry_collector roles resolve <role>_version: latest to
  a release whose tag is actually a version. regex_replace is a substitution, not a filter: a tag
  that did not match was returned unchanged and became the version, so a Go submodule tag such as
  syntax/v0.1.1 produced a download URL that 404s. Each role now reads the releases list, rejects
  drafts and prereleases on the flags GitHub sets, takes the newest release whose tag matches its
  pattern, and fails naming the tags it saw when none qualifies. Addresses
  grafana/grafana-ansible-collection#530.

Known Issues
------------

- An existing deployment rewrites /etc/grafana/grafana.ini on its first converge after upgrading
  and restarts Grafana once. Five booleans in the role's own defaults change case, and
  paths.plugins is newly rendered. No setting changes value.
v7.2.1
======

Release Summary
---------------

A correctness release for the grafana role's dashboard provisioning. Two defects, each in a
provisioning route the role tests never entered. The synchronising removal guarded itself with a
conditional that returns a list rather than a boolean, which ansible-core 2.19 made fatal, so that
path aborted the play on every version from 2.19 up while requires_ansible claims support to 3.0.0.
And the grafana.net dashboard copy declared owner root against a handler that recurses the same
tree setting owner grafana, so the two reversed each other and the role never converged. No
variable, default or interface changes; a consumer upgrading gets the fixes without action. Version
numbers are this fork's own and do not correspond to any grafana.grafana release; the upstream
commit this release is built from is recorded in its GitHub release notes.

Bugfixes
--------

- The grafana role's "Remove dashboards not present on deployer machine (synchronize)" task no
  longer aborts the play on ansible-core 2.19 and later. Its conditions used `X is defined and X`,
  and Jinja's `and` yields an operand rather than a boolean, so the condition evaluated to a list;
  ansible-core 2.19 rejects a non-boolean conditional outright. They are length comparisons now.
  Addresses grafana/grafana-ansible-collection#493.
- The grafana role's "Import grafana.net dashboards" task copies with owner grafana rather than
  owner root. The handler it notifies recurses the provisioned dashboards tree setting owner
  grafana, so the copy and the handler reversed each other on every run and the role could never
  report no change. Addresses grafana/grafana-ansible-collection#244.
- The grafana role's folder synchronise task gains the same two corrections: its condition is a
  list of boolean tests rather than a Jinja `and`, and grafana_provisioning_synced is filtered
  through `| bool`. Without the filter a string extra-var such as `-e
  grafana_provisioning_synced=false` read as truthy there while the dashboards task, which does
  filter, read it as false, so synchronisation was nominally off while folders were removed.

Minor Changes
-------------

- The role test harness gains an optional prepare phase, run once before the first converge, for
  state a role is expected to reconcile away. Converge runs twice to prove idempotence, so it
  cannot create state a role is meant to remove without that removal reporting a change forever. A
  role without a prepare.yml does not get the phase.
- The grafana role test enters the dashboard provisioning routes it previously left at their
  defaults: grafana_provisioning_synced and a grafana_dashboards entry are set, and verify asserts
  the ownership of provisioned files, that the datasource placeholder was rewritten, and that a
  dashboard absent from the deployer is removed.

v7.2.0
======

Release Summary
---------------

Two literals in the mimir role become variables, both defaulting to what the role always did.
mimir_target is the target line of the configuration; a consumer that never calls the alertmanager
can run all alone, which also leaves the memberlist KV service uninitialised on a single node.
mimir_config_mode is the mode of /etc/mimir/config.yml; a consumer that renders object-store
credentials into it can set 0640. No existing behaviour changes. Version numbers are this fork's own
and do not correspond to any grafana.grafana release; the upstream commit this release is built from
is recorded in its GitHub release notes.

Minor Changes
-------------

- The mimir role gains mimir_target, the target line of /etc/mimir/config.yml, defaulting to the
  all,alertmanager,overrides-exporter the template always wrote. target joins the keys
  mimir_config_extra refuses.
- The mimir role gains mimir_config_mode, the mode of /etc/mimir/config.yml, defaulting to the 0644
  the task always wrote. The file carries secret_access_key when an S3 backend is configured; 0640
  keeps it to the mimir user and group.
- The mimir role test sets mimir_config_mode to 0640 and asserts the mode of the rendered file.

v7.1.0
======

Release Summary
---------------

The mimir role can now render any top-level key of /etc/mimir/config.yml, not only the twelve its
template names. mimir_config_extra takes a dict of top-level keys -- multitenancy_enabled,
store_gateway, compactor, frontend and the rest of Mimir's sections -- and renders it after the
named sections; a key that also has a named section is refused before the template runs. The /ready
wait is configurable through mimir_ready_retries and mimir_ready_delay, defaulting to the 5 and 8
that were literal. No existing behaviour changes. Version numbers are this fork's own and do not
correspond to any grafana.grafana release; the upstream commit this release is built from is
recorded in its GitHub release notes.

Minor Changes
-------------

- The mimir role gains mimir_config_extra, a dict of top-level keys for /etc/mimir/config.yml that
  have no mimir_<section> variable of their own. It is rendered after the named sections. A key
  present both there and as a named section fails the run naming the key and the variable to use
  instead, because YAML parsers accept a duplicated top-level key and Mimir would read whichever
  survived parsing.
- The mimir role's wait for /ready is configurable through mimir_ready_retries (default 5) and
  mimir_ready_delay (default 8 seconds), the values that were previously literal. A clustered node
  that joins memberlist before its ingester reports ready can need more than the 40 seconds those
  allow.
- The mimir role test sets multitenancy_enabled: false through the passthrough and checks it from
  outside: a labels query with no X-Scope-OrgID header is answered rather than refused.

v7.0.0
======

Release Summary
---------------

Two roles are removed. grafana_agent and promtail no longer ship: Grafana archived the Agent, and
declared Promtail end of life on 2026-03-02 with no packages published after Loki 3.6.0. Any
playbook calling indigo423.grafana.grafana_agent or indigo423.grafana.promtail no longer resolves
them; the alloy role replaces both. Every remaining role now installs a pinned version by default
rather than whichever release was newest at run time, and a weekly tracker opens a pull request,
verified by the role tests, when a pin falls behind. The grafana role retries repository metadata
fetches on RHEL to ride out a cache offset in Grafana's package CDN. The roles are now executed on
ansible-core 2.18 on both package families and, for grafana and alloy, on 2.21.4, the newest release
inside the range requires_ansible claims. Version numbers are this fork's own and do not correspond
to any grafana.grafana release; the upstream commit this release is built from is recorded in its
GitHub release notes.

Minor Changes
-------------

- A weekly workflow compares every role's pinned version with its upstream releases and opens one
  pull request per role that has fallen behind. The pull request runs that role's tests on both
  package families before a human merges it. grafana is excluded because its version is a package-
  repository version rather than a release tag.
- Roles are executed on ansible-core 2.18 on both package families, and grafana on both families
  plus alloy on Debian are also executed on 2.21.4, the newest release inside the requires_ansible
  range. Static analysis covers 2.17, 2.18 and devel. requires_ansible is unchanged at
  >=2.17.0,<3.0.0.
- The grafana role retries its two package installs on RHEL. grafana_install_retries (default 5) and
  grafana_install_retry_delay (default 30 seconds) apply to both the dependency install and the
  Grafana install, because update_cache refreshes every enabled repository on the first as well. Set
  grafana_install_retries to 0 to install exactly once.

Breaking Changes / Porting Guide
--------------------------------

- Every role installs a pinned version by default instead of resolving the newest release at run
  time. The defaults are grafana 13.2.1, loki 3.7.7, mimir 3.2.1, tempo 3.0.3, alloy 1.19.2 and
  opentelemetry_collector 0.160.0. Set <role>_version to a version of your choice, or to latest to
  restore the previous behaviour. Every pin except opentelemetry_collector is what latest resolved
  to on the day it was set.
- The grafana_agent role is removed. Grafana archived the Agent in favour of Alloy, and the role
  shipped no test, so no version bump could ever be verified. Use the alloy role.
- The opentelemetry_collector role's default version moves from 0.90.1 to 0.160.0. The old default
  predated pinning and had fallen seventy minor releases behind.
- The promtail role is removed. Grafana declared Promtail end of life on 2026-03-02 and published no
  packages after Loki 3.6.0, so nothing newer will ever exist. Use the alloy role.

Bugfixes
--------

- ansible.cfg used collections_paths, a spelling ansible-core 2.19 removed and 2.21 silently
  ignores. The singular collections_path is read by every version in the requires_ansible range.
- grafana on RHEL no longer fails intermittently with "Bad GPG signature" on repomd.xml. The cause
  is the cache in front of rpm.grafana.com serving the metadata and its signature from different
  generations for up to two minutes after a republish, not the key or the pinned version, and the
  install now retries across that window. The repository GPG check stays enabled, as Grafana's own
  documentation configures it.

v6.2.2
======

Release Summary
---------------

Corrects what the published collection says about its own dependencies. requirements.txt declared
this repository's linters -- yamllint, ansible-lint and pylint -- and now declares requests, the
library every module actually imports and which was declared nowhere. Two further manifests stop
shipping: requirements.yml, which duplicated galaxy.yml's own dependencies as unconstrained git
URLs, and roles/grafana/test-requirements.txt, which listed Molecule's dependencies for scenarios
this fork never invokes. Version numbers are this fork's own and do not correspond to any
grafana.grafana release; the upstream commit this release is built from is recorded in its GitHub
release notes.

Minor Changes
-------------

- requirements.yml is no longer published. It duplicated galaxy.yml's own dependencies as git URLs
  pointing at main, so a consumer following it would have installed three collections unconstrained.
  ansible-galaxy resolves the constrained versions from the collection's MANIFEST.json instead, and
  continues to do so.
- roles/grafana/test-requirements.txt is no longer published. It declared molecule, docker, pytest-
  testinfra, jmespath, selinux and passlib for Molecule scenarios this fork never invokes.

Bugfixes
--------

- requirements.txt now declares requests, the collection's actual Python runtime dependency. It
  previously declared yamllint, ansible-lint and pylint, none of which a consumer needs, while the
  library all 18 modules import behind a HAS_REQUESTS guard was declared nowhere -- so a module
  reporting missing_required_lib('requests') pointed at documentation that did not exist.
v6.2.1
======

Release Summary
---------------

Patch release. The user-facing change is a set of role and module bugfixes, one of them carried from
an upstream pull request. Everything else in this release is repository infrastructure that the
published collection does not contain: the lint gates now actually fail when a linter finds
something, the quality gates have a single shared definition used by both CI and the release, and
the development toolchain installs without a specific Python interpreter. Version numbers are this
fork's own and do not correspond to any grafana.grafana release; the upstream commit this release is
built from is recorded in its GitHub release notes.

Minor Changes
-------------

- Use fully-qualified collection names for builtin actions in the opentelemetry_collector role and the
  integration targets, and correct task naming and Jinja spacing, so the collection satisfies
  ansible-lint's production profile with no failures or warnings.
- Whitespace and indentation corrections across roles/ and examples/ so the collection is clean under
  yamllint and editorconfig-checker. No behaviour changes.

Bugfixes
--------

- Skip the firewalld rule removal during alloy uninstall when firewalld is inactive, so the play no
  longer relied on ignore_errors and now mirrors the deploy conditions by @baltvinicius in
  https://github.com/grafana/grafana-ansible-collection/pull/539
- Return a value from alert_contact_point when the read-back after a successful update does not list
  the UID. The function fell through and returned None, which the module unpacks into three values,
  so a successful update could raise a TypeError instead of reporting success.
- Set pipefail on the grafana_agent version-detection pipelines. Without it a failing curl or a
  missing grafana-agent binary produced an empty string and the pipeline still reported success, so
  the role proceeded with no version at all.
- Set an explicit mode on the systemd drop-in the grafana role creates with blockinfile, which
  previously took whatever the umask gave it.
- Use ansible.builtin.command instead of shell for two grafana_agent tasks that need no shell,
  removing a layer of word-splitting and quoting from paths built by template.
- Remove a duplicated assignment to api_url in the dashboard module.
v6.2.0
======

Release Summary
---------------

First curated release of this fork. Version numbers are this fork's own and do not correspond to any grafana.grafana release; the upstream commit each release is built from is recorded in its GitHub release notes. This release carries seven upstream pull requests that are open and unmerged, with their authors preserved. Each is dropped once upstream merges it.

Bugfixes
--------

- Set chdir to the Grafana homepath so grafana-cli can install plugins on Grafana 13 by @indigo423 in https://github.com/grafana/grafana-ansible-collection/pull/510
- Guard the grafana_rhsm_* conditions against undefined variables by @uLcL in https://github.com/grafana/grafana-ansible-collection/pull/534
- Add module_hotfixes to the yum/dnf repository so Grafana packages win over system ones by @WistfulAdris in https://github.com/grafana/grafana-ansible-collection/pull/538
- Create dashboard folders from a list instead of a stringified list by @cmehat in https://github.com/grafana/grafana-ansible-collection/pull/448
- Set owner and group when extracting the OpenTelemetry Collector by @mhumeSF in https://github.com/grafana/grafana-ansible-collection/pull/475
- Treat HTTP 409 as an existing alert contact point, restoring idempotency on current Grafana by @argpna in https://github.com/grafana/grafana-ansible-collection/pull/536
- Accept the mimir- prefix when determining the latest Mimir version by @Spirit-act in https://github.com/grafana/grafana-ansible-collection/pull/461

Minor Changes
-------------

- Fix colon spacing in roles/grafana/tasks/dashboards.yml, introduced by the carried contribution from https://github.com/grafana/grafana-ansible-collection/pull/448
- Raise the requires_ansible floor to >=2.17.0 to match the versions actually tested
- Correct the release notes title, which the build-time namespace rewrite cannot reach

v6.1.0
======

Major Changes
-------------

- Run molecule only when required by @voidquark in https://github.com/grafana/grafana-ansible-collection/pull/441
- migrate stack create/update/delete to stacks-api by @KucicM in https://github.com/grafana/grafana-ansible-collection/pull/494

v6.0.6
======

Major Changes
-------------

- Restore default listen address and port in Mimir by @56quarters in https://github.com/grafana/grafana-ansible-collection/pull/456
- fix broken Grafana apt repository addition by @kleini in https://github.com/grafana/grafana-ansible-collection/pull/454

v6.0.5
======

Major Changes
-------------

- Fallback to empty dict in case grafana_ini is undefined by @root-expert in https://github.com/grafana/grafana-ansible-collection/pull/403
- Fix Mimir config file validation task by @Windos in https://github.com/grafana/grafana-ansible-collection/pull/428
- Fixes issue by @digiserg in https://github.com/grafana/grafana-ansible-collection/pull/421
- Import custom dashboards only when directory exists by @mahendrapaipuri in https://github.com/grafana/grafana-ansible-collection/pull/430
- Updated YUM repo urls from `packages.grafana.com` to `rpm.grafana.com` by @DejfCold in https://github.com/grafana/grafana-ansible-collection/pull/414
- Use credentials from grafana_ini when importing dashboards by @root-expert in https://github.com/grafana/grafana-ansible-collection/pull/402
- do not skip scrape latest github version even in check_mode by @cmehat in https://github.com/grafana/grafana-ansible-collection/pull/408
- fix datasource documentation by @jeremad in https://github.com/grafana/grafana-ansible-collection/pull/437
- fix mimir_download_url_deb & mimir_download_url_rpm by @germebl in https://github.com/grafana/grafana-ansible-collection/pull/400
- update catalog info by @Duologic in https://github.com/grafana/grafana-ansible-collection/pull/434
- use deb822 for newer debian versions by @Lukas-Heindl in https://github.com/grafana/grafana-ansible-collection/pull/440

v6.0.4
======

Major Changes
-------------

- Add SUSE support to Alloy role by @pozsa in https://github.com/grafana/grafana-ansible-collection/pull/423
- Fixes to foldersFromFilesStructure option by @root-expert in https://github.com/grafana/grafana-ansible-collection/pull/351
- Migrate RedHat install to ansible.builtin.package by @r65535 in https://github.com/grafana/grafana-ansible-collection/pull/431
- add macOS support to alloy role by @l50 in https://github.com/grafana/grafana-ansible-collection/pull/418
- replace None with [] for safe length checks by @voidquark in https://github.com/grafana/grafana-ansible-collection/pull/426

v6.0.3
======

Major Changes
-------------

- Bump ansible-lint from 24.9.2 to 25.6.1 by @dependabot[bot] in https://github.com/grafana/grafana-ansible-collection/pull/391
- Bump brace-expansion from 1.1.11 to 1.1.12 in the npm_and_yarn group across 1 directory by @dependabot[bot] in https://github.com/grafana/grafana-ansible-collection/pull/396
- Changes for issue
- Update Mimir README.md by @Gufderald in https://github.com/grafana/grafana-ansible-collection/pull/397
- declare collection dependencies by @ishanjainn in https://github.com/grafana/grafana-ansible-collection/pull/390
- declare collection dependencies by @kleini in https://github.com/grafana/grafana-ansible-collection/pull/392
- ensure IP assert returns boolean result by @aardbol in https://github.com/grafana/grafana-ansible-collection/pull/398
- improve mimir/alloy examples playbook by @smCloudInTheSky in https://github.com/grafana/grafana-ansible-collection/pull/369
- store APT key with .asc extension by @derhuerst in https://github.com/grafana/grafana-ansible-collection/pull/394

v6.0.2
======

Major Changes
-------------

- Add delete protection by @KucicM in https://github.com/grafana/grafana-ansible-collection/pull/381
- Don't override defaults by @56quarters in https://github.com/grafana/grafana-ansible-collection/pull/382
- Don't use a proxy when doing Alloy readiness check by @benoitc-croesus in https://github.com/grafana/grafana-ansible-collection/pull/375
- Fix Mimir URL verify task by @parcimonic in https://github.com/grafana/grafana-ansible-collection/pull/358
- Fix some regression introduced by v6 by @voidquark in https://github.com/grafana/grafana-ansible-collection/pull/376
- Update when statement to test for dashboard files found by @hal58th in https://github.com/grafana/grafana-ansible-collection/pull/363
- Use become false in find task by @santilococo in https://github.com/grafana/grafana-ansible-collection/pull/368
- alloy_readiness_check_use_https by @piotr-g in https://github.com/grafana/grafana-ansible-collection/pull/359
- declare collection dependencies by @kleini in https://github.com/grafana/grafana-ansible-collection/pull/386
- ensure alerting provisioning directory exists by @derhuerst in https://github.com/grafana/grafana-ansible-collection/pull/364
- mark configuration deployment task with `no_log` by @kkantonop in https://github.com/grafana/grafana-ansible-collection/pull/380
- properly validate config by @pieterlexis-tomtom in https://github.com/grafana/grafana-ansible-collection/pull/354
- template ingester and querier section by @Gufderald in https://github.com/grafana/grafana-ansible-collection/pull/371
- use ansible_facts instead of variables by @kleini in https://github.com/grafana/grafana-ansible-collection/pull/365

v6.0.1
======

Minor Changes
-------------

- Remove Node modules from Ansible Collection build

v6.0.0
======

Major Changes
-------------

- Add foldersFromFilesStructure option by @root-expert in https://github.com/grafana/grafana-ansible-collection/pull/326
- Add tempo role by @CSTDev in https://github.com/grafana/grafana-ansible-collection/pull/323
- Do not log grafana.ini contents when setting facts by @root-expert in https://github.com/grafana/grafana-ansible-collection/pull/325
- Fix loki_operational_config section not getting rendered in config.yml by @olegkaspersky in https://github.com/grafana/grafana-ansible-collection/pull/330
- Fix sectionless items edge case by @santilococo in https://github.com/grafana/grafana-ansible-collection/pull/303
- Fix tags Inherit default vars by @MJurayev in https://github.com/grafana/grafana-ansible-collection/pull/341
- Fix the markdown code fences for install command by @benmatselby in https://github.com/grafana/grafana-ansible-collection/pull/306
- Grafana fix facts in main.yml by @voidquark in https://github.com/grafana/grafana-ansible-collection/pull/315
- Make dashboard imports more flexible by @torfbolt in https://github.com/grafana/grafana-ansible-collection/pull/308
- Make systemd create /var/lib/otel-collector by @pieterlexis-tomtom in https://github.com/grafana/grafana-ansible-collection/pull/336
- Validate config by @pieterlexis-tomtom in https://github.com/grafana/grafana-ansible-collection/pull/327
- add catalog-info file for internal dev catalog by @theSuess in https://github.com/grafana/grafana-ansible-collection/pull/317
- add publish step to GitHub Actions workflow for Ansible Galaxy by @thelooter in https://github.com/grafana/grafana-ansible-collection/pull/340
- add user module to create/update/delete grafana users by @mvalois in https://github.com/grafana/grafana-ansible-collection/pull/178
- force temporary directory even in check mode for  dashboards.yml by @cmehat in https://github.com/grafana/grafana-ansible-collection/pull/339
- integrate sles legacy init-script support by @floerica in https://github.com/grafana/grafana-ansible-collection/pull/184
- management of the config.river with the conversion of the config.yaml by @lbrule in https://github.com/grafana/grafana-ansible-collection/pull/149
- use ansible_facts instead of ansible_* variables by @kleini in https://github.com/grafana/grafana-ansible-collection/pull/296

v5.7.0
======

Major Changes
-------------

- Ability to set custom directory path for \*.alloy config files by @voidquark in https://github.com/grafana/grafana-ansible-collection/pull/294
- Add tests and support version latest by @pieterlexis-tomtom in https://github.com/grafana/grafana-ansible-collection/pull/299
- Fix 'dict object' has no attribute 'path' when running with --check by @JMLX42 in https://github.com/grafana/grafana-ansible-collection/pull/283
- Update grafana template by @santilococo in https://github.com/grafana/grafana-ansible-collection/pull/300
- add loki bloom support by @voidquark in https://github.com/grafana/grafana-ansible-collection/pull/298
- grafana.ini yaml syntax by @intermittentnrg in https://github.com/grafana/grafana-ansible-collection/pull/232

v5.6.0
======

Major Changes
-------------

- Adding "distributor" section support to mimir config file by @HamzaKhait in https://github.com/grafana/grafana-ansible-collection/pull/247
- Allow alloy_user_groups variable again by @pjezek in https://github.com/grafana/grafana-ansible-collection/pull/276
- Alloy Role Improvements by @voidquark in https://github.com/grafana/grafana-ansible-collection/pull/281
- Bump ansible-lint from 24.6.0 to 24.9.2 by @dependabot in https://github.com/grafana/grafana-ansible-collection/pull/270
- Bump pylint from 3.2.5 to 3.3.1 by @dependabot in https://github.com/grafana/grafana-ansible-collection/pull/273
- Ensure check-mode works for otel collector by @pieterlexis-tomtom in https://github.com/grafana/grafana-ansible-collection/pull/264
- Fix message argument of dashboard task by @Nemental in https://github.com/grafana/grafana-ansible-collection/pull/256
- Update Alloy variables to use the `grafana_alloy_` namespace so they are unique by @Aethylred in https://github.com/grafana/grafana-ansible-collection/pull/209
- Update README.md by @aioue in https://github.com/grafana/grafana-ansible-collection/pull/272
- Update README.md by @aioue in https://github.com/grafana/grafana-ansible-collection/pull/275
- Update main.yml by @aioue in https://github.com/grafana/grafana-ansible-collection/pull/274
- add grafana_plugins_ops to defaults and docs by @weakcamel in https://github.com/grafana/grafana-ansible-collection/pull/251
- add option to populate google_analytics_4_id value by @copolycube in https://github.com/grafana/grafana-ansible-collection/pull/249
- fix ansible-lint warnings on Forbidden implicit octal value "0640" by @copolycube in https://github.com/grafana/grafana-ansible-collection/pull/279

v5.5.1
======

Bugfixes
--------

- Add check_mode: false to Loki "Scrape GitHub" Task by @winsmith in https://github.com/grafana/grafana-ansible-collection/pull/262

v5.5.0
======

Major Changes
-------------

- add support for extra args by @harryfinbow in https://github.com/grafana/grafana-ansible-collection/pull/259
- mimir molecule should use ansible core 2.16 by @GVengelen in https://github.com/grafana/grafana-ansible-collection/pull/254

v5.4.1
======

Major Changes
-------------

- Updated promtail arch map for aarch64 matching by @gianmarco-mameli in https://github.com/grafana/grafana-ansible-collection/pull/257

v5.4.0
======

Major Changes
-------------

- Use a variable to control uninstall behavior instead of tags by @dobbi84 in https://github.com/grafana/grafana-ansible-collection/pull/253

v5.3.0
======

Major Changes
-------------

- Add a config check before restarting mimir by @panfantastic in https://github.com/grafana/grafana-ansible-collection/pull/198
- Add support for configuring feature_toggles in grafana role by @LexVar in https://github.com/grafana/grafana-ansible-collection/pull/173
- Backport post-setup healthcheck from agent to alloy by @v-zhuravlev in https://github.com/grafana/grafana-ansible-collection/pull/213
- Bump ansible-lint from 24.2.3 to 24.5.0 by @dependabot in https://github.com/grafana/grafana-ansible-collection/pull/207
- Bump ansible-lint from 24.5.0 to 24.6.0 by @dependabot in https://github.com/grafana/grafana-ansible-collection/pull/216
- Bump braces from 3.0.2 to 3.0.3 in the npm_and_yarn group across 1 directory by @dependabot in https://github.com/grafana/grafana-ansible-collection/pull/218
- Bump pylint from 3.1.0 to 3.1.1 by @dependabot in https://github.com/grafana/grafana-ansible-collection/pull/200
- Bump pylint from 3.1.1 to 3.2.2 by @dependabot in https://github.com/grafana/grafana-ansible-collection/pull/208
- Bump pylint from 3.2.2 to 3.2.3 by @dependabot in https://github.com/grafana/grafana-ansible-collection/pull/217
- Bump pylint from 3.2.3 to 3.2.5 by @dependabot in https://github.com/grafana/grafana-ansible-collection/pull/234
- Change from config.river to config.alloy by @cardasac in https://github.com/grafana/grafana-ansible-collection/pull/225
- Fix Grafana Configuration for Unified and Legacy Alerting Based on Version by @voidquark in https://github.com/grafana/grafana-ansible-collection/pull/215
- Fix env file location by @v-zhuravlev in https://github.com/grafana/grafana-ansible-collection/pull/211
- Support adding alloy user to extra groups by @v-zhuravlev in https://github.com/grafana/grafana-ansible-collection/pull/212
- Updated result.json['message'] to result.json()['message'] by @CPreun in https://github.com/grafana/grafana-ansible-collection/pull/223
- readme styling & language improvements by @tigattack in https://github.com/grafana/grafana-ansible-collection/pull/214

v5.2.0
======

Major Changes
-------------

- Add a new config part to configure KeyCloak based auth by @he0s in https://github.com/grafana/grafana-ansible-collection/pull/191
- Add promtail role by @voidquark in https://github.com/grafana/grafana-ansible-collection/pull/197
- Bump ansible-lint from 24.2.2 to 24.2.3 by @dependabot in https://github.com/grafana/grafana-ansible-collection/pull/195

v5.1.0
======

Major Changes
-------------

- Uninstall Step for Loki and Mimir by @voidquark in https://github.com/grafana/grafana-ansible-collection/pull/193

v5.0.0
======

Major Changes
-------------

- Add Grafana Loki role by @voidquark in https://github.com/grafana/grafana-ansible-collection/pull/188
- Add Grafana Mimir role by @GVengelen in https://github.com/grafana/grafana-ansible-collection/pull/183

v4.0.0
======

Major Changes
-------------

- Add an Ansible role for Grafana Alloy by @ishanjainn in https://github.com/grafana/grafana-ansible-collection/pull/169

Minor Changes
-------------

- Apply correct uid + gid for imported dashboards by @hypery2k in https://github.com/grafana/grafana-ansible-collection/pull/167
- Bump ansible-lint from 24.2.0 to 24.2.1 by @dependabot in https://github.com/grafana/grafana-ansible-collection/pull/164
- Bump ansible-lint from 24.2.0 to 24.2.1 by @dependabot in https://github.com/grafana/grafana-ansible-collection/pull/168
- Bump black from 24.1.1 to 24.3.0 by @dependabot in https://github.com/grafana/grafana-ansible-collection/pull/165
- Clarify grafana-server configuration in README by @VGerris in https://github.com/grafana/grafana-ansible-collection/pull/177
- Update description to match module by @brmurphy in https://github.com/grafana/grafana-ansible-collection/pull/179

v3.0.0
======

Major Changes
-------------

- Add an Ansible role for OpenTelemetry Collector by @ishanjainn in https://github.com/grafana/grafana-ansible-collection/pull/138

Minor Changes
-------------

- Bump pylint from 3.0.3 to 3.1.0 by @dependabot in https://github.com/grafana/grafana-ansible-collection/pull/158
- Bump pylint from 3.0.3 to 3.1.0 by @dependabot in https://github.com/grafana/grafana-ansible-collection/pull/161
- Bump the pip group across 1 directories with 1 update by @dependabot in https://github.com/grafana/grafana-ansible-collection/pull/156
- Bump yamllint from 1.33.0 to 1.35.1 by @dependabot in https://github.com/grafana/grafana-ansible-collection/pull/155
- Bump yamllint from 1.33.0 to 1.35.1 by @dependabot in https://github.com/grafana/grafana-ansible-collection/pull/159
- ExecStartPre and EnvironmentFile settings to system unit file by @fabiiw05 in https://github.com/grafana/grafana-ansible-collection/pull/157
- datasources url parameter fix by @dergudzon in https://github.com/grafana/grafana-ansible-collection/pull/162

v2.2.5
======

Release Summary
---------------

Grafana and Agent Role bug fixes and security updates

Minor Changes
-------------

- Add 'run_once' to download&unzip tasks by @v-zhuravlev in https://github.com/grafana/grafana-ansible-collection/pull/136
- Adding `oauth_allow_insecure_email_lookup` to fix oauth user sync error by @hypery2k in https://github.com/grafana/grafana-ansible-collection/pull/132
- Bump ansible-core from 2.15.4 to 2.15.8 by @dependabot in https://github.com/grafana/grafana-ansible-collection/pull/137
- Bump ansible-lint from 6.13.1 to 6.14.3 by @dependabot in https://github.com/grafana/grafana-ansible-collection/pull/139
- Bump ansible-lint from 6.14.3 to 6.22.2 by @dependabot in https://github.com/grafana/grafana-ansible-collection/pull/142
- Bump ansible-lint from 6.22.2 to 24.2.0 by @dependabot in https://github.com/grafana/grafana-ansible-collection/pull/150
- Bump jinja2 from 3.1.2 to 3.1.3 by @dependabot in https://github.com/grafana/grafana-ansible-collection/pull/129
- Bump pylint from 2.16.2 to 3.0.3 by @dependabot in https://github.com/grafana/grafana-ansible-collection/pull/141
- Bump yamllint from 1.29.0 to 1.33.0 by @dependabot in https://github.com/grafana/grafana-ansible-collection/pull/140
- Bump yamllint from 1.29.0 to 1.33.0 by @dependabot in https://github.com/grafana/grafana-ansible-collection/pull/143
- Bump yamllint from 1.33.0 to 1.34.0 by @dependabot in https://github.com/grafana/grafana-ansible-collection/pull/151
- Change handler to systemd by @v-zhuravlev in https://github.com/grafana/grafana-ansible-collection/pull/135
- Fix links in grafana_agent/defaults/main.yaml by @PabloCastellano in https://github.com/grafana/grafana-ansible-collection/pull/134
- Topic/grafana agent idempotency by @ohdearaugustin in https://github.com/grafana/grafana-ansible-collection/pull/147

v2.2.4
======

Release Summary
---------------

Grafana and Agent Role bug fixes and security updates

Minor Changes
-------------

- Bump cryptography from 41.0.4 to 41.0.6 by @dependabot in https://github.com/grafana/grafana-ansible-collection/pull/126
- Drop curl check by @v-zhuravlev in https://github.com/grafana/grafana-ansible-collection/pull/120
- Fix check mode for grafana role by @Boschung-Mecatronic-AG-Infrastructure in https://github.com/grafana/grafana-ansible-collection/pull/125
- Fix check mode in Grafana Agent by @AmandaCameron in https://github.com/grafana/grafana-ansible-collection/pull/124
- Update tags in README by @ishanjainn in https://github.com/grafana/grafana-ansible-collection/pull/121

v2.2.3
======

Release Summary
---------------

Remove dependency on local-fs.target from Grafana Agent role

Minor Changes
-------------

- Remove dependency on local-fs.target from Grafana Agent role

v2.2.2
======

Release Summary
---------------

Grafana Role bug fixes and security updates

Minor Changes
-------------

- Bump cryptography from 41.0.3 to 41.0.4
- Create missing notification directory in Grafana Role
- Remove check_mode from create local directory task in Grafana Role

v2.2.1
======

Release Summary
---------------

Allow alert resource provisioning in Grafana Role

Minor Changes
-------------

- Allow alert resource provisioning in Grafana Role

v2.2.0
======

Release Summary
---------------

Grafana Agent Role Updates

Minor Changes
-------------

- Use 'ansible_system' env variable to detect os typ in Grafana Agent Role
- hange grafana Agent Wal and Positions Directory in Grafana Agent Role

v2.1.9
======

Release Summary
---------------

Security Updates and Grafana Agent Version failure fixes

Minor Changes
-------------

- Add check for Curl and failure step if Agent Version is not retrieved
- Bump cryptography from 39.0.2 to 41.0.3
- Bump semver from 5.7.1 to 5.7.2
- Bump word-wrap from 1.2.3 to 1.2.5
- Create local dashboard directory in check mode
- Update CI Testing
- Update Cloud Stack Module failures

v2.1.8
======

Release Summary
---------------

Fix grafana dashboard import in Grafana Role

Minor Changes
-------------

- Fix grafana dashboard import in Grafana Role

v2.1.7
======

Release Summary
---------------

YAML Fixes

Minor Changes
-------------

- YAML Fixes

v2.1.6
======

Release Summary
---------------

Grafana and Grafana Agent role updates

Minor Changes
-------------

- Add overrides.conf with CAP_NET_BIND_SERVICE for grafana-server unit
- Fix Grafana Dashboard Import for Grafana Role
- Make grafana_agent Idempotent
- Provisioning errors in YAML
- Use new standard to configure Grafana APT source for Grafana Role

v2.1.5
======

Release Summary
---------------

Update Grafana Agent Download varibale and ZIP file

Minor Changes
-------------

- Add Grafana Agent Version and CPU Arch to Downloaded ZIP in Grafana Agent Role
- Move _grafana_agent_base_download_url from /vars to /defaults in Grafana Agent Role

v2.1.4
======

Release Summary
---------------

Update Datasource Tests and minor fixes

Minor Changes
-------------

- Datasource test updates and minor fixes

v2.1.3
======

Release Summary
---------------

Update modules to fix failing Sanity Tests

Minor Changes
-------------

- indentation and Lint fixes to modules

v2.1.2
======

Release Summary
---------------

Idempotency Updates and minor api_url fixes

Minor Changes
-------------

- Fix Deleting datasources
- Fix alert_notification_policy failing on fresh instance
- Making Deleting folders idempotent
- Remove trailing slash automatically from grafana_url

v2.1.1
======

Release Summary
---------------

Update Download tasks in Grafana Agent Role

Minor Changes
-------------

- Update Download tasks in Grafana Agent Role

v2.1.0
======

Release Summary
---------------

Add Grafana Server role and plugins support on-prem Grafana

Major Changes
-------------

- Addition of Grafana Server role by @gardar
- Configurable agent user groups by @NormanJS
- Grafana Plugins support on-prem Grafana installation by @ishanjainn
- Updated Service for flow mode by @bentonam

Minor Changes
-------------

- Ability to configure date format in grafana server role by @RomainMou
- Avoid using shell for fetching latest version in Grafana Agent Role by @gardar
- Fix for invalid yaml with datasources list enclosed in quotes by @elkozmon
- Remove agent installation custom check by @VLZZZ
- Remove explicit user creation check by @v-zhuravlev

v2.0.0
======

Release Summary
---------------

Updated Grafana Agent Role

Major Changes
-------------

- Added Lint support
- Configs for server, metrics, logs, traces, and integrations
- Installation of the latest version
- Local installations when internet connection is not allowed
- Only download binary to controller once instead of hosts
- Skip install if the agent is already installed and the version is the same as the requested version
- Support for Grafana Agent Flow
- Validation of variables

v1.1.1
======

Release Summary
---------------

Updated return description and value for grafana.grafana.folder module

Minor Changes
-------------

- Updated the return message in grafana.grafana.folder module

v1.1.0
======

Release Summary
---------------

Added Role to deploy Grafana Agent on linux hosts

Major Changes
-------------

- Added Role for Grafana Agent

v1.0.5
======

Release Summary
---------------

Add Note to modules which don't support Idempotency

Minor Changes
-------------

- Added Note to datasource and dashboard module about not supporting Idempotency

v1.0.4
======

Release Summary
---------------

Bug fixes and idempotency fixes for modules

Major Changes
-------------

- All modules except dashboard and datasource modules now support idempotency

Minor Changes
-------------

- All modules use `missing_required_lib`` to compose the message for module.fail_json() when required library is missing from host

Bugfixes
--------

- Fixed cases where cloud_stack and alert_contact_point modules do not return a tuple when nothing in loop matches

v1.0.3
======

Minor Changes
-------------

- Add a fail method to modules source code if `requests` library is not present
- Fixed markup for arg option in Documentation
- Updated Documentation with `notes` to specify if the check_mode feature is supported by modules
- removed `supports_check_mode=True` from source code of modules

v1.0.2
======

Release Summary
---------------

Documentation updates with updated description for modules

v1.0.1
======

Release Summary
---------------

Documentation updates with updated examples

v1.0.0
======

Release Summary
---------------

CI and testing improvements

v0.0.7
======

Release Summary
---------------

Documentation update for return values in `grafana.grafana.dashboard`

v0.0.6
======

Minor Changes
-------------

- Idempotency updates to cloud_api_key and datasource modules

v0.0.5
======

Release Summary
---------------

Documentation update and code cleanup

v0.0.4
======

Bugfixes
--------

- Fix an issue with `cloud_stack` idempotency

v0.0.3
======

Release Summary
---------------

Documentation update and code cleanup

v0.0.2
======

Release Summary
---------------

Updated input parameters description for all modules

v0.0.1
======

Release Summary
---------------

It's a release! First version to publish to Ansible Galaxy
