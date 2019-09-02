import jupyter_client as jc
import hashlib
import re
import inspect
import json
import codecs
import time

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
    (("inspect", "y"), ['edd3b1']),
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

class dotdict(dict):
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__

def trim(s):
    if s:
        return re.sub('\s*\n', '\n', re.sub('\#.*', '', s.strip()))
    return s

def id_stream(prevs):
    id = max([0] + [prev.id or 0 for prev in prevs])
    def bump():
        nonlocal id
        id += 1
        return id
    return bump

def slices(s):
    return re.split(r'(?<=\S)(?=\n{2,}\S)', s)

def line_count(s):
    return len(re.findall(r'\n', s))

def calculate_queue(body, prevs):
    parts = slices(body)

    changed = False
    line_begin = -1
    next_id = id_stream(prevs)
    for prev, part in zip_longest(prevs, parts):
        if part is not None:
            line_end = line_begin + line_count(part.rstrip())
            me = dotdict(
                code = part,
                line_begin = line_begin + 1,
                line_end = line_end,
                id = next_id()
            )
            if changed or (not prev or trim(prev.code) != trim(part) or prev.status == 'cancelled'):
                changed = True
                me.status = 'scheduled'
                if prev and prev.msgs:
                    me.prev_msgs = prev.msgs
            else:
                me.status = 'done'
                if prev and prev.msgs:
                    me.msgs = prev.msgs
            yield me
            line_begin = line_end

def __dbg__unused__(part):
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
                if msg.get('execution_state', None) == 'idle':
                    break
                else:
                    yield msg

        def complete(i, offset):
            msg_id = kc.complete(i, offset)
            data = kc.get_shell_msg()['content']
            matches = data['matches']
            list(wait_idle())
            return matches

        def inspect(i, offset):
            msg_id = kc.inspect(i, offset)
            data = kc.get_shell_msg()['content']
            data = data.get('data', {})
            text = data.get('text/plain')
            list(wait_idle())
            return text if text else str(data)

        def process_part(part):
            msg_id = kc.execute(part)
            for msg in wait_idle():
                if 'data' in msg:
                    yield dotdict(type='data', data=msg['data'])
                elif msg == 'interrupted':
                    yield dotdict(type='cancel', data={})
                elif 'ename' in msg:
                    yield dotdict(type='error', data={'text/plain': '\n'.join(msg['traceback'])}, **msg)
                elif msg.get('name') in ['stdout', 'stderr']:
                    yield dotdict(type='stream', data={'text/plain': msg['text']}, stream=msg['name'])
                elif 'execution_state' in msg:
                    pass
                elif 'execution_count' in msg:
                    pass
                else:
                    print('unknown message: ', end='')
                    pprint(msg)
            msg = kc.get_shell_msg(timeout=1)
            msg = msg['content']
            for payload in msg.get('payload', []):
                if 'data' in payload:
                    # ?print
                    yield dotdict(type='data', data=payload['data'])
                else:
                    print('unknown message: ', end='')
                    pprint(msg)

        def process_queue(queue):
            # pprint(queue)
            done = []
            outdated = []
            for i, q in enumerate(queue):
                if q.status == 'done':
                    done.append(q)
                else:
                    outdated = queue[i:]
                    break
            next_id = id_stream(queue)
            state = lambda done, now=None, scheduled=[]: dotdict(done=done, now=now, scheduled=scheduled, all=done + ([now] if now else []) + scheduled)
            errored = False
            for i, now in enumerate(outdated):
                scheduled = outdated[i+1:]
                now = dotdict(now, id=next_id(), status='executing', msgs=[])
                yield state(done, now, scheduled)

                for msg in process_part(now.code):
                    now = dotdict(now, id=next_id(), msgs=[*now.msgs, msg])
                    yield state(done, now, scheduled)
                    if msg.type == 'error' or msg.type == 'cancel':
                        errored = True

                if errored:
                    cancelled = [dotdict(s, id=next_id(), status='cancelled', msgs=s.msgs or s.prev_msgs, prev_msgs=None) for s in [now, *scheduled]]
                    yield state([*done, *cancelled])
                    return

                now = dotdict(now, id=next_id(), status='done')
                if 'prev_msgs' in now:
                    del now['prev_msgs']
                done = [*done, now]

            yield state(done)

        prevs = []

        def process(body):
            nonlocal prevs
            queue = list(calculate_queue(body, prevs))
            for fwd in process_queue(queue):
                yield fwd
                prevs = fwd.done

        yield dotdict(locals())

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

def msg_to_stdout(msg):
    if msg.data:
        mimes = msg.data
        text = mimes['text/plain']
        print(text, end='' if msg.type == 'stream' else '\n')

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
            enc.setopt(libsixel.SIXEL_OPTFLAG_COLORS, "256")
            if msg.get('metamimes', {}).get('needs_background') == 'light':
                enc.setopt(libsixel.SIXEL_OPTFLAG_BGCOLOR, "#fff")
            enc.encode(name)


def processed_messages(states):
    for state in states:
        now = state.now
        if now and now.msgs:
            yield now.msgs[-1]

def processed_to_stdout(states):
    for state in states:
        now = state.now
        if now and not now.msgs:
            print('\n>>>', '\n... '.join(shorter(now.code.strip().split('\n'))))
        elif now and now.msgs:
            msg = now.msgs[-1]
            msg_to_stdout(msg)

def test():
    with kernel() as k:
        def md5(text):
            return hashlib.md5(text.encode()).hexdigest()[:6]

        for i, o in test_cases:
            o_hat = []
            if isinstance(i, str):
                i = unindent(i)
                for msg in processed_messages(k.process(i)):
                    if msg.type == 'error':
                        o_hat.append(msg.evalue)
                    else:
                        txt = msg.data['text/plain']
                        if 'Docstring' in txt:
                            o_hat.append(md5(txt))
                        else:
                            o_hat.append(txt)

            else:
                cmd, s = i
                res = k[cmd](s, len(s))
                if cmd == 'complete':
                    o_hat.append(res)
                else:
                    res = '\n'.join(l for l in res.split('\n') if 'File' not in l)
                    o_hat.append(md5(res))
            if o != o_hat:
                print('BAD', o, o_hat)
            else:
                print('ok:', o_hat)

        return
        print('\n-------------\n')
        for i, _o in test_cases:
            if isinstance(i, str):
                processed_to_stdout(k.process(unindent(i)))
            else:
                cmd, s = i
                res = k[cmd](s, len(s))
                print(res)

def filter_completions(xs):
    normal = any(not x.name.startswith('_') for x in xs)
    if normal:
        return [x for x in xs if not x.name.startswith('_')]
    else:
        return xs

def info(s):
    return 'info -style menu "' + qq(s) + '"'

class Pool():
    def __init__(self, keys):
        self.free = set(keys)
        self.map = dotdict()

    def pop(self, key):
        self.free.add(key)
        try:
            del self.map[key]
        except KeyError:
            pass

    def add(self, value):
        key = self.free.pop()
        self.map[key] = value
        return key

    def __getitem__(self, key):
        return self.map[key]

    def __setitem__(self, key, value):
        self.map[key] = value

PUAs = {chr(x) for x in range(0xe000, 0xf8ff)}

def handle_request(kernel, body, cmd, pos, client, session, *args, pua_pool=Pool(PUAs)):

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

    def process(timestamp, _timestamp_flag_lines, *prev_flag_lines):

        def b64_json(data):
            json_obj = json.dumps(data).encode()
            b64_str = codecs.encode(json_obj, 'base64').decode()
            return b64_str.replace('\n', '').replace('=', '\\=')

        offset = 3
        # ['12|\ue000', '14|\ue002']
        # {'12': '\ue000', '14': '\ue002'}
        prev_flag_lines = [x.split('|') for x in prev_flag_lines if '|' in x]
        prev_flag_lines = {int(k) - offset: v for k, v in prev_flag_lines}

        sent = set()
        first = True
        for state in kernel.process(body):
            msgs = []

            chars = {}

            if first:
                # assign a PUA char to each line, reusing if possible
                first = False
                flag_lines = {}
                for blob in state.all:
                    line = blob.line_end
                    if line in prev_flag_lines:
                        flag_lines[line] = prev_flag_lines[line]
                    else:
                        flag_lines[line] = pua_pool.add(line)

                spec = ' '.join(f'{l + offset}|{c}' for l, c in flag_lines.items())
                msgs.append(f'''
                    set window neptyne_flags {timestamp} {spec}
                    set window ui_options ncurses_assistant=none  # clear ui_options
                ''')

                for old_line, old_char in prev_flag_lines.items():
                    if old_line not in flag_lines:
                        pua_pool.pop(old_char)
                        # msgs.append(set_char(old_char, ''))

            if state.now:
                print(state.now.status, state.now.line_end)

            for blob in state.all:
                if blob.id not in sent:
                    print('sending', blob.line_end, blob.status, 'id=' + str(blob.id))
                    sent.add(blob.id)
                    chars[flag_lines[blob.line_end]] = blob
                    # here we could send simplified text msgs (remove ansi escapes and so on)

            ui_options = ' '.join(f'neptyne_{ord(char)}={b64_json(value)}' for char, value in chars.items())
            msgs.append(f'set -add window ui_options {ui_options}')
            send('\n'.join(msgs))

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

        # We run the jedi command inside the kernel
        def _jedi_complete(*args, **kws):
            import jedi
            import json
            i = jedi.Interpreter(*args, **kws)
            cs = i.completions()
            d = [dict(name=c.name, complete=c.complete, docstring=c.docstring()) for c in cs]
            print(json.dumps(d))

        jedi_complete_s = inspect.getsource(_jedi_complete)

        for msg in processed_messages(kernel.process_part(f'{jedi_complete_s}\n_jedi_complete({body!r}, namespaces=[locals(), globals()], line={line}, column={column-1})')):
            if msg.type == 'stream':
                s = msg.data['text/plain']
                try:
                    matches = json.loads(s)
                except:
                    return
                completions(matches, args)

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
if 'MPLBACKEND' in os.environ:
    test()
elif __name__ == '__main__':
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
                    processed_to_stdout(k.process(open(f, 'r').read()))
                except FileNotFoundError:
                    pass
            for event in i.event_gen(yield_nones=False):
                (_, event_type, _, filename) = event
                # print(event_type, filename)

                if event_type == ['IN_CLOSE_WRITE'] and filename in watched_files:
                    processed_to_stdout(k.process(open(filename, 'r').read()))

                if event_type == ['IN_CLOSE_WRITE'] and filename == '.requests':
                    try:
                        request, body = open(filename, 'r').read().split('\n', 1)
                        handle_request(k, body, *request.split(' '))
                    except ValueError as e:
                        print('Invalid request:', str(open(filename, 'r').read()).split('\n')[0])
                        import traceback
                        print(traceback.format_exc())
                        continue


