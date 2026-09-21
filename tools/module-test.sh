#!/usr/bin/env bash
#
# Run a plugin module against a running Grafana.
#
# The role tests cover roles/. Nothing covered plugins/, and the modules are
# the part of this collection whose entire behaviour is the shape of an HTTP
# request. Upstream issue #537 is what that produced: Grafana 13.0 removed
# `PUT /api/datasources/:id`, the datasource module addressed a data source by
# exactly that route, and every update failed with a bare 404 for as long as it
# took a user to report it.
#
# A mock cannot see that. What changed is which routes Grafana serves, so the
# test has to ask a Grafana. This harness starts one, mints a token against it,
# and runs tests/modules/<module>/verify.yml on the control node.
#
# Two things are read rather than declared, for the same reason in both cases:
#
#   grafana_version    from roles/grafana/defaults/main.yml, so the Grafana
#                      under test is the Grafana the role installs. A version
#                      named here as well would be a second definition, and the
#                      one that matters is what a consumer gets.
#   ansible-core       from pyproject.toml's `module-test` group through uv,
#                      never from PATH. tools/role-test.sh has the long version
#                      of why: a local pass and a CI pass have to be statements
#                      about the same engine.
#
# The module runs on the control node against an HTTP endpoint, so unlike a
# role test there is nothing to provision inside the container and no inventory
# beyond localhost.
#
# tests/integration/targets/ is a different thing, inherited and dormant: it is
# written for `ansible-test integration` against a Grafana Cloud stack this
# fork has no credentials for, and has never run here. It stays byte-identical
# so an upstream merge does not conflict on it.
#
# Usage: tools/module-test.sh <module>
#        tools/module-test.sh --list
#
#   <module>  a directory under tests/modules/
#
# MODULE_TEST_GRAFANA_VERSION runs the same scenario against another Grafana,
# for establishing when a route appeared or went away. Unset, the role's pin
# decides.

set -euo pipefail

source "$(pwd)/tools/includes/utils.sh"
source "$(pwd)/tools/includes/logging.sh"

readonly TEST_ROOT="tests/modules"
readonly WORK_ROOT="build/module-test"

if [[ "${1:-}" == "--list" ]]; then
  echo "modules:"
  for d in "${TEST_ROOT}"/*/; do
    [[ -d "${d}" ]] && echo "  $(basename "${d}")"
  done
  exit 0
fi

module="${1:-}"

if [[ -z "${module}" ]]; then
  echo >&2 "usage: tools/module-test.sh <module>"
  echo >&2 "       tools/module-test.sh --list"
  exit 1
fi

verify="${TEST_ROOT}/${module}/verify.yml"
if [[ ! -f "${verify}" ]]; then
  echo >&2 "no verify playbook at ${verify}; run tools/module-test.sh --list"
  exit 1
fi

for tool in docker curl python3; do
  if [[ "$(command -v "${tool}")" = "" ]]; then
    echo >&2 "${tool} command is required";
    exit 1;
  fi
done
if [[ "$(command -v uv)" = "" ]]; then
  echo >&2 "TOOLCHAIN NOT INSTALLED: uv is required, see (https://docs.astral.sh/uv/) or run: brew install uv";
  exit 1;
fi

# The `module-test` group: the declared ansible-core plus requests, which the
# modules import and which the control node therefore needs.
ansiblePlaybook=(uv run --frozen --group module-test ansible-playbook)
if ! ansibleVersion="$("${ansiblePlaybook[@]}" --version </dev/null 2>/dev/null | head -1)"; then
  echo >&2 "TOOLCHAIN NOT INSTALLED: ansible-core is not available. Run \"make install\".";
  exit 1;
fi
if [[ -z "${ansibleVersion}" ]]; then
  echo >&2 "TOOLCHAIN NOT INSTALLED: ansible-core is not available. Run \"make install\".";
  exit 1;
fi

# The version the grafana role installs. Read from the role's defaults, where
# the weekly pin bump writes it, so a bump moves this test with it. For Grafana
# the package version and the image tag are the same string.
# MODULE_TEST_GRAFANA_VERSION overrides it for a by-hand range check, which is
# how the 404 boundary in the datasource scenario's header was established. It
# is not a second definition of the version under test: unset, which is how CI
# and every ordinary run leave it, the role's pin decides.
grafanaVersion="${MODULE_TEST_GRAFANA_VERSION:-}"
if [[ -z "${grafanaVersion}" ]]; then
  grafanaVersion="$(awk -F'"' '/^grafana_version:/ {print $2; exit}' roles/grafana/defaults/main.yml)"
  grafanaVersionSource="roles/grafana/defaults/main.yml"
else
  grafanaVersionSource="MODULE_TEST_GRAFANA_VERSION"
fi
readonly grafanaVersionSource
if [[ -z "${grafanaVersion}" ]]; then
  echo >&2 "could not read grafana_version from roles/grafana/defaults/main.yml";
  exit 1;
fi
readonly grafanaVersion
readonly image="grafana/grafana:${grafanaVersion}"

heading "Grafana Ansible Collection" "Module test: ${module}"

info "engine: ${ansibleVersion} from dependency group 'module-test'"
info "grafana: ${grafanaVersion} (${grafanaVersionSource})"

readonly container="moduletest-${module}"
readonly label="moduletest=${module}"
readonly workDir="${WORK_ROOT}/${module}"

# Admin credentials for the container only. They exist to mint the service
# account token below and are never what the module is given: Grafana 13
# removed API key creation, and a service account token is what a consumer now
# authenticates with.
readonly adminUser="admin"
readonly adminPassword="module-test"

cleanup() {
  local ids
  ids="$(docker ps -aq --filter "label=${label}" 2>/dev/null || true)"
  if [[ -n "${ids}" ]]; then
    # shellcheck disable=SC2086
    docker rm -f ${ids} >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

info "removing anything left by a previous run"
cleanup

mkdir -p "${workDir}"

# Port 0, so docker assigns one. A fixed 3000 collides with whatever the
# developer already has running, and this harness is meant to be run locally.
info "starting ${image}"
docker run -d --name "${container}" \
  --label "${label}" \
  -p 0:3000 \
  -e "GF_SECURITY_ADMIN_USER=${adminUser}" \
  -e "GF_SECURITY_ADMIN_PASSWORD=${adminPassword}" \
  "${image}" >/dev/null

# docker port prints one line per published address, IPv4 and IPv6. The host
# port is the same in both.
hostPort="$(docker port "${container}" 3000/tcp | head -1 | sed 's/.*://')"
if [[ -z "${hostPort}" ]]; then
  emergency "could not read the published port of ${container}"
fi
readonly hostPort
readonly grafanaUrl="http://127.0.0.1:${hostPort}"
readonly adminUrl="http://${adminUser}:${adminPassword}@127.0.0.1:${hostPort}"

# `database: ok` rather than a 200 from /api/health: Grafana answers that
# endpoint while it is still migrating its database, and an API call made in
# that window fails for a reason that has nothing to do with the module.
info "waiting for grafana at ${grafanaUrl}"
ready=0
for _ in $(seq 1 90); do
  if curl -fsS "${adminUrl}/api/health" 2>/dev/null | grep -q '"database": *"ok"'; then
    ready=1
    break
  fi
  sleep 2
done
if [[ "${ready}" -ne 1 ]]; then
  docker logs "${container}" 2>&1 | tail -40 >&2 || true
  emergency "grafana did not become ready"
fi

info "minting an admin service account token"
saResponse="$(
  curl -fsS -X POST "${adminUrl}/api/serviceaccounts" \
    -H 'Content-Type: application/json' \
    -d '{"name":"module-test","role":"Admin","isDisabled":false}'
)"
saId="$(printf '%s' "${saResponse}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')"
tokenResponse="$(
  curl -fsS -X POST "${adminUrl}/api/serviceaccounts/${saId}/tokens" \
    -H 'Content-Type: application/json' \
    -d '{"name":"module-test"}'
)"
apiKey="$(printf '%s' "${tokenResponse}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["key"])')"
if [[ -z "${apiKey}" ]]; then
  emergency "could not mint a service account token"
fi
readonly apiKey

# ansible resolves `grafana.grafana.<module>` from
# <path>/ansible_collections/<namespace>/<name>, and this repository *is* that
# collection without being laid out as one. tools/sanity.sh copies the tree to
# satisfy the same requirement; here it is a symlink, because a copy would test
# whatever the copy was made from and the point is to test the working tree.
#
# The repository root stays on the path as well, so collections installed into
# ./ansible_collections by ansible-lint or the role harness still resolve.
namespace="$(awk '/^namespace:/ {print $2; exit}' galaxy.yml | tr -d '"'"'"'')"
name="$(awk '/^name:/ {print $2; exit}' galaxy.yml | tr -d '"'"'"'')"
if [[ -z "${namespace}" || -z "${name}" ]]; then
  emergency "could not read namespace/name from galaxy.yml"
fi
info "collection: ${namespace}.${name}"

collectionsRoot="${workDir}/collections"
rm -rf "${collectionsRoot}"
mkdir -p "${collectionsRoot}/ansible_collections/${namespace}"
ln -s "$(pwd)" "${collectionsRoot}/ansible_collections/${namespace}/${name}"

ANSIBLE_COLLECTIONS_PATH="$(cd "${collectionsRoot}" && pwd):$(pwd)"
export ANSIBLE_COLLECTIONS_PATH
export ANSIBLE_NOCOWS=1
export ANSIBLE_RETRY_FILES_ENABLED=0

info "running ${verify}"
set +e
"${ansiblePlaybook[@]}" \
  -i localhost, \
  -e "ansible_connection=local" \
  -e "grafana_url=${grafanaUrl}" \
  -e "grafana_api_key=${apiKey}" \
  "${verify}" 2>&1 | tee "${workDir}/verify.log"
status="${PIPESTATUS[0]}"
set -e

if [[ "${status}" -ne 0 ]]; then
  emergency "module test failed: ${module} against grafana ${grafanaVersion}"
fi

success "module test passed: ${module} against grafana ${grafanaVersion}"
