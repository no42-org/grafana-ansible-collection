#!/usr/bin/env bash
#
# Provisions the standalone editorconfig-checker binary, pinned and verified.
#
# The Node package `editorconfig-checker@5.0.1` was used before. It downloads a
# platform binary at install time and ships none for darwin-arm64, and when it
# cannot find one it prints a stack trace and **exits 0**:
#
#   Error: ENOENT: no such file or directory, scandir
#     '.../node_modules/editorconfig-checker/bin/latest/bin'
#   exit=0
#
# So `make ci-lint-editorconfig` reported success on any Apple Silicon machine
# without checking a single file. lint-gates requires that a gate fail when its
# linter cannot run, and a wrapper that swallows its own crash cannot satisfy
# that. The standalone Go binary has no such wrapper.
#
# This file used to claim it followed the "same pattern as shellcheck and
# actionlint". It did not: neither of those was provisioned at all, and the
# sentence described an intention as though it were done. They are provisioned
# now, beside this file, and all three share tools/includes/provision.sh.
#
# The hashes are from the release's own checksums.txt, published by upstream.

readonly EDITORCONFIG_CHECKER_VERSION="4.0.1"

# editorconfigCheckerBin
# -----------------------------------
# Echoes a path to the pinned, verified binary, downloading it on first use.
# Fails loudly rather than falling back to an unpinned copy on PATH: an
# unpinned linter is a gate that can change what it demands without anyone
# changing the repository.
# -----------------------------------
editorconfigCheckerBin() {
  local asset sha
  # Upstream ships one universal darwin build rather than per-architecture ones.
  asset="$(platformAsset editorconfig-checker \
    "editorconfig-checker-darwin-all.tar.gz" \
    "editorconfig-checker-darwin-all.tar.gz" \
    "editorconfig-checker-linux-arm64.tar.gz" \
    "editorconfig-checker-linux-amd64.tar.gz")" || return 1

  sha="$(platformAsset editorconfig-checker \
    "9ed547505176d7384e1fb861ecfdd13df8c15e37d4bbcc2bd40e52e81ab32176" \
    "9ed547505176d7384e1fb861ecfdd13df8c15e37d4bbcc2bd40e52e81ab32176" \
    "f162c749ade763ed4954de678ebb786c99431b9a615a964c284605e68dbbd3f9" \
    "90139c6ed52373c0acfc9deb2a07aa812e5184753afd4bc8252bf44eb4909155")" || return 1

  local url="https://github.com/editorconfig-checker/editorconfig-checker/releases/download"
  url="${url}/v${EDITORCONFIG_CHECKER_VERSION}/${asset}"

  provisionBinary editorconfig-checker "${EDITORCONFIG_CHECKER_VERSION}" "${url}" "${sha}" "editorconfig-checker*"
}
