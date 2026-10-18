# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Ronny Trommer <ronny@no42.org>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import contextlib
import json

import pytest

from ansible.module_utils import basic
from ansible.module_utils.common.text.converters import to_bytes
from ansible_collections.grafana.grafana.plugins.modules import cloud_plugin

try:
    from ansible.module_utils.testing import patch_module_args
except ImportError:
    # ansible-core before 2.19 reads module arguments from this global.
    @contextlib.contextmanager
    def patch_module_args(args):
        saved = basic._ANSIBLE_ARGS
        basic._ANSIBLE_ARGS = to_bytes(json.dumps({'ANSIBLE_MODULE_ARGS': args}))
        try:
            yield
        finally:
            basic._ANSIBLE_ARGS = saved

CLOUD_API_KEY = 'cloud-token'

# The fields main() reads, as the module's RETURN documentation describes
# them. Nothing here was confirmed against the Grafana Cloud API.
PLUGIN = {
    'pluginId': 663,
    'pluginName': 'GitHub',
    'pluginSlug': 'grafana-github-datasource',
    'version': '1.0.14',
    'latestVersion': '1.0.15',
}


class Response(object):
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body


class Recorder(object):
    """Stands in for one requests function and keeps every call's headers."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.headers = []

    def __call__(self, url, **kwargs):
        self.headers.append(kwargs.get('headers'))
        return self.responses.pop(0)


def run_module(monkeypatch, state, version, post=None, get=None, delete=None):
    for name, fake in (('post', post), ('get', get), ('delete', delete)):
        monkeypatch.setattr(cloud_plugin.requests, name, fake or Recorder())
    args = {
        'name': 'grafana-github-datasource',
        'version': version,
        'stack_slug': 'example',
        'cloud_api_key': CLOUD_API_KEY,
        'state': state,
        '_ansible_remote_tmp': '/tmp',
        '_ansible_keep_remote_files': False,
    }
    with patch_module_args(args):
        with pytest.raises(SystemExit) as exit_info:
            cloud_plugin.main()
    return exit_info.value.code


def assert_authenticated(recorder, calls):
    assert len(recorder.headers) == calls
    for headers in recorder.headers:
        assert headers['Authorization'] == 'Bearer ' + CLOUD_API_KEY


def test_present_installs_with_cloud_api_key(monkeypatch):
    post = Recorder(Response(200, PLUGIN))

    assert run_module(monkeypatch, 'present', '1.0.14', post=post) == 0
    assert_authenticated(post, 1)


def test_present_updates_with_cloud_api_key(monkeypatch):
    post = Recorder(Response(409, {'message': 'already installed'}), Response(200, PLUGIN))
    get = Recorder(Response(200, PLUGIN))

    assert run_module(monkeypatch, 'present', '1.0.15', post=post, get=get) == 0
    assert_authenticated(post, 2)
    assert_authenticated(get, 1)


def test_absent_deletes_with_cloud_api_key(monkeypatch):
    delete = Recorder(Response(200, PLUGIN))

    assert run_module(monkeypatch, 'absent', 'latest', delete=delete) == 0
    assert_authenticated(delete, 1)
