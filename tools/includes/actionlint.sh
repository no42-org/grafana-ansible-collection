#!/usr/bin/env bash
#
# Provisions actionlint, pinned and checksum-verified.
#
# Before this it came from whatever was on PATH locally and from a wget in
# gate.yml, so `make ci-lint-release` could not run at all on a clean checkout:
# it exited at the tool guard and abandoned the five checks after it.
#
# The hashes are from the release's own actionlint_<version>_checksums.txt,
# published by upstream, unlike shellcheck's which are computed here.

readonly ACTIONLINT_VERSION="1.7.12"

# actionlintBin
# -----------------------------------
# Echoes a path to the pinned, verified actionlint, downloading it on first use.
# -----------------------------------
actionlintBin() {
  local asset sha
  asset="$(platformAsset actionlint \
    "actionlint_${ACTIONLINT_VERSION}_darwin_arm64.tar.gz" \
    "actionlint_${ACTIONLINT_VERSION}_darwin_amd64.tar.gz" \
    "actionlint_${ACTIONLINT_VERSION}_linux_arm64.tar.gz" \
    "actionlint_${ACTIONLINT_VERSION}_linux_amd64.tar.gz")" || return 1

  sha="$(platformAsset actionlint \
    "aba9ced2dee8d27fecca3dc7feb1a7f9a52caefa1eb46f3271ea66b6e0e6953f" \
    "5b44c3bc2255115c9b69e30efc0fecdf498fdb63c5d58e17084fd5f16324c644" \
    "325e971b6ba9bfa504672e29be93c24981eeb1c07576d730e9f7c8805afff0c6" \
    "8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8")" || return 1

  local url="https://github.com/rhysd/actionlint/releases/download"
  url="${url}/v${ACTIONLINT_VERSION}/${asset}"

  provisionBinary actionlint "${ACTIONLINT_VERSION}" "${url}" "${sha}" "actionlint"
}
