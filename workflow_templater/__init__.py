#!/usr/bin/env python3

import sys
import ruamel.yaml
import os
import argparse
import logging
import json
from shlex import quote
from functools import partial
from itertools import chain
if __name__ == '__main__':
    # preserve ability to launch this script (__main__.py) directly
    from urlopen_jira import urlopen_jira, get_password
    from our_jinja import OurJinjaEnvironment, OurJinjaLoader
    from quote_windows import escape_cmd, escape_ps
    from common import pretty_dump
else:
    from .urlopen_jira import urlopen_jira, get_password
    from .our_jinja import OurJinjaEnvironment, OurJinjaLoader
    from .quote_windows import escape_cmd, escape_ps
    from .common import pretty_dump
from jinja2 import StrictUndefined, DebugUndefined
import datetime
import smtplib
import importlib.util
from email.mime.text import MIMEText
from appdirs import user_config_dir


yaml = ruamel.yaml.YAML(typ='safe')

COMMON_VARS_FILES = (
    '0_common.yaml',
    '00_common.yaml',
    'common.yaml',
)

class Continue(Exception):
    pass

# This marker is used to exclude some fields from updating (for example, in case when it's needed
# to preserve human's changes). However, during issue creation, there will be an attempt to update
# them (to make sure that all required variables have been gathered). To avoid even the very first
# update, there is the following marker (with "force"). It is useful if, for example, you do not have
# permissions to update certain fields so you can only create an issue with them pre-filled.
NO_UPDATE_MARKER = '_workflow_templater_no_update'
FORCE_NO_UPDATE_MARKER = '_workflow_templater_force_no_update'
def jinja_render_recursive(env, what, vars, path, updating_while_creating=False, updating=False):
    if type(what) == list:
        newlist = []  # not using map here because we need index for error message
        for i, item in enumerate(what):
            try:
                result = jinja_render_recursive(env, item, vars, path + ['[{}]'.format(i)], updating_while_creating)
                try:
                    for marker, situation in (
                        (f'{NO_UPDATE_MARKER}:', updating_while_creating),
                        (f'{FORCE_NO_UPDATE_MARKER}:', updating),
                    ):
                        if result.startswith(marker):
                            if situation:
                                raise Continue()
                            result = result[len(marker):]
                except AttributeError:
                    pass
                newlist.append(result)
            except Continue:
                pass
        return newlist
    elif type(what) == dict:
        newdict = {}
        for k, v in what.items():
            try:
                new_value = jinja_render_recursive(env, v, vars, path + [k], updating_while_creating)
                try:
                    for marker, situation in (
                        (NO_UPDATE_MARKER, updating_while_creating),
                        (FORCE_NO_UPDATE_MARKER, updating),
                    ):
                        if k.endswith(marker):
                            if situation:
                                raise Continue()
                            k = k[:-len(marker)]
                except AttributeError:
                    pass
                newdict[k] = new_value
            except Continue:
                pass
        return newdict
    elif type(what) == str:
        try:
            result = env.from_string(what).render(vars)
            JSONMARKER = '_workflow_templater_parsejson:'
            if result.startswith(JSONMARKER):
                return json.loads(result[len(JSONMARKER):])
            else:
                return result
        except Exception as e:
            logging.critical('Template error in {path}: {err}.'.format(
                path='/'.join(path),
                err=repr(e),
            ))
            raise
    else:
        return what


ASKMARKER = '_workflow_templater_ask:'
def process_vars(v, label):
    if isinstance(v, str):
        if v.startswith(ASKMARKER):
            type_ = v.replace(ASKMARKER, '')
            if type_ == 'bool':
                v = input(f'{label} (y/yes/n/no)?: ').strip().lower() in ('y', 'yes',)
            elif type_ == 'str':
                v = input(f'{label} (enter value): ')
            else:
                raise Exception(f'unknown type for {ASKMARKER} {type_}')
            return v
        else:
            return v
    elif isinstance(v, list):
        newlist = []
        for index, item in enumerate(v):
            newlist.append(process_vars(item, f'{label}[{index}]'))
        return newlist
    elif isinstance(v, dict):
        return dict(map(lambda t: (t[0], process_vars(t[1], f'{label}.{t[0]}')), v.items()))
    else:
        return v


class Issue:
    def __init__(self, name, common_vars, additional_vars, data, fromfile, id=None, is_dryrun=False, no_update=False, updating=False):
        self.name = name
        self.fromfile = fromfile
        self.common_vars = common_vars
        self.additional_vars = additional_vars # TODO: remove them? Don't forget about foreach_key and shit
        self.data = data
        self.is_dryrun = is_dryrun
        self.no_update = no_update
        self.updating = updating
        self.self_key_dict = {}

    @property
    def final_vars(self):
        return dict(**self.common_vars, **self.additional_vars, **self.self_key_dict)

    @property
    def id(self):
        return self._id

    @id.setter
    def id(self, id):
        self._id = id
        self.common_vars[f'issuekey_{ self.name }'] = id
        self.self_key_dict['issuekey_self'] = id

    def update(self):
        raise NotImplementedError()


class JiraIssue(Issue):
    def __init__(self, name, common_vars, additional_vars, data, fromfile, id=None, is_dryrun=False, no_update=False, updating=False, jira=None):
        super().__init__(name, common_vars, additional_vars, data, fromfile, id, is_dryrun, no_update, updating)
        self.jira = jira
        self.update_fields = self.data.pop('update', None)
        self.watchers = self.data.pop('watchers', ())

        if id is None:
            fields = jinja_render_recursive(jinja_env_permissive, self.data, self.final_vars, [self.fromfile])
            if self.is_dryrun:
                self.id = f'FAKE_JIRA_KEY-{ name }'
                logging.info(pretty_dump(fields))
            else:
                # create issue
                logging.info('creating issue for %s', name)
                result, _ = urlopen_jira_wrap('rest/api/2/issue/', 'POST', {
                    'fields': fields,
                })
                self.id = result['key']
                logging.info('created issue for %s, key: %s', name, self.id)
        else:
            self.id = id

    def update(self):
        if self.no_update:
            return
        fields = jinja_render_recursive(jinja_env_strict, self.data, self.final_vars, [self.fromfile], self.updating, True)
        update = jinja_render_recursive(jinja_env_strict, self.update_fields, self.final_vars, [self.fromfile], self.updating, True)
        watchers = jinja_render_recursive(jinja_env_strict, self.watchers, self.final_vars, [self.fromfile], self.updating, True)
        if self.is_dryrun:
            pass
            logging.info('-----{}-----'.format(self.id))
            logging.info(pretty_dump(fields))
            if update:
                logging.info(pretty_dump(update))
            logging.info(pretty_dump({'watchers': watchers}))
        else:
            if type(update) != list:
                # some actions in jira, despite being a list, may contain only one item, for example "issuelinks"
                # that's why we need to be able to perform several update actions with different data
                update = [update]
            for i, u in enumerate(update):
                logging.info('updating issue %s (%s) %s', self.id, i + 1, self.name)
                urlopen_jira_wrap(f'rest/api/2/issue/{self.id}', 'PUT', {
                    'fields': fields,
                    'update': u,
                })
            for watcher in watchers:
                logging.info('adding watcher %s to %s %s', watcher, self.id, self.name)
                urlopen_jira_wrap(f'rest/api/2/issue/{self.id}/watchers', 'POST', watcher)


class EmailIssue(Issue):
    def __init__(self, name, common_vars, additional_vars, data, fromfile, id=None, is_dryrun=False, no_update=False, updating=False, smtp=None, user=None, keyring_service=None, email_from=None):
        super().__init__(name, common_vars, additional_vars, data, fromfile, id, is_dryrun, no_update, updating)
        self.smtp = smtp
        self.user = user
        self.email_from = email_from
        self.keyring_service = keyring_service
        self.id = jinja_render_recursive(jinja_env_permissive, self.data, self.final_vars, [self.fromfile])['Message-ID']

    def update(self):
        if self.no_update:
            return
        rendered = jinja_render_recursive(jinja_env_strict, self.data, self.final_vars, [self.fromfile], self.updating, True)
        self.id = rendered['Message-ID']
        if self.is_dryrun:
            logging.info('Email: {}'.format(pretty_dump(rendered)))
        else:
            logging.info('sending email from %s', self.name)
            if 'Body_html' in rendered:
                msg = MIMEText(rendered.pop('Body_html'), 'html')
            else:
                msg = MIMEText(rendered.pop('Body'), 'plain')
            msg['From'] = self.email_from
            for header in ('To', 'Cc', 'Bcc',):
                if header in rendered:
                    msg[header] = ', '.join(rendered.pop(header))

            for h, v in rendered.items():
                if v:
                    msg[h] = v

            with smtplib.SMTP(self.smtp.split(':')[0], int(self.smtp.split(':')[1])) as s:
                s.starttls()
                # TODO: handle bad password here
                logging.debug(s.login(self.user, get_password(self.keyring_service, self.user)))
                s.send_message(msg)
            logging.info('sent email from %s\nSubject: %s\nTo: %s\nMessage-Id: %s', self.name, msg['Subject'] if 'Subject' in msg else 'empty', msg['To'] if 'To' in msg else 'no one', msg['Message-Id'] if 'Message-Id' in msg else 'empty')

ISSUE_TYPES = {
    '.jira.yaml': JiraIssue,
    '.email.yaml': EmailIssue,
}

def prepare_future_update_cmd(issues, common_vars, updating):
    future_update_arg = json.dumps(dict(map(lambda issue: (issue.name, issue.id), issues)))
    update_issues_cmd_parts = sys.argv[1:].copy()
    if updating:
        for i, arg in enumerate(update_issues_cmd_parts):
            if arg == '--update':
                update_issues_cmd_parts[i + 1] = future_update_arg
                break
    else:
        update_issues_cmd_parts.insert(0, '--update')
        update_issues_cmd_parts.insert(1, future_update_arg)
    cmd_cmd = ' '.join(chain((os.path.basename(sys.argv[0]),), map(escape_cmd, update_issues_cmd_parts)))
    powershell_cmd = ' '.join((os.path.basename(sys.argv[0]), escape_ps(update_issues_cmd_parts),))
    unixshell_cmd = ' '.join(chain((sys.argv[0],), map(quote, update_issues_cmd_parts)))
    update_issues_cmd = '\n'.join((
        '', 'For cmd.exe:', cmd_cmd,
        '', 'For Powershell:', powershell_cmd,
        '', 'For UNIX Shell:', unixshell_cmd,
    ))
    common_vars['update_issues_cmd'] = update_issues_cmd
    # Warning: parent shell detection here is very unreliable, for example, it will fail inside cygwin
    if os.name == 'nt' and 'PROMPT' in os.environ:  # hacky way to detect cmd.exe
        return cmd_cmd
    elif os.name == 'nt':  # if we're not inside cmd.exe, let's assume that we're inside powershell
        return powershell_cmd
    elif os.name == 'posix':  # inside unix shell
        return unixshell_cmd
    else:
        return update_issues_cmd

def main():
    parser = argparse.ArgumentParser(description='Workflow Templater', formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('--dry-run', action='store_true', help='do not post anything to jira, do not send emails, just render templates')
    parser.add_argument('--no-dry-run', action='store_false', dest='dry_run', help='disable dry-run if it was enabled in config file')
    parser.add_argument('-v', '--verbose', action='store_true', help='be verbose')
    parser.add_argument('--vars', type=str, metavar='FILE', help='read variables from FILE instead of *common.yaml')
    parser.add_argument('--update', type=str, help='do not create issues in jira, update existing instead. Format: JSON like {"issue_file_1": "issuekey2", "issue_file_2": "issuekey2"}. You most likely don\'t need to write it youself (however, you can), instead, workflow-templater at the end will will print command to re-launch it with this argument. If you want, you can include this command in the template as "update_issues_cmd" variable.')
    parser.add_argument('--jira', type=str, help='jira API url, ex. https://jira.example.com')
    parser.add_argument('--jira-user', type=str)
    parser.add_argument('--jira-keyring-service-name', type=str, default=None)
    parser.add_argument('--email-smtp', type=str, help='SMTP server host:port')
    parser.add_argument('--email-user', type=str)
    parser.add_argument('--email-keyring-service-name', type=str, default=None)
    parser.add_argument('--email-from', type=str)
    default_config_path = os.path.join(user_config_dir('workflow-templater', roaming=True), 'config.yaml')
    parser.add_argument('--config', type=str, default=default_config_path, help='overwrite config file path, default is {}'.format(default_config_path))
    parser.add_argument('--print-config-path', action='store_true', help='print config file path and exit')
    parser.add_argument('--access-token', type=str, default=None)
    parser.add_argument('template_dir', type=str, help='path to dir with templates')
    args = parser.parse_args()
    if args.print_config_path:
        print(args.config)
        sys.exit(0)
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
    urlopen_jira_wrap = partial(urlopen_jira, user=args.jira_user, jira_base=args.jira,
                                keyring_service=args.jira_keyring_service_name, access_token=args.access_token)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(levelname)s %(message)s'
    )
    issues = []
    common_vars = {}
    def excepthook(exc_type, exc_value, exc_traceback):
        if args.verbose:
            logging.error("Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback,))
        else:
            logging.error("Unhandled exception {}: {}".format(exc_type.__name__, str(exc_value)))
        if issues:
            print('\nError happened, but some issues have already been created. To update existing issues, edit templates/vars, then execute:\n')
            print(prepare_future_update_cmd(issues, common_vars, args.update))
            print('\nFAIL')

    sys.excepthook = excepthook

    if args.vars:
        with open(os.path.join(args.template_dir, args.vars), 'r', encoding='utf8') as f:
            common_vars = yaml.load(f)
    else:
        for common_vars_file in COMMON_VARS_FILES:
            try:
                with open(os.path.join(args.template_dir, common_vars_file), 'r', encoding='utf8') as f:
                    common_vars = yaml.load(f)
            except FileNotFoundError:
                pass

    common_vars = process_vars(common_vars, 'common_vars')
    mutate_pyfile = os.path.join(args.template_dir, 'mutate.py')
    if os.path.isfile(mutate_pyfile):
        spec = importlib.util.spec_from_file_location("mutate_module", mutate_pyfile)
        mutate_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mutate_module)
        common_vars = mutate_module.mutate(common_vars)
    logging.debug((f'-- common_vars --\n\n{pretty_dump(common_vars)}'))

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
                    no_update = data.pop('no_update', False)
                    force_no_update = data.pop('force_no_update', False)

                    foreach = jinja_render_recursive(jinja_env_strict, data.pop('foreach', (None,)), common_vars, [filename, 'foreach'])
                    foreach_fromvar = data.pop('foreach_fromvar', None)
                    if foreach_fromvar is not None:
                        foreach = common_vars[foreach_fromvar]  # should crash if not exists
                    foreach_key = data.pop('foreach_key', 'item')
                    foreach_namevar = data.pop('foreach_namevar', None)
                    for i, item in enumerate(foreach):
                        name = '_'.join(
                            filter(
                                None,
                                (
                                    filename.replace(issue_type_ext, ''),
                                    (item if (type(item) == str or item is None) else str(i)) if foreach_namevar is None else item[foreach_namevar],
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
                                no_update=force_no_update if force_no_update else (no_update if name in update else False),
                                updating=name in update,
                                fromfile=filename,
                                **type_specific_params,
                            )
                        )

    future_cmd_short = prepare_future_update_cmd(issues, common_vars, args.update)

    for issue in issues:
        issue.update()

    print('\nTo update existing issues, edit templates/vars, then execute:\n')
    print(future_cmd_short)
    print('\nSUCCESS')


if __name__ == '__main__':
    main()
