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
    - [Using eggsecutable](#using-eggsecutable)
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
1. Install python ≥ 3.7.
    * Using official Python installer:
        1. Install python ≥ 3.7 from <https://python.org/> ("macOS 64-bit installer")
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
1. Make sure that python ≥ 3.7 is installed
2.
    ```sh
    pip3 install workflow-templater
    ```
### Using eggsecutable
1. Download workflow_templater-${version}-py3.x.egg from the latest release on [Releases page](https://github.com/m-khvoinitsky/workflow-templater/releases).
2. You can execute it directly or with `/bin/sh` (if you have compatible python and dependencies installed):
    ```sh
    ./workflow_templater-${version}-py3.x.egg --help
    sh ./workflow_templater-${version}-py3.x.egg --help
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
* There should be one file with variables named `0_common.yaml`, `00_common.yaml` or `common.yaml`.
* There may be any amount of "issue" files: ending with ".jira.yaml" for jira issue and ending with ".email.yaml" for email.
* Each "issue" file is yaml file where each string value is rendered with [Jinja2](http://jinja.pocoo.org/docs/templates/) using variables from `*common.yaml` file.

## Examples
See [basic release example](https://github.com/m-khvoinitsky/workflow-templater/tree/master/examples/basic_release_example) for basic example.
