# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Ronny Trommer <ronny@no42.org>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

"""How a plugin module reads a response that Grafana or Grafana Cloud refused.

A refusal's body is not guaranteed to be a JSON object with a `message`. It can
be one without that key, a JSON list, or not JSON at all, such as a proxy's
HTML 502. Indexing result.json()['message'] raised on every one of those and
lost the HTTP status the user needed (#143, #153).
"""

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


def message(result):
    """The response body's `message`, or None when it has none."""
    try:
        body = result.json()
    except ValueError:
        return None
    if isinstance(body, dict):
        return body.get('message')
    return None


def failure(result):
    """A refusal as {"status": <code>, "response": <detail>}.

    The detail is the body's `message` when the body is a JSON object that has
    one, otherwise the JSON body, otherwise the body text. A refusal that
    carries a message is reported exactly as the modules always reported it.
    """
    try:
        body = result.json()
    except ValueError:
        return {'status': result.status_code, 'response': result.text}
    if isinstance(body, dict) and 'message' in body:
        return {'status': result.status_code, 'response': body['message']}
    return {'status': result.status_code, 'response': body}


def accepted(result, ok=(200,), kind=None):
    """(body, None) for an accepted response, (None, failure(result)) otherwise.

    For a lookup, whose body the caller is about to read as the data it asked
    for: a refusal's body is not that data (#159). An accepted status whose
    body is not JSON, or not the `kind` of JSON the caller expects (a list of
    folders, say, where a gateway answered 200 with a dict), is reported too,
    since the caller cannot use it.
    """
    if result.status_code not in ok:
        return None, failure(result)
    try:
        body = result.json()
    except ValueError:
        return None, failure(result)
    if kind is not None and not isinstance(body, kind):
        return None, failure(result)
    return body, None
