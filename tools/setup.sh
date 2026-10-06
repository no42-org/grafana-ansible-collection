#!/usr/bin/env bash

source "$(pwd)/tools/includes/utils.sh"

source "./tools/includes/logging.sh"

# output the heading
heading "Grafana Ansible Collection" "Performing Setup Checks"

# make sure shellcheck exists
info "Checking to see if shellcheck is installed"
if [[ "$(command -v shellcheck)" = "" ]]; then
  warning "shellcheck is required if running lint locally, see: (https://shellcheck.net) or run: brew install nvm && nvm install 18";
else
  success "shellcheck is installed"
fi

# make sure uv exists
if [[ "$(command -v uv)" = "" ]]; then
  warning "uv command is required, see (https://docs.astral.sh/uv/) or run: brew install uv";
else
  success "uv is installed"
fi
