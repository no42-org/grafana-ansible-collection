# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Ronny Trommer <ronny@no42.org>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import json

import pytest

from ansible_collections.grafana.grafana.plugins.module_utils.responses import accepted, failure, message


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


@pytest.mark.parametrize('body, expected_message, expected_response', [
    ({'message': 'Forbidden'}, 'Forbidden', 'Forbidden'),
    ({'error': 'invalid token'}, None, {'error': 'invalid token'}),
    ([{'message': 'in a list'}], None, [{'message': 'in a list'}]),
    ('<html>Bad Gateway</html>', None, '<html>Bad Gateway</html>'),
], ids=['message', 'json-without-message', 'json-list', 'not-json'])
def test_message_and_failure(body, expected_message, expected_response):
    result = Response(418, body)

    assert message(result) == expected_message
    assert failure(result) == {'status': 418, 'response': expected_response}


@pytest.mark.parametrize('status, body, ok, expected', [
    (200, [{'uid': 'a'}], (200,), ([{'uid': 'a'}], None)),
    (202, {'id': 1}, (200, 202), ({'id': 1}, None)),
    (403, {'message': 'Forbidden'}, (200,), (None, {'status': 403, 'response': 'Forbidden'})),
    (200, '<html>not json</html>', (200,), (None, {'status': 200, 'response': '<html>not json</html>'})),
], ids=['accepted', 'accepted-by-ok', 'refused', 'accepted-but-not-json'])
def test_accepted(status, body, ok, expected):
    assert accepted(Response(status, body), ok=ok) == expected


def test_accepted_rejects_the_wrong_kind_of_json():
    assert accepted(Response(200, {'message': 'login required'}), kind=list) == (
        None, {'status': 200, 'response': 'login required'})
    assert accepted(Response(200, [1]), kind=list) == ([1], None)
