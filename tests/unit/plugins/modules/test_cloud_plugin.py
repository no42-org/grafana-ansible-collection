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
    """A requests response. A str body is not JSON, as an HTML error page is not."""

    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body
        self.text = body if isinstance(body, str) else json.dumps(body)

    def json(self):
        if isinstance(self._body, str):
            raise ValueError('Expecting value: line 1 column 1 (char 0)')
        return self._body


class Recorder(object):
    """Stands in for one requests function and keeps every call's headers."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.headers = []

    def __call__(self, url, **kwargs):
        self.headers.append(kwargs.get('headers'))
        assert self.responses, 'unexpected request to %s' % url
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


def run_module_succeeding(monkeypatch, capsys, state, version, **fakes):
    """Run the module, require it to succeed, and return its result."""
    capsys.readouterr()
    assert run_module(monkeypatch, state, version, **fakes) == 0
    return json.loads(capsys.readouterr().out)


def run_module_failing(monkeypatch, capsys, state, version, **fakes):
    """Run the module, require it to fail cleanly, and return its msg.

    An exception escaping main() is not caught here, so a refusal that raises
    fails the test with its own traceback.
    """
    capsys.readouterr()
    assert run_module(monkeypatch, state, version, **fakes) == 1
    result = json.loads(capsys.readouterr().out)
    assert result['failed'] is True
    return result['msg']


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


def test_refusal_with_a_message_fails_with_it(monkeypatch, capsys):
    post = Recorder(Response(403, {'message': 'Forbidden'}))

    msg = run_module_failing(monkeypatch, capsys, 'present', '1.0.14', post=post)
    assert msg == {'status': 403, 'response': 'Forbidden'}


def test_json_refusal_without_a_message_fails_with_the_body(monkeypatch, capsys):
    delete = Recorder(Response(401, {'error': 'invalid token'}))

    msg = run_module_failing(monkeypatch, capsys, 'absent', 'latest', delete=delete)
    assert msg == {'status': 401, 'response': {'error': 'invalid token'}}


def test_refusal_that_is_not_json_fails_with_the_text(monkeypatch, capsys):
    post = Recorder(Response(502, '<html>Bad Gateway</html>'))

    msg = run_module_failing(monkeypatch, capsys, 'present', '1.0.14', post=post)
    assert msg == {'status': 502, 'response': '<html>Bad Gateway</html>'}


def test_refused_lookup_after_a_conflict_fails_without_updating(monkeypatch, capsys):
    post = Recorder(Response(409, {'message': 'already installed'}))
    get = Recorder(Response(404, {'message': 'Not found'}))

    msg = run_module_failing(monkeypatch, capsys, 'present', '1.0.15', post=post, get=get)
    assert msg == {'status': 404, 'response': 'Not found'}
    assert len(post.headers) == 1, 'an update was attempted after the lookup was refused'


def test_refused_update_fails_with_its_status(monkeypatch, capsys):
    post = Recorder(Response(409, {'message': 'already installed'}), Response(400, {'message': 'invalid version'}))
    get = Recorder(Response(200, PLUGIN))

    msg = run_module_failing(monkeypatch, capsys, 'present', '1.0.15', post=post, get=get)
    assert msg == {'status': 400, 'response': 'invalid version'}


def test_update_accepted_with_another_success_status_succeeds(monkeypatch):
    # The two status checks this module gained accept any 2xx: before them,
    # the lookup and the update were taken as success whatever their status,
    # and nothing has shown the update answers 200 rather than 202.
    post = Recorder(Response(409, {'message': 'already installed'}), Response(202, PLUGIN))
    get = Recorder(Response(200, dict(PLUGIN, version='1.0.14')))

    assert run_module(monkeypatch, 'present', '1.0.15', post=post, get=get) == 0


def test_latest_with_the_newest_installed_is_unchanged(monkeypatch, capsys):
    post = Recorder(Response(409, {'message': 'already installed'}))
    get = Recorder(Response(200, dict(PLUGIN, version='1.0.15', latestVersion='1.0.15')))

    result = run_module_succeeding(monkeypatch, capsys, 'present', 'latest', post=post, get=get)
    assert result['changed'] is False
    assert len(post.headers) == 1, 'an update was sent for a plugin already at its newest version'
    assert_authenticated(get, 1)


def test_latest_with_an_older_version_installed_updates(monkeypatch, capsys):
    post = Recorder(Response(409, {'message': 'already installed'}), Response(200, PLUGIN))
    get = Recorder(Response(200, dict(PLUGIN, version='1.0.14', latestVersion='1.0.15')))

    result = run_module_succeeding(monkeypatch, capsys, 'present', 'latest', post=post, get=get)
    assert result['changed'] is True
    assert len(post.headers) == 2
    assert_authenticated(get, 1)


def test_concrete_version_already_installed_is_unchanged(monkeypatch, capsys):
    post = Recorder(Response(409, {'message': 'already installed'}))
    get = Recorder(Response(200, PLUGIN))

    result = run_module_succeeding(monkeypatch, capsys, 'present', '1.0.14', post=post, get=get)
    assert result['changed'] is False
    assert len(post.headers) == 1
    assert_authenticated(get, 1)


def test_latest_without_a_reported_newest_version_updates(monkeypatch, capsys):
    # What this covers is the decision: with no latestVersion to compare, an
    # update is sent. The update response is the fixture's full record, because
    # what a successful update returns is unverified (#144), and main() reads
    # its success fields from it either way.
    installed = dict(PLUGIN)
    del installed['latestVersion']
    post = Recorder(Response(409, {'message': 'already installed'}), Response(200, PLUGIN))
    get = Recorder(Response(200, installed))

    result = run_module_succeeding(monkeypatch, capsys, 'present', 'latest', post=post, get=get)
    assert result['changed'] is True
    assert len(post.headers) == 2
    assert_authenticated(get, 1)
