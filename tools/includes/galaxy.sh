#!/usr/bin/env bash
#
# Installing ansible collections from a requirements file, once, for every
# caller that needs it.
#
# There are two such callers and they used to be one: tools/role-test.sh grew
# bounded retries after a Galaxy outage turned one job of twelve red, and
# tools/lint-ansible.sh had none at all, which is how an HTTP 502 from Galaxy
# failed "Gate / Lint the collection" outright. Two copies of this logic would
# have drifted the way yamllint's two pinned versions drifted, so there is one.
#
# Usage, having sourced logging.sh first:
#
#   GALAXY_CMD=(uv run --frozen --group lint ansible-galaxy)
#   galaxyInstall requirements.yml            # always installs
#   galaxyInstall tests/roles/requirements.yml offline-first
#
# The second argument asks for an offline probe before the install. It is worth
# it only when the requirements resolve from Galaxy: `--offline` resolves the
# same dependency map against local artifacts, so a satisfied set answers in
# about a quarter of a second and opens no socket. A requirements file using
# `type: git` re-clones whatever it names regardless, so asking for the probe
# there buys nothing and the caller should not.
#
# On failure this exits the calling script. Returning would let a caller
# continue with collections it does not have, and `ansible-lint --offline`
# reports a clean pass on a tree whose collections are absent -- a linter that
# could not resolve its dependencies saying nothing is wrong.

# galaxyInstall <requirements file> [offline-first]
galaxyInstall() {
  local requirementsFile="${1}"
  local offlineFirst="${2:-}"

  if [[ ! -f "${requirementsFile}" ]]; then
    echo >&2 "missing ${requirementsFile}; cannot resolve collections";
    exit 1;
  fi

  info "resolving collections from ${requirementsFile}"

  if [[ "${offlineFirst}" == "offline-first" ]]; then
    if "${GALAXY_CMD[@]}" collection install -r "${requirementsFile}" --offline </dev/null >/dev/null 2>&1; then
      info "collections on disk already satisfy ${requirementsFile}; not contacting galaxy"
      return 0
    fi
  fi

  # Bounded retries for the transient case. The window backs off from 10
  # seconds over five attempts rather than waiting a fixed 15 over three,
  # because three attempts 15 seconds apart survive a 30-second outage and the
  # outage that turned `loki (debian)` red outlasted it: galaxy.ansible.com
  # reset the connection on all three inside 31 seconds.
  #
  # The odds are the reason a rare per-call failure is worth this much code.
  # Every role-test job resolves independently and the matrices run roughly two
  # dozen per push, so a service that fails occasionally per call fails
  # somewhere in almost every run.
  local attempts=5 backoff=10 installed=0 output="" attempt
  for attempt in $(seq 1 "${attempts}"); do
    # Success is the exit status, never the output. This once cleared the
    # captured output on success and tested it for emptiness afterwards, which
    # reads a silent failure as a success: ansible-galaxy prints an ERROR line
    # today, so it never fired, but it was a dependency on the tool staying
    # noisy.
    if output="$("${GALAXY_CMD[@]}" collection install -r "${requirementsFile}" </dev/null 2>&1)"; then
      installed=1
      break
    fi
    if [[ "${attempt}" -lt "${attempts}" ]]; then
      info "collection install failed, attempt ${attempt} of ${attempts}; retrying in ${backoff}s"
      sleep "${backoff}"
      backoff=$(( backoff * 2 ))
    fi
  done

  if [[ "${installed}" -eq 0 ]]; then
    [[ -n "${output}" ]] && echo "${output}" >&2
    echo >&2 "TOOLCHAIN NOT INSTALLED: could not install the collections in ${requirementsFile} after ${attempts} attempts";
    exit 1;
  fi
}
