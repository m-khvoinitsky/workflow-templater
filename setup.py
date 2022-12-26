#!/usr/bin/env python3
from setuptools import setup, find_packages
import os

with open('requirements.txt') as f:
    requirements = f.read().splitlines()

with open('README.md', 'r') as f:
    long_description = f.read()

setup(
    name="workflow_templater",
    version=os.environ.get('GITHUB_REF_NAME', '0.0'),
    packages=find_packages(),
    install_requires=requirements,
    zip_safe=True,
    entry_points={
        'console_scripts': [
            'workflow-templater = workflow_templater:main',
        ],
        'setuptools.installation': [
            'eggsecutable = workflow_templater:main',
        ]
    },
    author="Mikhail Khvoinitsky",
    author_email="me@khvoinitsky.org",
    description="Template engine for (currently) Jira and Email. Uses yaml and jinja2. It helps you create multiple (possibly cross-linked) jira issues and emails from a template.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url='https://github.com/m-khvoinitsky/workflow-templater',
    keywords="jira email template workflow release",
    classifiers=[
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3 :: Only',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Development Status :: 5 - Production/Stable',
        'Environment :: Console',
        'Intended Audience :: Information Technology',
        'Topic :: Office/Business :: Scheduling',
    ],
)
