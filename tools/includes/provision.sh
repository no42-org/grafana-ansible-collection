#!/usr/bin/env bash
#
# Download, verify and cache a pinned tool binary.
#
# Three tools reach this repository as released binaries rather than through a
# package manager: shellcheck, actionlint and editorconfig-checker. Each has a
# script beside this one declaring its version, its per-platform asset name and
# that asset's sha256. This file holds the part that would otherwise be written
# three times.
#
# The split is deliberate and matches what went wrong before. A tool's version
# lives with the tool, never in a shared table: `yamllint` was pinned to 1.35.1
# in pyproject.toml and 1.38.0 in gate.yml precisely because its version had
# drifted away from the code that invoked it. What is shared here is mechanism,
# not policy.
#
# Verification is mandatory. provisionBinary refuses to run without an expected
# hash, so a tool cannot be added that silently skips the check.

# provisionBinary
# -----------------------------------
# Usage: provisionBinary <name> <version> <url> <sha256> <find-pattern>
#
# Echoes a path to the verified binary, downloading it into tools/bin on first
# use. Every failure is loud and returns non-zero: a gate that cannot obtain its
# linter must fail, never fall back to an unpinned copy on PATH. An unpinned
# linter is a gate that can change what it demands with nothing committed.
# -----------------------------------
provisionBinary() {
  local name="${1}" version="${2}" url="${3}" expected="${4}" pattern="${5}"

  if [[ -z "${name}" || -z "${version}" || -z "${url}" || -z "${pattern}" ]]; then
    echo >&2 "TOOLCHAIN NOT INSTALLED: provisionBinary called without all of name, version, url, pattern"
    return 1
  fi

  # Not optional, and checked before anything is fetched. A tool added without
  # a hash would otherwise provision happily and quietly weaken the guarantee
  # for every tool beside it.
  if [[ -z "${expected}" ]]; then
    echo >&2 "TOOLCHAIN NOT INSTALLED: ${name} declares no expected sha256; refusing to provision unverified"
    return 1
  fi

  local binDir bin
  binDir="$(pwd)/tools/bin"
  bin="${binDir}/${name}-${version}"

  if [[ -x "${bin}" ]]; then
    echo "${bin}"
    return 0
  fi

  mkdir -p "${binDir}"
  local tmp
  tmp="$(mktemp -d)"

  local archive="${tmp}/${name}-download"
  if ! curl -fsSL "${url}" -o "${archive}"; then
    echo >&2 "TOOLCHAIN NOT INSTALLED: could not download ${url}"
    rm -rf "${tmp}"
    return 1
  fi

  local actual
  actual="$(shasum -a 256 "${archive}" | cut -d' ' -f1)"
  if [[ "${actual}" != "${expected}" ]]; then
    echo >&2 "TOOLCHAIN NOT INSTALLED: ${name} ${version} checksum mismatch"
    echo >&2 "  url      ${url}"
    echo >&2 "  expected ${expected}"
    echo >&2 "  actual   ${actual}"
    echo >&2 "A release asset changed, or the download was tampered with. Do not"
    echo >&2 "update the pinned hash without establishing which."
    rm -rf "${tmp}"
    return 1
  fi

  # tar reads both .gz and .xz without being told which.
  if ! tar -xf "${archive}" -C "${tmp}"; then
    echo >&2 "TOOLCHAIN NOT INSTALLED: could not unpack ${name} ${version}"
    rm -rf "${tmp}"
    return 1
  fi

  local extracted
  extracted="$(find "${tmp}" -type f -name "${pattern}" ! -name '*.tar.*' ! -name '*.json' ! -name '*-download' | head -1)"
  if [[ -z "${extracted}" ]]; then
    echo >&2 "TOOLCHAIN NOT INSTALLED: no binary matching '${pattern}' inside the ${name} archive"
    rm -rf "${tmp}"
    return 1
  fi

  mv "${extracted}" "${bin}"
  chmod +x "${bin}"
  rm -rf "${tmp}"
  echo "${bin}"
}

# platformAsset
# -----------------------------------
# Usage: platformAsset <tool-name> <darwin-arm64> <darwin-amd64> <linux-arm64> <linux-amd64>
#
# Echoes the caller's value for the current platform, or fails naming the
# platform it could not serve. shellcheck 0.9.0 shipped no darwin.aarch64
# build, so a pin can be unusable on a maintainer's machine while looking
# perfectly reasonable in a workflow that only ever runs on linux.
# -----------------------------------
platformAsset() {
  local name="${1}" darwinArm="${2}" darwinAmd="${3}" linuxArm="${4}" linuxAmd="${5}"
  local os arch
  os="$(uname -s | tr '[:upper:]' '[:lower:]')"
  arch="$(uname -m)"

  case "${os}/${arch}" in
    darwin/arm64 | darwin/aarch64) echo "${darwinArm}" ;;
    darwin/x86_64)                 echo "${darwinAmd}" ;;
    linux/arm64 | linux/aarch64)   echo "${linuxArm}" ;;
    linux/x86_64)                  echo "${linuxAmd}" ;;
    *)
      echo >&2 "TOOLCHAIN NOT INSTALLED: no ${name} build pinned for ${os}/${arch}"
      return 1
      ;;
  esac
}
