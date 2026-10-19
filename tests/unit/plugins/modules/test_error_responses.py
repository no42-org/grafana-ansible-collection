# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Ronny Trommer <ronny@no42.org>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Every plugin module fails a refused request with its HTTP status (#153).

One case per module drives main() to a failure branch with a refusal whose
JSON body has no `message`. Before #153 each of these branches indexed
result.json()['message'] and escaped main() as KeyError.
"""

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import contextlib
import glob
import importlib
import json
import os
import re

import pytest

from ansible.module_utils import basic
from ansible.module_utils.common.text.converters import to_bytes

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


class Response(object):
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body
        self.text = json.dumps(body)

    def json(self):
        return self._body


class Requests(object):
    """Answers each requests function from its own queue of responses."""

    def __init__(self, responses):
        self.responses = dict((method, list(queue)) for method, queue in responses.items())

    def fake(self, method):
        def call(url, **kwargs):
            queue = self.responses.get(method)
            assert queue, 'unexpected %s %s' % (method.upper(), url)
            return queue.pop(0)
        return call


REFUSAL_BODY = {'error': 'refused'}
REFUSED = Response(400, REFUSAL_BODY)
GRAFANA = {'grafana_url': 'http://grafana.test', 'grafana_api_key': 'key'}

# (module, arguments, responses): the shortest route each module offers to a
# failure branch that read the refusal's message.
CASES = [
    ('alert_contact_point',
     dict(GRAFANA, name='cp', uid='cp', type='email', settings={'addresses': 'a@example.org'}),
     {'post': [REFUSED]}),
    ('alert_notification_policy',
     dict(GRAFANA, routes=[]),
     {'get': [Response(200, {})], 'put': [REFUSED]}),
    ('cloud_api_key',
     dict(name='k', role='Admin', org_slug='org', existing_cloud_api_key='key'),
     {'post': [REFUSED]}),
    ('cloud_plugin',
     dict(name='grafana-github-datasource', stack_slug='stack', cloud_api_key='key'),
     {'post': [REFUSED]}),
    ('cloud_stack',
     dict(name='s', stack_slug='s', cloud_api_key='key', org_slug='org'),
     {'post': [REFUSED]}),
    ('dashboard',
     dict(GRAFANA, dashboard={'dashboard': {'title': 't'}}),
     {'post': [REFUSED]}),
    ('datasource',
     dict(GRAFANA, dataSource={'name': 'ds', 'type': 'prometheus'}),
     {'post': [REFUSED]}),
    ('folder',
     dict(GRAFANA, title='f', uid='f'),
     {'post': [REFUSED]}),
    ('user',
     dict(admin_name='admin', admin_password='pw', login='u', grafana_url='http://grafana.test'),
     {'get': [Response(404, {'message': 'user not found'})], 'post': [REFUSED]}),
]


def run_failing(monkeypatch, capsys, name, args, responses):
    """Run a module, require it to fail cleanly, and return its result.

    An exception escaping main() is not caught here, so a module that raises
    on the refusal fails the test with its own traceback.
    """
    module = importlib.import_module('ansible_collections.grafana.grafana.plugins.modules.' + name)
    requests = Requests(responses)
    for method in ('get', 'post', 'put', 'delete', 'patch'):
        monkeypatch.setattr(module.requests, method, requests.fake(method))
    args = dict(args, _ansible_remote_tmp='/tmp', _ansible_keep_remote_files=False)
    capsys.readouterr()
    with patch_module_args(args):
        with pytest.raises(SystemExit) as exit_info:
            module.main()
    assert exit_info.value.code == 1
    result = json.loads(capsys.readouterr().out)
    assert result['failed'] is True
    return result


@pytest.mark.parametrize('name, args, responses', CASES, ids=[case[0] for case in CASES])
def test_refusal_without_a_message_fails_with_the_status(monkeypatch, capsys, name, args, responses):
    result = run_failing(monkeypatch, capsys, name, args, responses)
    if name == 'alert_notification_policy':
        # This module has always reported the status in msg and the response
        # body under output; that interface is kept.
        assert result['msg'] == 'Status code is 400'
        assert result['output'] == REFUSAL_BODY
    else:
        assert result['msg'] == {'status': 400, 'response': REFUSAL_BODY}


def test_cloud_stack_conflict_without_a_message_fails_with_the_status(monkeypatch, capsys):
    # cloud_stack chooses a branch by the message text of a 409 or 403. A
    # message that is missing must match no branch, not raise.
    result = run_failing(monkeypatch, capsys, 'cloud_stack',
                         dict(name='s', stack_slug='s', cloud_api_key='key', org_slug='org'),
                         {'post': [Response(409, REFUSAL_BODY)]})
    assert result['msg'] == {'status': 409, 'response': REFUSAL_BODY}


def test_no_module_indexes_the_message_of_a_response():
    # The defect is a textual pattern, so the guard is textual: the next copy
    # of it is caught here even in a branch no case above reaches.
    modules = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'plugins', 'modules', '*.py')
    paths = sorted(glob.glob(modules))
    assert paths, 'found no modules at %s' % modules
    pattern = re.compile(r"json\(\)\[\s*['\"]message['\"]\s*\]")
    offenders = [os.path.basename(p) for p in paths if pattern.search(open(p).read())]
    assert offenders == [], "use module_utils.responses instead of json()['message'] in: %s" % ', '.join(offenders)
