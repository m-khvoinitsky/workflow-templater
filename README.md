# Intro
Template engine for (currently) Jira and Email. Uses yaml and jinja2. It helps you create multiple (possibly cross-linked) jira issues and emails from a template.

# Table of Contents
<!-- generated with `md_toc -p README.md github` -->
<!--TOC-->

- [Intro](#intro)
- [Table of Contents](#table-of-contents)
- [Installation](#installation)
  - [Windows](#windows)
  - [macOS](#macos)
  - [Anything else (GNU/Linux, Cygwin, *nix, etc)](#anything-else-gnulinux-cygwin-nix-etc)
    - [Using pip](#using-pip)
    - [Using pipx](#using-pipx)
    - [From source](#from-source)
- [Usage](#usage)
- [Configuration](#configuration)
- [Template description](#template-description)
  - [Overview](#overview)
  - [Examples](#examples)

<!--TOC-->

# Installation

## Windows
1. Download Workflow_Templater_${version}.exe from the latest release on [Releases page](https://github.com/m-khvoinitsky/workflow-templater/releases).
2. Install it.
3. Now `workflow-templater` executable should be available from Windows Command Prompt (`cmd.exe`) and from Powershell.
4. (Optional, recommended) Install [Windows Terminal](https://github.com/Microsoft/Terminal) and use it instead of default console.

## macOS
1. Install python ≥ 3.10.
    * Using official Python installer:
        1. Install python ≥ 3.10 from <https://python.org/> ("macOS 64-bit installer")
        2. Install CA certificates for python, execute in Terminal:
            ```
            /Applications/Python\ 3.7/Install\ Certificates.command
            ```
            Alternatively, you can double-click on `Install Certificates.command` in Finder
    * Or using [Homebrew](https://brew.sh/):
        ```sh
        brew install python
        ```
2.  ```sh
    pip3 install workflow-templater
    ```
## Anything else (GNU/Linux, Cygwin, *nix, etc)
### Using pip
1. Make sure that python ≥ 3.10 is installed
2.
    ```sh
    pip3 install workflow-templater
    ```
### Using pipx
1.
    ```sh
    pipx run workflow-templater
    ```
### From source
1. Clone this repo
2. Install dependencies if required
    ```sh
    pip3 install -r requirements.txt
    ```
3. You can execute the script directly:
    ```
    cd workflow_templater
    ./workflow_templater/__init__.py --help
    ```
    Or install/build/whatever it with
    ```
    python3 setup.py
    ```

# Usage
See
```sh
workflow-templater --help
```
# Configuration
To avoid typing same command line arguments each time, it is possible to specify them in configuration file. Configuration file location is OS-specific, to find out correct location for your os, execute `workflow-templater --help`, you'll see message "--config CONFIG  overwrite config file path, default is ${location}" where ${location} is the location of configuration file on your OS. You can create this file and specify values of command-line arguments omitting `--` and replacing `-` with `_`, for example, `--jira-user j_wayne` becomes `jira_user: j_wayne`, `--dry-run` becomes `dry_run: true` and so on. You can also use jinja2 in configuration file which evaluates using variables from itself.

Example `~/.config/workflow-templater/config.yaml`:
```yaml
dry_run: true
verbose: true
user: j_wayne
jira: https://jira.example.com/
jira_user: '{{ user }}'
email_user: '{{ user }}'
email_from: '{{ user }}@example.com'
email_smtp: 'smtp.example.com:587'
# avoid typing in the same password for jira and email
jira_keyring_service_name: 'MyCorp LDAP'
email_keyring_service_name: 'MyCorp LDAP'

```

# Template description
## Overview
* Whole workflow template is a directory.
* There should be one file with variables named `0_common.yaml`, `00_common.yaml` or `common.yaml`. Alternatively, you can name this file as you wish and specify its name with `--vars` argument.
* There may be any amount of "issue" files:
    * ending with ".jira.yaml" for jira issue
        * All fields in each jira.issue file are send as is to Jira via [API](https://docs.atlassian.com/software/jira/docs/api/REST/latest/#api/2/issue-createIssue) in `fields` fileld with the exception of following fields:
            * `watchers`: it's impossible to add watchers during create so it handled separately via [this API method](https://docs.atlassian.com/software/jira/docs/api/REST/latest/#api/2/issue-addWatcher).
            * `update`: its content is sent in `update` via [API](https://docs.atlassian.com/software/jira/docs/api/REST/latest/#api/2/issue-createIssue)
            * global special fields (see below)
    * ending with ".email.yaml" for email.
* There may be optional file named `mutate.py` with function `mutate` which accepts variables, modifies them and returns the result wich can be used in templates.

  Basic example:
  ```python
  def mutate(variables):
      variables['new_variable'] = f'{variables["old_var1"]} and {variables["old_var2"]}'
      return variables
  ```

  Security note: if you concerned that this feature introduces an ability to execute arbitrary code from the templates, that's correct. However, this is also possible with bare jinja templates (see [https://github.com/pallets/jinja/issues/549](https://github.com/pallets/jinja/issues/549)), so you should make sure that your templates come from trusted sources anyway.

* Each "issue" file is yaml file where each string value is rendered with [Jinja2](http://jinja.pocoo.org/docs/templates/) using variables from `*common.yaml` file.
* Special variables available for use in jinja:
    * `issuekey_self`: Jira issue key or Message-ID of current issue or email.
    * `issuekey_<name>`: Jira issue key or Message-ID of issue or email named `<name>`. For example, for issue in filename `something.jira.yaml` this variable name would be `issuekey_something` and it can be used in all templates.
* Global special fields:
    * `foreach`: list, create one issue per item in this list. List items should be strings or dicts (in case of dicts you must specify `foreach_namevar` too, see below). In case of strings, issuekey_ variable would be named `issuekey_<name>_<list_value>`
    Example:
        ```yaml
        foreach:
        - Android
        - iOS
        summary: 'Release application for {{ item }}'
        ...
        ```
        would finally evaluate to following issues:
        ```yaml
        summary: 'Release application for Android'
        ...
        ```
        ```yaml
        summary: 'Release application for iOS'
        ...
        ```
    * `foreach_fromvar`: if content for `foreach` variable is shared between several templates, it's better to specify it in `*common.yaml` file and specify here the name of the variable in this file. Example:
        `common.yaml`:
        ```yaml
        OSes:
        - Android
        - iOS
        ...
        ```
        `build.jira.yaml`:
        ```yaml
        foreach_fromvar: OSes
        summary: 'Build clients for {{ item }}'
        ...
        ```
        `release.jira.yaml`:
        ```yaml
        foreach_fromvar: OSes
        summary: 'Release application for {{ item }}'
        ...
        ```
    * `foreach_key`: if you don't like default variable name (`item`) for each item in `foreach` list, you may specify it here. Example
        ```yaml
        foreach:
        - Android
        - iOS
        foreach_key: os
        summary: 'Release application for {{ os }}'
        ...
        ```
        would finally evaluate to following issues:
        ```yaml
        summary: 'Release application for Android'
        ...
        ```
        ```yaml
        summary: 'Release application for iOS'
        ...
        ```
    * `foreach_namevar`: when foreach is in use, workflow-templater would generate issuekey_ variable name as follows: `issuekey_<name>_<list_value>`. If you use dicts as foreach values, you need to specify key name in this dicts which will be appended to the end of this variable name. Example
        `release.jira.yaml` file:
        ```yaml
        foreach:
        - name: Android
          date: !!timestamp 2019-10-24 06:30:00.0
        - name: iOS
          date: !!timestamp 2019-10-24 10:50:00.0
        foreach_namevar: name
        summary: 'Release application for {{ item.name }}'
        ...
        ```
        Now in any other (or the same) issue you can link to this issues as follows:
        ```yaml
        summary: 'Notify community'
        description: |
          Android release task: {{ issuekey_release_Android }}
          iOS release task: {{ issuekey_release_iOS }}
        ```
    * `if`: if this variable value evaluates to empty string (`''`), `false` or `no`, this template will be completely ignored. Note: value for this variable is calculated for each item separately when `foreach` or `foreach_fromvar` is in use.
    Example:
        ```yaml
        foreach:
        - Android
        - iOS
        foreach_key: os
        if: '{{ os in ["Android", "GNU/Linux"] }}'
        summary: 'Release application for {{ os }}'
        ...
        ```
        would finally evaluate to following issue (only one, obviously):
        ```yaml
        summary: 'Release application for Android'
        ...
        ```

## Examples
See [basic release example](https://github.com/m-khvoinitsky/workflow-templater/tree/master/examples/basic_release_example) for basic example.
