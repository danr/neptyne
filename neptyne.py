import jupyter_client as jc
import hashlib
import re
import inspect
import json
import codecs

from pprint import pprint
from itertools import zip_longest
from contextlib import contextmanager
from subprocess import Popen, PIPE

# def kernel_name(filename):
#     if filename.endswith('.jl'):
#         return 'julia-1.1'
#     elif filename.endswith('.lua'):
#         return 'lua'
#     else:
#         return 'python'

def unindent(s):
    lines = s.split('\n')
    d = min(len(l) - len(l.lstrip()) for l in lines if l)
    return '\n'.join(l[d:] for l in lines)

unindent("  apan")

test_cases = [("""
    x = 2

    x += 1
    x*x

    x+5
    """, ['9', '8']), ("""
    x = 2

    x += 1 # new irrelevant comment
    x*x

    x+4
    """, ['7']),
    ("""
    x = 2

    x += 1
    x*x

    x+3
    """, ['6']), ("""
    x = 2

    x -= 1
    x*x

    x+3
    """, ['4', '5']), ("""
    x = 1

    x -= 1
    x*x
    """, ['0']),
    (("complete", "x."), [['bit_length', 'conjugate', 'denominator', 'from_bytes', 'imag', 'numerator', 'real', 'to_bytes']]),
    ("""
    def y(a):
        '''hehehe'''
        a+=1

        a+=1
        return a

    y(1)
    """, ['3']),
    (("inspect", "y"), ['68d36b']),
    ("print(1)", ['1\n']),
    ("?print", ['e23cc7']),
    ("import sys; print(1, file=sys.stderr)", ['1\n']),
    ("!echo 1", ['1\r\n']),
    ("!echo 1;sleep .05;echo 1", ['1\r\n', '1\r\n']),
    ("""
    u = !echo 1
    u.l
    """, ["['1']"]),
    ("%notebook export.ipynb", []),
    ("pritn(1)", ["name 'pritn' is not defined"]),
    ("print(x)", ["0\n"]),
]

def span(p, xs):
    xs = iter(xs)
    l, r = [], []
    for x in xs:
        if p(*x):
            l.append(x)
        else:
            r.append(x)
            r += list(xs)
            break
    return l, r

def trim(s):
    if s:
        return re.sub('\s*\n', '\n', re.sub('\#.*', '', s.strip()))
    return s

class dotdict(dict):
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__

def dbg(part):
    def dbg_(line):
        if line.strip().startswith('##'):
            words = line.split()[1:]
            words = ', '.join(f"'{word}': {word}" for word in words)
            words = '{' + words + '}'
            line = line.replace('##', f'dbg({words}) #')
        return line
    return '\n'.join(map(dbg_, part.split('\n')))

@contextmanager
def kernel(kernel_name='python'):
    with jc.run_kernel(kernel_name=kernel_name, stdin=False) as kc:
        # print('got kernel')
        def wait_idle():
            while True:
                try:
                    msg = kc.get_iopub_msg()
                except KeyboardInterrupt:
                    kc.parent.interrupt_kernel()
                    yield 'interrupted'
                    continue
                msg = msg['content']
                # pprint(msg)
                if msg.get('execution_state', None) == 'idle':
                    break
                else:
                    yield msg

        prevs = []

        def complete(i, offset, handler):
            msg_id = kc.complete(i, offset)
            data = kc.get_shell_msg()['content']
            # pprint(data)
            matches = data['matches']
            yield matches
            list(wait_idle())

        def inspect(i, offset, handler):
            msg_id = kc.inspect(i, offset)
            data = kc.get_shell_msg()['content']
            data = data.get('data', {})
            text = data.get('text/plain')
            if text:
                yield text
            else:
                yield str(data)
            list(wait_idle())

        def process_part(part, handler, **metadata):
            handler.executing(part, **metadata)
            msg_id = kc.execute(part)
            cancel = False
            for msg in wait_idle():
                if 'data' in msg:
                    handler.data(msg['data'], **metadata)
                elif msg == 'interrupted':
                    cancel = True
                elif 'ename' in msg:
                    cancel = handler.error(**msg, **metadata) #ename, evalue, traceback
                elif msg.get('name') in ['stdout', 'stderr']:
                    handler.stream(msg['text'], msg['name'], **metadata)
            msg = kc.get_shell_msg(timeout=1)
            msg = msg['content']
            for payload in msg.get('payload', []):
                if 'data' in payload:
                    # ?print
                    data = payload['data']['text/plain']
                    handler.immediate(data, **metadata)
            return cancel

        def process(i, handler):
            nonlocal prevs
            # prevs = []
            parts = [ dbg(p) for p in re.split(r'(\n\n(?=\S))', i) ]
            zipped = list(zip_longest(parts, prevs))
            same, zipped = span(lambda part, prev: trim(prev) == trim(part), zipped)
            prevs = [ part for part, prev in same ]
            # print('same:', len(same))
            for part, prev in zipped:
                if part:
                    lines = lambda s: len(re.findall(r'\n', s))
                    line = sum(lines(p) for p in prevs) + lines(part.rstrip())
                    cancel = process_part(part, handler, line=line) if trim(part) else False
                    if cancel:
                        break
                    else:
                        prevs.append(part)

        yield dotdict(locals())

class Handler():
    def executing(_, part, **metadata):
        print(metadata, '\n>>>', '\n... '.join(shorter(part.strip().split('\n'))))

    def error(_, ename, evalue, traceback, **kws):
        print('\n'.join(traceback)) or True

    def stream(_, text, stream, **metadata):
        print(metadata, text, end='')

    def data(_, mimes, **metadata):
        # pprint(mimes)
        # png and html can be sent here inline
        png = mimes.get('image/png')
        svgxml = mimes.get('image/svg+xml')
        if png or svgxml:
            import libsixel
            from libsixel.encoder import Encoder
            import base64
            name = '/tmp/img.png'
            if svgxml:
                tmp = '/tmp/img.xml'
                with open(tmp, 'w') as f:
                    f.write(svgxml)
                Popen(["convert", tmp, name]).wait()
            else:
                with open(name, 'wb') as f:
                    f.write(base64.b64decode(png))
            enc = Encoder()
            # enc.setopt(e.SIXEL_OPTFLAG_WIDTH, "400")
            # enc.setopt(e.SIXEL_OPTFLAG_QUALITY, "low")
            enc.setopt(libsixel.SIXEL_OPTFLAG_COLORS, "256")
            if msg.get('metamimes', {}).get('needs_background') == 'light':
                enc.setopt(libsixel.SIXEL_OPTFLAG_BGCOLOR, "#fff")
            enc.encode(name)
            return
        print(metadata, mimes.get('text/plain').strip('\n'))

    def immediate(_, text, **metadata):
        print(metadata, text.strip())

def completion_esc(msg):
    return msg.replace('\\', '\\\\').replace('|', '\\|')
def qq(msg):
    return msg.replace('"', '""').replace('%', '%%')
def unansi(msg):
    ansi_escape = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')
    return ansi_escape.sub('', msg)

def shorter(xs):
    if len(xs) > 3:
        return [xs[0], '[...]', xs[-1]]
    else:
        return xs

std_handler = Handler()

def test():
    with kernel() as k:
        class TestHandler(Handler):
            def executing(_, part, **metadata):
                # print('>>>', part)
                pass

            def error(_, ename, evalue, traceback, **metadata):
                o_hat.append(evalue)

            def stream(_, text, stream, **metadata):
                o_hat.append(text)

            def data(_, mimes, **metadata):
                o_hat.append(mimes.get('text/plain'))

            def complete(_, ms):
                o_hat.append(ms)

            def md5(_, text, **metadata):
                o_hat.append(hashlib.md5(text.encode()).hexdigest()[:6])

            inspect = immediate = md5

            def __getitem__(self, item):
                return getattr(self, item)

        test_handler = TestHandler()

        for i, o in test_cases:
            o_hat = []
            if isinstance(i, str):
                i = unindent(i)
                k.process(i, test_handler)
            else:
                cmd, s = i
                for res in k[cmd](s, len(s), test_handler):
                    test_handler[cmd](res)
            if o != o_hat:
                print('BAD', o, o_hat)
            else:
                print('ok:', o_hat)

        return
        print('\n-------------\n')
        for i, _o in test_cases:
            if isinstance(i, str):
                k.process(i, std_handler)
            else:
                cmd, s = i
                for msg in k[cmd](s, len(s), std_handler):
                    print(msg)

def filter_completions(xs):
    normal = any(not x.name.startswith('_') for x in xs)
    if normal:
        return [x for x in xs if not x.name.startswith('_')]
    else:
        return xs

def info(s):
    return 'info -style menu "' + qq(s) + '"'

def handle_request(kernel, body, cmd, pos, client, session, *args):

    pos = int(pos)

    def send(msg):
        msg = 'eval -client {} "{}"'.format(client, qq(msg))
        p = Popen(['kak', '-p', str(session).rstrip()], stdin=PIPE)
        p.stdin.write(msg.encode())
        p.stdin.flush()
        p.stdin.close()
        p.wait()

    def completions(matches, args):
        line, column = map(int, args[:2])
        _, _, neptyne_completions, timestamp = args
        matches = filter_completions(list(map(dotdict, matches)))
        if not matches:
            return
        qqc = lambda m: qq(completion_esc(m))
        msg = ['"' + qqc(m.name) + '|' + qqc(m.doccmd or info(m.docstring)) + '|' + qqc(m.name) + '"' for m in matches]
        m0 = matches[0]
        dist = len(m0.name) - len(m0.complete)
        cmd = ['set window', neptyne_completions, str(line) + '.' + str(column - dist) + '@' + timestamp]
        msg = ' '.join(cmd + msg)
        send(msg)


    def complete():
        for reply in kernel.complete(body, pos, std_handler):
            matches = [
                dict(name=m, complete=m, doccmd='neptyne_inspect menu')
                for m in reply
            ]
            completions(matches, args)

    def process(timestamp):
        send(f'''
            try %[ decl line-specs neptyne_flags ]
            try %[ addhl window/ flag-lines default neptyne_flags ]
            set window neptyne_flags {timestamp}
            set window ui_options
        ''')

        def codepoint(line):
            return chr(ord('\ue000') + line)

        state = dotdict(seq_id = 0)
        def encoded_send(**data):
            pprint(data)
            state.seq_id += 1
            json_obj = json.dumps({**data, **state}).encode()
            b64_str = codecs.encode(json_obj, 'base64').decode()
            b64_str = b64_str.replace('\n', '').replace('=', '\\=')
            send(f'set -add window ui_options neptyne_{state.seq_id}={b64_str}')

        class ProcessHandler():
            def executing(_, part, line):
                # print('\n>>>', '\n... '.join(shorter(part.strip().split('\n'))))
                send('set -add window neptyne_flags ' + str(2+line) + '|' + codepoint(line))
                encoded_send(command='executing', args=[part], line=line, codepoint=codepoint(line))

            def __getattr__(_, command):
                return lambda *args, line, **kws: encoded_send(
                        command=command,
                        args=args,
                        line=line,
                        codepoint=codepoint(line),
                        **kws)

        print('processing')
        kernel.process(body, ProcessHandler())

    def inspect():
        for text in kernel.inspect(body, pos, std_handler):
            print('\n' + text)
            where, *args = args
            width, height = map(int, args)
            msg = unansi(text)
            msg = [line[:width-8] for line in msg.split('\n')]
            msg = '\n'.join(msg[:height-8])
            style = '-style menu' if where == 'menu' else ''
            msg = f'info {style} "{qq(msg)}"'
            send(msg)

    def jedi_icomplete(line, column):
        # We run the jedi command inside the kernel
        def _doit(*args, **kws):
            import jedi
            import json
            i = jedi.Interpreter(*args, **kws)
            cs = i.completions()
            d = [dict(name=c.name, complete=c.complete, docstring=c.docstring()) for c in cs]
            print(json.dumps(d))

        def on_reply(s, *_):
            try:
                matches = json.loads(s)
            except:
                return
            completions(matches, args)

        doit_s = inspect.getsource(_doit)
        h = dotdict()
        h.stream = on_reply
        h.text = lambda *_: None
        h.immediate = lambda *_: None
        h.executing = lambda *_: None

        # zap lines above current blob (to preserve line number)
        lines = []
        ok = True
        for l in body.split('\n')[:line][::-1]:
            if not l:
                ok = False
            if ok:
                lines.append(l)
            else:
                lines.append('')
        body = '\n'.join(lines[::-1])

        kernel.process_part(f'{doit_s}\n_doit({body!r}, namespaces=[locals(), globals()], line={line}, column={column-1})', h)

    def jedi(subcmd, *args):
        import jedi
        line, column = map(int, args)
        try:
            script = jedi.Script(body, line, column - 1) # , watched_file)
        except:
            print('jedi failed')
            return
        if subcmd == 'icomplete':
            jedi_icomplete(line, column)
        if subcmd == 'complete':
            matches = [
                dict(name=m.name, complete=m.complete, docstring=m.docstring())
                for m in script.completions()
            ]
            completions(matches, args)
        elif subcmd == 'docstring':
            try:
                print(script.goto_definitions()[0].docstring())
            except:
                print('nothing')
                pass
        elif subcmd == 'usages':
            pprint(script.usages())
        elif subcmd == 'sig':
            pprint(script.call_signatures())
        elif subcmd == 'goto':
            pprint(script.goto_definitions())
        else:
            print('Invalid jedi command: ', subcmd)

    if '_' in cmd:
        head, subcmd = cmd.split('_')
        locals()[head](subcmd, *args)
    else:
        locals()[cmd](*args)

import os
if __name__ == '__main__' and 'MPLBACKEND' not in os.environ:
    import sys
    if sys.argv[1:2] == ['test']:
        test()
    else:
        from inotify.adapters import Inotify
        i = Inotify()
        i.add_watch('.')
        watched_files = sys.argv[1:]
        # watched_file = (sys.argv + [None])[1]
        # import os
        # common = os.path.commonpath([os.getcwd(), watched_file])
        # watched_file = watched_file[1+len(common):]
        # print(common, watched_file)
        with kernel() as k:
            for f in watched_files:
                try:
                    k.process(open(f, 'r').read(), std_handler)
                except FileNotFoundError:
                    pass
            for event in i.event_gen(yield_nones=False):
                (_, event_type, _, filename) = event
                # print(event_type, filename)

                if event_type == ['IN_CLOSE_WRITE'] and filename in watched_files:
                    k.process(open(filename, 'r').read(), std_handler)

                if event_type == ['IN_CLOSE_WRITE'] and filename == '.requests':
                    try:
                        request, body = open(filename, 'r').read().split('\n', 1)
                        handle_request(k, body, *request.split(' '))
                    except ValueError:
                        print('Invalid request:', str(open(filename, 'r').read()))
                        continue


