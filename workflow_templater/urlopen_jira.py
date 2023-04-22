'''
Simple wrapper over urllib.request which handles jira authentication
and saves credentials (password and cookies) in your OS secret storage.
Depends on https://pypi.org/project/keyring/

Recommended usage pattern:

    from functools import partial

    urlopen_jira_wrap = partial(urlopen_jira, user=your_user_var, jira_base=your_jira_base_var, keyring_service=your_service_name_var)

    result, _ = urlopen_jira_wrap('rest/api/2/issue/', 'POST', {
        'fields': { ... },
    })
    jira_issue_key = result['key']

'''
import re
import keyring
import logging
import json
from getpass import getpass
from urllib.request import urlopen, Request
from urllib.parse import urljoin
from urllib.error import HTTPError
try:
    from .common import pretty_dump
except ImportError:
    # preserve ability to launch __main__.py directly
    from common import pretty_dump


def get_password(service_name, user, overwrite=False):
    password = keyring.get_password(service_name, user)
    if password is None or overwrite:
        password = getpass(prompt='Password for {}: '.format(service_name))
        keyring.set_password(service_name, user, password)
        logging.info('saved for future runs')
    return password


def get_cookie(password_service, user, jira_base, overwrite=False):
    cookies_service = '{}_{}_cookies'.format('workflow-templater', re.sub(r'[^a-z0-9]+', '_', jira_base).strip('_'))
    cookies = keyring.get_password(cookies_service, user)
    if cookies is None or overwrite:
        wrong_password = False
        for _ in range(3):
            try:
                cookie_parts = []
                data, res_obj = urlopen_jira(
                    'rest/auth/1/session',
                    jira_base=jira_base,
                    method='POST',
                    data={
                        'username': user,
                        'password': get_password(password_service, user, overwrite=wrong_password),
                    },
                )
                logging.debug(data)
                for k, v in res_obj.headers.items():
                    if isinstance(k, str) and k.lower() == 'set-cookie':
                        cookie_parts.append(v.split(';')[0])
                cookies = '; '.join(cookie_parts)
                keyring.set_password(cookies_service, user, cookies)
                break
            except HTTPError as e:
                if e.code == 401:
                    wrong_password = True
                    logging.warning('Wrong password')
                    continue
    if cookies is None:
        raise Exception('Unable to get session from jira')
    return cookies


def urlopen_jira(url, method='GET', data=None, user=None, keyring_service=None, jira_base=None, access_token=None):
    if jira_base is None:
        raise Exception('jira_base is required')
    final_url = urljoin(jira_base, url)
    debugdata = data
    try:
        debugdata = data.copy()
        if 'password' in debugdata:
            debugdata['password'] = '*' * len(debugdata['password'])
    except TypeError:
        pass
    except AttributeError:
        pass
    logging.debug('%s %s %s %s', final_url, user, method, debugdata)

    bad_cookies = False
    for _ in range(3):
        try:
            headers = {
                'Content-Type': 'application/json',
            }
            if access_token is not None:
                if jira_base.endswith('atlassian.net'):
                    headers["Authorization"] = f"Basic {access_token}"
                else:
                    headers["Authorization"] = f"Bearer {access_token}"
            elif user is not None:
                headers['Cookie'] = get_cookie(keyring_service, user, jira_base=jira_base, overwrite=bad_cookies)

            res_obj = urlopen(
                Request(
                    final_url,
                    data=json.dumps(data).encode() if data is not None else None,
                    headers=headers,
                    method=method
                ),
                timeout=120
            )
        except HTTPError as e:
            if e.code == 401 and user is not None:
                bad_cookies = True
                logging.info('Expired cookies, refreshing...')
                continue
            error_data = e.read()
            try:
                error_data_parsed = json.loads(error_data)
                logging.error('during %s to %s: %s %s\n%s', method, final_url, e.code, e.reason, pretty_dump(error_data_parsed))
            except json.JSONDecodeError:
                logging.error('during %s to %s: %s %s %s', method, final_url, e.code, e.reason, error_data)
            raise e
        if res_obj.code == 204:  # No Content
            return None, res_obj
        else:
            result = json.load(res_obj)  # json.loads(res_obj.read().decode('utf-8'))
            logging.debug(pretty_dump(result))
            return result, res_obj

        raise Exception('This code should have never been reached')
    raise Exception('Something went wrong')
