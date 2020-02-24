import ruamel.yaml
from io import StringIO

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
