'''
Changes over regular jinja2:
* support for arbitrary relative imports, example:
    {% include '../common/cluster_update.j2' %}
* implemented filters
  * quote: escape string for POSIX shell
* implemented tests:
  * contains: checks if iterable contains an element;
    similar to built-in "in" but works vice-versa
'''
import os
from shlex import quote
from jinja2 import FileSystemLoader, Environment, TemplateNotFound


class OurJinjaLoader(FileSystemLoader):
    def get_source(self, environment, template):
        for searchpath in self.searchpath:
            filename = os.path.join(searchpath, template)
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    contents = f.read()
            except FileNotFoundError:
                continue

            mtime = os.path.getmtime(filename)

            def uptodate():
                try:
                    return os.path.getmtime(filename) == mtime
                except OSError:
                    return False
            return contents, filename, uptodate
        raise TemplateNotFound(template)


class OurJinjaEnvironment(Environment):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.filters['quote'] = quote
        self.tests['contains'] = lambda where, what: what in where

    def join_path(self, template, parent):
        return os.path.join(os.path.dirname(parent), template)
