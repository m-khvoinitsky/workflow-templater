import re
# https://blogs.msdn.microsoft.com/twistylittlepassagesallalike/2011/04/23/everyone-quotes-command-line-arguments-the-wrong-way/
# Warning: this is not a complete solution! Do not use it for arbitrary uncontrolled data

def argv_quote(s):
    # https://docs.microsoft.com/en-us/previous-versions//17w5ykft(v=vs.85)
    s = re.sub(r'\\+(?=")', lambda mo: mo.group() * 2, s)
    s = s.replace('"', r'\"')
    if ' ' in s or '\t' in s:
        s = re.sub(r'\\+$', lambda mo: mo.group() * 2, s)
        s = '"{}"'.format(s)
    return s


def escape_ps(args):
    return '--% {}'.format(' '.join(map(argv_quote, args)))

def escape_cmd(s):
    return re.sub(r'\(|\)|\%|\!|\^|\"|\<|\>|\&|\|', lambda mo: f'^{mo.group()}', argv_quote(s))
