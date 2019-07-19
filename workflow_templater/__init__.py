#!/usr/bin/env python3

import sys
import ruamel.yaml
import os
import argparse
import logging
import json
from io import StringIO
from shlex import quote
from functools import partial
if __name__ == '__main__':
    # preserve ability to launch this script (__main__.py) directly
    from urlopen_jira import urlopen_jira, get_password
    from our_jinja import OurJinjaEnvironment, OurJinjaLoader
else:
    from .urlopen_jira import urlopen_jira, get_password
    from .our_jinja import OurJinjaEnvironment, OurJinjaLoader
from jinja2 import StrictUndefined, DebugUndefined
import datetime
import smtplib
from email.mime.text import MIMEText
from appdirs import user_config_dir


yaml = ruamel.yaml.YAML(typ='safe')

COMMON_VARS_FILES = (
    '0_common.yaml',
    '00_common.yaml',
    'common.yaml',
)


def jinja_render_recursive(env, what, vars, path):
    if type(what) == list:
        newlist = []  # not using map here because we need index for error message
        for i, item in enumerate(what):
            newlist.append(jinja_render_recursive(env, item, vars, path + ['[{}]'.format(i)]))
        return newlist
    elif type(what) == dict:
        return dict(map(lambda items: (items[0], jinja_render_recursive(env, items[1], vars, path + [items[0]]),), what.items()))
    elif type(what) == str:
        try:
            return env.from_string(what).render(vars)
        except Exception as e:
            logging.critical('Template error in {path}: {err}. Exiting...'.format(
                path='/'.join(path),
                err=repr(e),
            ))
            sys.exit(1)
    else:
        return what


def pretty_dump(obj):
    yaml = ruamel.yaml.YAML(typ='rt')
    yaml.indent(mapping=2, sequence=2, offset=0)
    yaml.width = 99999
    def make_good_strings(obj):
        if type(obj) == list:
            return list(map(make_good_strings, obj))
        elif type(obj) == dict:
            return dict(map(lambda items: (items[0], make_good_strings(items[1]),), obj.items()))
        elif type(obj) == str:
            if obj.count('\n') > 0:
                return ruamel.yaml.scalarstring.LiteralScalarString(
                    '\n'.join(map(lambda x: x.rstrip(), obj.splitlines()))
                )
            else:
                return obj
        else:
            return obj

    with StringIO() as strio:
        yaml.dump(make_good_strings(obj), stream=strio)
        return strio.getvalue()

class Issue:
    def __init__(self, name, common_vars, additional_vars, data, fromfile, id=None, is_dryrun=False):
        self.name = name
        self.fromfile = fromfile
        self.common_vars = common_vars
        self.additional_vars = additional_vars # TODO: remove them? Don't forget about foreach_key and shit
        self.data = data
        self.is_dryrun = is_dryrun

    @property
    def final_vars(self):
        return dict(**self.common_vars, **self.additional_vars)

    @property
    def id(self):
        return self._id

    @id.setter
    def id(self, id):
        self._id = id
        self.common_vars[f'issuekey_{ self.name }'] = id

    def update(self):
        raise NotImplementedError()


class JiraIssue(Issue):
    def __init__(self, name, common_vars, additional_vars, data, fromfile, id=None, is_dryrun=False, jira=None):
        super().__init__(name, common_vars, additional_vars, data, fromfile, id, is_dryrun)
        self.jira = jira
        self.update_fields = self.data.pop('update', None)
        self.watchers = self.data.pop('watchers', ())

        if id is None:
            fields = jinja_render_recursive(jinja_env_permissive, self.data, self.final_vars, [self.fromfile])
            if self.is_dryrun:
                self.id = f'FAKE_JIRA_KEY-{ name }'
                logging.debug(pretty_dump(fields))
            else:
                # create issue
                logging.debug('creating issue for %s', name)
                result, _ = urlopen_jira_wrap('rest/api/2/issue/', 'POST', {
                    'fields': fields,
                })
                self.id = result['key']
                logging.info('created issue for %s, key: %s', name, self.id)
        else:
            self.id = id

    def update(self):
        fields = jinja_render_recursive(jinja_env_strict, self.data, self.final_vars, [self.fromfile])
        update = jinja_render_recursive(jinja_env_strict, self.update_fields, self.final_vars, [self.fromfile])
        if self.is_dryrun:
            pass
            logging.debug('-----{}-----'.format(self.id))
            logging.debug(pretty_dump(fields))
            if update:
                logging.debug(pretty_dump(update))
            logging.debug(pretty_dump({'watchers': self.watchers}))
        else:
            urlopen_jira_wrap(f'rest/api/2/issue/{self.id}', 'PUT', {
                'fields': fields,
                'update': update,
            })
            for watcher in self.watchers:
                urlopen_jira_wrap(f'rest/api/2/issue/{self.id}/watchers', 'POST', watcher)



class EmailIssue(Issue):
    def __init__(self, name, common_vars, additional_vars, data, fromfile, id=None, is_dryrun=False, smtp=None, user=None, keyring_service=None, email_from=None):
        super().__init__(name, common_vars, additional_vars, data, fromfile, id, is_dryrun)
        self.smtp = smtp
        self.user = user
        self.email_from = email_from
        self.keyring_service = keyring_service
        self.id = jinja_render_recursive(jinja_env_permissive, self.data, self.final_vars, [self.fromfile])['Message-ID']

    def update(self):

        rendered = jinja_render_recursive(jinja_env_strict, self.data, self.final_vars, [self.fromfile])
        self.id = rendered['Message-ID']
        if self.is_dryrun:
            logging.debug('Email: {}'.format(pretty_dump(rendered)))
        else:
            msg = MIMEText(rendered.pop('Body'))
            msg['From'] = self.email_from
            msg['To'] = ', '.join(rendered.pop('To'))
            for h, v in rendered.items():
                if v:
                    msg[h] = v

            with smtplib.SMTP(self.smtp.split(':')[0], int(self.smtp.split(':')[1])) as s:
                s.starttls()
                # TODO: handle bad password here
                logging.debug(s.login(self.user, get_password(self.keyring_service, self.user)))
                s.send_message(msg)

ISSUE_TYPES = {
    '.jira.yaml': JiraIssue,
    '.email.yaml': EmailIssue,
}


def main():
    parser = argparse.ArgumentParser(description='Jira issue maker')
    parser.add_argument('--dry-run', action='store_true', help='do not post anything to jira, do not send emails, just render templates')
    parser.add_argument('--no-dry-run', action='store_false', dest='dry_run', help='disable dry-run if it was enabled in config file')
    parser.add_argument('-v', '--verbose', action='store_true', help='be verbose')
    parser.add_argument('--update', type=str, help='do not create issues in jira, update existing instead')
    parser.add_argument('--jira', type=str, help='jira API url, ex. https://jira.example.com')
    parser.add_argument('--jira-user', type=str)
    parser.add_argument('--jira-keyring-service-name', type=str, default=None)
    parser.add_argument('--email-smtp', type=str, help='SMTP server host:port')
    parser.add_argument('--email-user', type=str)
    parser.add_argument('--email-keyring-service-name', type=str, default=None)
    parser.add_argument('--email-from', type=str)
    default_config_path = os.path.join(user_config_dir('workflow-templater', roaming=True), 'config.yaml')
    parser.add_argument('--config', type=str, default=default_config_path, help='overwrite config file path, default is {}'.format(default_config_path))
    parser.add_argument('template_dir', type=str, help='path to dir with templates')
    args = parser.parse_args()
    if args.config:
        try:
            with open(os.path.expanduser(args.config), 'r', encoding='utf8') as f:
                for k, v in yaml.load(f).items():
                    parser.set_defaults(**{k: v})
                args = parser.parse_args()  # re-parse args with new defaults from config
        except FileNotFoundError:
            if args.config != default_config_path:
                raise

    prev_iteration = None
    while True:
        # render jinja until nothing changes
        args_result = jinja_render_recursive(
            OurJinjaEnvironment(undefined=DebugUndefined),
            prev_iteration if prev_iteration else vars(args),
            prev_iteration if prev_iteration else vars(args),
            ['config&args:']
        )
        if args_result == prev_iteration:
            break
        prev_iteration = args_result
    # do it one more time but crash if something left unexpanded
    args_result = jinja_render_recursive(
        OurJinjaEnvironment(undefined=StrictUndefined),
        args_result,
        args_result,
        ['config&args:']
    )
    for k, v in args_result.items():
        setattr(args, k, v)

    if args.jira_keyring_service_name is None:
        args.jira_keyring_service_name = args.jira
    if args.email_keyring_service_name is None:
        args.email_keyring_service_name = args.email_smtp

    global urlopen_jira_wrap  # get rid of it?
    urlopen_jira_wrap = partial(urlopen_jira, user=args.jira_user, jira_base=args.jira, keyring_service=args.jira_keyring_service_name)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format='%(levelname)s %(message)s'
    )
    def excepthook(exc_type, exc_value, exc_traceback):
        logging.error("Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback,))

    sys.excepthook = excepthook

    common_vars = {}
    for common_vars_file in COMMON_VARS_FILES:
        try:
            with open(os.path.join(args.template_dir, common_vars_file), 'r', encoding='utf8') as f:
                common_vars = yaml.load(f)
        except FileNotFoundError:
            pass

    update = {}
    if args.update:
        update = json.loads(args.update)
        common_vars['updating'] = datetime.datetime.timestamp(datetime.datetime.utcnow())

    global jinja_env_permissive
    global jinja_env_strict
    jinja_env_permissive = OurJinjaEnvironment(
        loader=OurJinjaLoader(args.template_dir),
        undefined=DebugUndefined,
    )
    jinja_env_strict = OurJinjaEnvironment(
        loader=OurJinjaLoader(args.template_dir),
        undefined=StrictUndefined,
    )

    issues = []
    for filename in sorted(os.listdir(args.template_dir)):
        for issue_type_ext, IssueType in ISSUE_TYPES.items():
            if filename.endswith(issue_type_ext):
                if IssueType == JiraIssue:
                    type_specific_params = { 'jira': args.jira }
                elif IssueType == EmailIssue:
                    type_specific_params = { 'smtp': args.email_smtp, 'user': args.email_user, 'email_from': args.email_from, 'keyring_service': args.email_keyring_service_name }
                with open(os.path.join(args.template_dir, filename), 'r', encoding='utf8') as f:
                    data = yaml.load(f)

                    if_jinja = data.pop('if', None)

                    foreach = data.pop('foreach', (None,))
                    foreach_fromvar = data.pop('foreach_fromvar', None)
                    if foreach_fromvar is not None:
                        foreach = common_vars[foreach_fromvar]  # should crash if not exists
                    foreach_key = data.pop('foreach_key', 'item')
                    foreach_namevar = data.pop('foreach_namevar', None)
                    for item in foreach:
                        if item is not None and foreach_namevar is None and type(item) != str:
                            logging.critical("{}: Items in foreach are not strings, if it's a dict, you should use 'foreach_namevar' variable".format(filename))
                            sys.exit(1)
                        name = '_'.join(
                            filter(
                                None,
                                (
                                    filename.replace(issue_type_ext, ''),
                                    item if foreach_namevar is None else item[foreach_namevar],
                                )
                            )
                        )  # hard to read?
                        additional_vars = {} if item is None else {foreach_key: item}
                        if if_jinja is not None:
                            computed = jinja_render_recursive(jinja_env_strict, if_jinja, dict(**common_vars, **additional_vars), [filename, 'if'])
                            if computed.lower() in ('false', 'no', ''):
                                continue

                        issues.append(
                            IssueType(
                                name=name,
                                common_vars=common_vars,
                                additional_vars=additional_vars,
                                data=data.copy(),
                                id=update[name] if name in update else None,
                                is_dryrun=args.dry_run,
                                fromfile=filename,
                                **type_specific_params,
                            )
                        )

    future_update_arg = json.dumps(dict(map(lambda issue: (issue.name, issue.id), issues)))
    update_issues_cmd_parts = sys.argv.copy()
    if args.update:
        for i, arg in enumerate(update_issues_cmd_parts):
            if arg == '--update':
                update_issues_cmd_parts[i + 1] = future_update_arg
                break
    else:
        update_issues_cmd_parts.insert(1, '--update')
        update_issues_cmd_parts.insert(2, future_update_arg)
    update_issues_cmd = ' '.join(map(quote, update_issues_cmd_parts))
    common_vars['update_issues_cmd'] = update_issues_cmd

    for issue in issues:
        issue.update()

    print('\nTo update existing issues, edit templates/vars, then execute:\n')
    print(update_issues_cmd)


if __name__ == '__main__':
    main()
