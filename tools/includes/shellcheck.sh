#!/usr/bin/env bash
#
# Provisions shellcheck, pinned and checksum-verified.
#
# Before this, shellcheck came from whatever was on PATH locally and from a
# wget of 0.9.0 in gate.yml. Two definitions of one version, and they had
# already diverged: the maintainer's machine ran 0.11.0 while every CI run
# measured 0.9.0. A green local `make ci-lint-shell` said nothing about CI.
#
# Pinned to 0.11.0, which is the current release, rather than to CI's 0.9.0.
# Two reasons, measured 2026-09-11 rather than assumed:
#
#   Findings are identical. Both versions report 0 findings across the same 19
#   scripts, compared through the official container images so neither had a
#   platform advantage. Moving forward costs no finding churn.
#
#   0.9.0 cannot run here at all. It publishes darwin.x86_64 but no
#   darwin.aarch64, so adopting CI's pin would have made this gate unrunnable
#   on Apple Silicon. That is the editorconfig-checker@5.0.1 defect again: a
#   pinned tool with no build for the platform the maintainer uses.
#
# The hashes below are computed from the official release assets, not published
# by upstream: shellcheck ships no checksums file, unlike actionlint and
# editorconfig-checker. That is weaker, because it cannot detect an asset that
# was already wrong when first fetched. It still detects any later change to a
# release asset that is immutable by convention, which is the realistic risk.
# Do not refresh a hash to make a download pass without establishing why it
# moved.

readonly SHELLCHECK_VERSION="0.11.0"

# Provides: shellcheckBin
# -----------------------------------
# Echoes a path to the pinned, verified shellcheck, downloading it on first use.
#
# The banner above does not read "# shellcheckBin". A comment beginning with
# "# shellcheck" is parsed as a shellcheck *directive*, so the obvious banner
# makes shellcheck fail this file with SC1073 before reading any of it.
# -----------------------------------
shellcheckBin() {
  local asset sha
  asset="$(platformAsset shellcheck \
    "shellcheck-v${SHELLCHECK_VERSION}.darwin.aarch64.tar.xz" \
    "shellcheck-v${SHELLCHECK_VERSION}.darwin.x86_64.tar.xz" \
    "shellcheck-v${SHELLCHECK_VERSION}.linux.aarch64.tar.xz" \
    "shellcheck-v${SHELLCHECK_VERSION}.linux.x86_64.tar.xz")" || return 1

  sha="$(platformAsset shellcheck \
    "56affdd8de5527894dca6dc3d7e0a99a873b0f004d7aabc30ae407d3f48b0a79" \
    "3c89db4edcab7cf1c27bff178882e0f6f27f7afdf54e859fa041fca10febe4c6" \
    "12b331c1d2db6b9eb13cfca64306b1b157a86eb69db83023e261eaa7e7c14588" \
    "8c3be12b05d5c177a04c29e3c78ce89ac86f1595681cab149b65b97c4e227198")" || return 1

  local url="https://github.com/koalaman/shellcheck/releases/download"
  url="${url}/v${SHELLCHECK_VERSION}/${asset}"

  provisionBinary shellcheck "${SHELLCHECK_VERSION}" "${url}" "${sha}" "shellcheck"
}
