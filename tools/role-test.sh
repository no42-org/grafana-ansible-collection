#!/usr/bin/env bash
#
# Run a role test against a container: converge, idempotence, verify.
#
# Replaces the Molecule workflows, which failed for two unrelated reasons: one
# pinned ansible-core against a floating Python and died at import, and the
# scenario files use platform keys current Molecule rejects. This harness
# depends only on ansible-core and docker, both already required.
#
# Three phases, in order:
#
#   converge      apply the role to a fresh container
#   idempotence   apply it again; fail if any task reports changed
#   verify        assert the expected end state
#
# Idempotence is the phase that matters most. Converge proves a role runs;
# idempotence proves it is a correct Ansible role, and it is the one thing
# converge cannot see.
#
# Usage: tools/role-test.sh <role> <distro>
#        tools/role-test.sh --list
#
#   <role>    a directory under tests/roles/
#   <distro>  a key from DISTRO_IMAGES below
#
# Containers are named deterministically and removed unconditionally before and
# after the run, so a crashed or interrupted run cannot poison the next one.

set -euo pipefail

source "$(pwd)/tools/includes/utils.sh"
source "$(pwd)/tools/includes/logging.sh"

# Distro families, not distros. One Debian-family and one RHEL-family entry is
# the minimum that exercises both package managers: carried contributions #538
# (module_hotfixes on a yum_repository) and #534 (the grafana_rhsm_* conditions)
# live behind `ansible_facts['pkg_mgr'] in ['yum','dnf']` and are unreachable on
# Debian.
#
# Both images run systemd and ship python3, verified before adoption. Neither
# needs its systemd path overridden: both declare /usr/lib/systemd/systemd as
# their own CMD.
readonly DISTRO_KEYS=("debian" "rhel")
distroImage() {
  case "${1}" in
    debian) echo "dokken/ubuntu-22.04" ;;
    rhel)   echo "dokken/almalinux-9" ;;
    *)      echo "" ;;
  esac
}

readonly TEST_ROOT="tests/roles"
readonly WORK_ROOT="build/role-test"

if [[ "${1:-}" == "--list" ]]; then
  echo "roles:"
  for d in "${TEST_ROOT}"/*/; do
    [[ -d "${d}" ]] && echo "  $(basename "${d}")"
  done
  echo "distros:"
  for k in "${DISTRO_KEYS[@]}"; do
    echo "  ${k}  ->  $(distroImage "${k}")"
  done
  exit 0
fi

role="${1:-}"
distro="${2:-}"

if [[ -z "${role}" ]] || [[ -z "${distro}" ]]; then
  echo >&2 "usage: tools/role-test.sh <role> <distro>"
  echo >&2 "       tools/role-test.sh --list"
  exit 1
fi

image="$(distroImage "${distro}")"
if [[ -z "${image}" ]]; then
  echo >&2 "unknown distro '${distro}'; run tools/role-test.sh --list"
  exit 1
fi

converge="${TEST_ROOT}/${role}/converge.yml"
verify="${TEST_ROOT}/${role}/verify.yml"

if [[ ! -f "${converge}" ]]; then
  echo >&2 "no converge playbook at ${converge}"
  exit 1
fi
if [[ ! -f "${verify}" ]]; then
  echo >&2 "no verify playbook at ${verify}"
  exit 1
fi

if [[ "$(command -v docker)" = "" ]]; then
  echo >&2 "docker command is required";
  exit 1;
fi
if [[ "$(command -v ansible-playbook)" = "" ]]; then
  echo >&2 "ansible-playbook is required; the role-test toolchain is not installed";
  exit 1;
fi

heading "Grafana Ansible Collection" "Role test: ${role} on ${distro}"

readonly container="roletest-${role}-${distro}"
readonly workDir="${WORK_ROOT}/${role}-${distro}"

# Unconditional cleanup. A role test that leaves containers behind makes the
# next run's result meaningless, so removal happens on every exit path.
cleanup() {
  docker rm -f "${container}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

info "removing any container left by a previous run"
cleanup

mkdir -p "${workDir}"

info "starting ${image} as ${container}"
docker run -d --name "${container}" \
  --privileged \
  --cgroupns=host \
  -v /sys/fs/cgroup:/sys/fs/cgroup:rw \
  "${image}" >/dev/null

# systemd needs a moment before service management works, and every role under
# test manages services.
info "waiting for systemd"
systemdReady=0
for _ in $(seq 1 30); do
  state="$(docker exec "${container}" systemctl is-system-running 2>/dev/null || true)"
  if [[ "${state}" == "running" ]] || [[ "${state}" == "degraded" ]]; then
    systemdReady=1
    break
  fi
  sleep 2
done
if [[ "${systemdReady}" -ne 1 ]]; then
  emergency "systemd did not come up in ${container}"
fi

cat > "${workDir}/inventory.yml" <<INV
---
all:
  hosts:
    ${container}:
      ansible_connection: community.docker.docker
      ansible_python_interpreter: /usr/bin/python3
INV

ANSIBLE_ROLES_PATH="$(pwd)/roles"
export ANSIBLE_ROLES_PATH
export ANSIBLE_NOCOWS=1
export ANSIBLE_RETRY_FILES_ENABLED=0
export ANSIBLE_HOST_KEY_CHECKING=False

# Control-node fixture directory, passed in as an absolute resolved path.
# It must not contain ".." segments: roles that derive names by stripping this
# value as a literal prefix from discovered paths produce nonsense otherwise.
fixturesDir="$(cd "$(dirname "${workDir}")" && pwd)/fixtures"
mkdir -p "${fixturesDir}"

runPlaybook() {
  local playbook="${1}"
  local logFile="${2}"
  ansible-playbook \
    -i "${workDir}/inventory.yml" \
    -e "role_test_fixtures=${fixturesDir}" \
    "${playbook}" 2>&1 | tee "${logFile}"
  return "${PIPESTATUS[0]}"
}

# ---------------------------------------------------------------- converge
info "phase 1/3: converge"
if ! runPlaybook "${converge}" "${workDir}/converge.log"; then
  emergency "converge failed; idempotence and verify were not run"
fi
success "converge passed"

# ------------------------------------------------------------- idempotence
info "phase 2/3: idempotence — applying the role a second time"
if ! runPlaybook "${converge}" "${workDir}/idempotence.log"; then
  emergency "the second converge failed outright"
fi

# The recap is the authoritative count: a task that reports changed on a second
# identical run is a role that flaps, which converge alone cannot detect.
changedTotal="$(
  grep -oE 'changed=[0-9]+' "${workDir}/idempotence.log" \
    | cut -d= -f2 \
    | awk '{ sum += $1 } END { print sum + 0 }'
)"

if [[ "${changedTotal}" -ne 0 ]]; then
  error "the second run reported ${changedTotal} changed task(s); the role is not idempotent"
  grep -E '^(changed|TASK)' "${workDir}/idempotence.log" | grep -B1 '^changed' | head -40 >&2 || true
  emergency "idempotence failed"
fi
success "idempotence passed: 0 changed tasks on the second run"

# ------------------------------------------------------------------ verify
info "phase 3/3: verify"
if ! runPlaybook "${verify}" "${workDir}/verify.log"; then
  emergency "verify failed"
fi
success "verify passed"

success "role test passed: ${role} on ${distro} (${image})"
