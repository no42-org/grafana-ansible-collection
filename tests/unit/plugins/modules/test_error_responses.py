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


def run(monkeypatch, capsys, name, args, responses):
    """Run a module and return its exit code and result.

    An exception escaping main() is not caught here, so a module that raises
    fails the test with its own traceback.
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
    return exit_info.value.code, json.loads(capsys.readouterr().out)


def run_failing(monkeypatch, capsys, name, args, responses):
    """Run a module, require it to fail cleanly, and return its result."""
    code, result = run(monkeypatch, capsys, name, args, responses)
    assert code == 1
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
    pattern = re.compile(r"json\(\)\s*(\[|\.get\()\s*['\"]message['\"]")
    offenders = []
    for path in paths:
        with open(path) as module_file:
            if pattern.search(module_file.read()):
                offenders.append(os.path.basename(path))
    assert offenders == [], "use module_utils.responses instead of reading json()'s message in: %s" % ', '.join(offenders)


class NotJson(object):
    """A refusal whose body is not JSON, as a proxy's HTML error page is not."""

    def __init__(self, status_code, text):
        self.status_code = status_code
        self.text = text

    def json(self):
        raise ValueError('Expecting value: line 1 column 1 (char 0)')


def test_cloud_stack_refused_listing_fails_with_the_status(monkeypatch, capsys):
    # After "That URL has already been taken", cloud_stack lists the org's
    # stacks. The listing was parsed before its status was checked.
    taken = Response(409, {'message': 'That URL has already been taken, please try an alternate URL'})
    result = run_failing(monkeypatch, capsys, 'cloud_stack',
                         dict(name='s', stack_slug='s', cloud_api_key='key', org_slug='org'),
                         {'post': [taken], 'get': [NotJson(502, '<html>Bad Gateway</html>')]})
    assert result['msg'] == {'status': 502, 'response': '<html>Bad Gateway</html>'}


def test_datasource_conflict_that_is_not_json_is_resolved_by_listing(monkeypatch, capsys):
    # The 409 branch read the conflict text with result.json().get(), which
    # raised on a body that is not JSON before the listing was even asked.
    result = run_failing(monkeypatch, capsys, 'datasource',
                         dict(GRAFANA, dataSource={'name': 'ds', 'type': 'prometheus'}),
                         {'post': [NotJson(409, '<html>Conflict</html>')], 'get': [REFUSED]})
    assert result['msg']['status'] == 400


def test_user_refused_password_change_fails_with_the_status(monkeypatch, capsys):
    result = run_failing(monkeypatch, capsys, 'user',
                         dict(admin_name='admin', admin_password='pw', login='u', password='new',
                              grafana_url='http://grafana.test', state='update_password'),
                         # The new password does not log in yet (401), then the admin
                         # lookup finds the user, and the password change is refused.
                         {'get': [Response(401, {'message': 'invalid username or password'}),
                                  Response(200, {'id': 7, 'login': 'u'})],
                          'put': [REFUSED]})
    assert result['msg'] == {'status': 400, 'response': REFUSAL_BODY}


# --------------------------------------------------- #159 refused lookups
# Each lookup below read its body before checking its status. The fakes
# answer only the requests listed, so a delete, PUT or update the module
# should not send fails the test as "unexpected".

FORBIDDEN_BODY = {'message': 'Forbidden'}
CONTACT_POINT = dict(GRAFANA, name='cp', uid='cp', type='email', settings={'addresses': 'a@example.org'})
FOLDER = dict(GRAFANA, title='f', uid='f')
USER = dict(admin_name='admin', admin_password='pw', login='u', grafana_url='http://grafana.test')

LOOKUP_CASES = [
    ('alert_contact_point-present', 'alert_contact_point', CONTACT_POINT,
     {'post': [Response(409, {'message': 'conflict'})], 'get': [Response(403, FORBIDDEN_BODY)]}),
    ('alert_contact_point-absent', 'alert_contact_point', dict(CONTACT_POINT, state='absent'),
     {'get': [Response(403, FORBIDDEN_BODY)]}),
    ('folder-present', 'folder', FOLDER,
     {'post': [Response(412, {'message': 'exists'})], 'get': [Response(403, FORBIDDEN_BODY)]}),
    ('folder-absent', 'folder', dict(FOLDER, state='absent'),
     {'get': [Response(403, FORBIDDEN_BODY)]}),
    ('user-present', 'user', USER,
     {'get': [Response(403, FORBIDDEN_BODY)]}),
    ('user-absent', 'user', dict(USER, state='absent'),
     {'get': [Response(403, FORBIDDEN_BODY)]}),
]


@pytest.mark.parametrize('name, args, responses', [c[1:] for c in LOOKUP_CASES], ids=[c[0] for c in LOOKUP_CASES])
def test_refused_lookup_fails_with_its_status(monkeypatch, capsys, name, args, responses):
    result = run_failing(monkeypatch, capsys, name, args, responses)
    assert result['msg'] == {'status': 403, 'response': 'Forbidden'}


def test_refused_policy_read_fails_without_writing(monkeypatch, capsys):
    # A 403 body has no 'routes', which the module took to mean "no policy
    # yet" and answered with a PUT.
    result = run_failing(monkeypatch, capsys, 'alert_notification_policy', dict(GRAFANA, routes=[]),
                         {'get': [Response(403, FORBIDDEN_BODY)]})
    assert result['msg'] == 'Status code is 403'
    assert result['output'] == 'Forbidden'


def test_lookup_that_is_not_json_fails_with_the_text(monkeypatch, capsys):
    result = run_failing(monkeypatch, capsys, 'folder', dict(FOLDER, state='absent'),
                         {'get': [NotJson(502, '<html>Bad Gateway</html>')]})
    assert result['msg'] == {'status': 502, 'response': '<html>Bad Gateway</html>'}


def test_refused_read_back_after_an_accepted_update_reports_the_change(monkeypatch, capsys):
    # The PUT was accepted, so the change happened. A refused read-back must
    # not turn that into a failure; the module reports the body it sent.
    code, result = run(monkeypatch, capsys, 'alert_contact_point', CONTACT_POINT,
                       {'post': [Response(409, {'message': 'conflict'})],
                        'get': [Response(200, []), Response(403, FORBIDDEN_BODY)],
                        'put': [Response(202, {})]})
    assert code == 0
    assert result['changed'] is True
    # The request body the module sent, which spells the key UID.
    assert result['output']['UID'] == 'cp'


def test_password_change_proceeds_when_the_new_password_is_refused(monkeypatch, capsys):
    # The first lookup logs in with the new password. A 401 there is the
    # answer "not changed yet", not a failure.
    code, result = run(monkeypatch, capsys, 'user',
                       dict(USER, password='new', state='update_password'),
                       {'get': [Response(401, {'message': 'invalid username or password'}),
                                Response(200, {'id': 7, 'login': 'u'})],
                        'put': [Response(200, {'message': 'User password updated'})]})
    assert code == 0
    assert result['changed'] is True


def test_password_change_fails_when_the_admin_lookup_is_refused(monkeypatch, capsys):
    result = run_failing(monkeypatch, capsys, 'user', dict(USER, password='new', state='update_password'),
                         {'get': [Response(401, {'message': 'invalid username or password'}),
                                  Response(403, FORBIDDEN_BODY)]})
    assert result['msg'] == {'status': 403, 'response': 'Forbidden'}


# A 200 whose JSON is not the kind of data the lookup asked for, as a gateway
# answering every path with a login dict produces. Found in code review.
SHAPE_CASES = [
    ('alert_contact_point-absent', 'alert_contact_point', dict(CONTACT_POINT, state='absent'),
     {'get': [Response(200, {'message': 'login required'})]}),
    ('folder-absent', 'folder', dict(FOLDER, state='absent'),
     {'get': [Response(200, {'message': 'login required'})]}),
    ('user-present', 'user', USER,
     {'get': [Response(200, {})]}),
]


@pytest.mark.parametrize('name, args, responses', [c[1:] for c in SHAPE_CASES], ids=[c[0] for c in SHAPE_CASES])
def test_lookup_of_the_wrong_shape_fails_with_its_status(monkeypatch, capsys, name, args, responses):
    result = run_failing(monkeypatch, capsys, name, args, responses)
    assert result['msg']['status'] == 200


def test_policy_read_of_the_wrong_shape_fails_without_writing(monkeypatch, capsys):
    result = run_failing(monkeypatch, capsys, 'alert_notification_policy', dict(GRAFANA, routes=[]),
                         {'get': [Response(200, ['not', 'a', 'policy'])]})
    assert result['msg'] == 'Status code is 200'


def test_password_change_fails_when_the_new_password_probe_errors(monkeypatch, capsys):
    # Only an authentication refusal means "not changed yet".
    result = run_failing(monkeypatch, capsys, 'user', dict(USER, password='new', state='update_password'),
                         {'get': [Response(500, {'message': 'internal error'})]})
    assert result['msg'] == {'status': 500, 'response': 'internal error'}
