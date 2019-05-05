import jupyter_client as jc
import hashlib
import re

from pprint import pprint
from itertools import zip_longest
from contextlib import contextmanager
from subprocess import Popen, PIPE

io = [("""
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
("""u = !echo 1
u.l""", ["['1']"]),
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

@contextmanager
def kernel():
    with jc.run_kernel(stdin=False) as kc:
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

        prevs = []

        def complete(i, offset, self):
            msg_id = kc.complete(i, offset)
            data = kc.get_shell_msg()['content']
            matches = data['matches']
            yield matches
            list(wait_idle())

        def inspect(i, offset, self):
            msg_id = kc.inspect(i, offset)
            data = kc.get_shell_msg()['content']
            data = data['data']
            text = data.get('text/plain')
            if text:
                yield text
            else:
                yield str(data)
            list(wait_idle())

        def process(i, self):
            nonlocal prevs
            parts = re.split(r'\n\n(?=\S)', i)
            zipped = list(zip_longest(parts, prevs))
            same, zipped = span(lambda part, prev: trim(prev) == trim(part), zipped)
            prevs = list(map(lambda x: x[0], same))
            for part, prev in zipped:
                if part:
                    self.executing(part)
                    msg_id = kc.execute(part)
                    cancel = False
                    for msg in wait_idle():
                        if 'data' in msg:
                            # png and html can be sent here inline
                            # pprint(msg)
                            data = msg['data']
                            png = data.get('image/png')
                            if png:
                                import libsixel
                                from libsixel.encoder import Encoder
                                import base64
                                name = '/tmp/img.png'
                                with open(name, 'wb') as f:
                                    f.write(base64.b64decode(png))
                                enc = Encoder()
                                # enc.setopt(e.SIXEL_OPTFLAG_WIDTH, "400")
                                # enc.setopt(e.SIXEL_OPTFLAG_QUALITY, "low")
                                enc.setopt(libsixel.SIXEL_OPTFLAG_COLORS, "256")
                                if msg.get('metadata', {}).get('needs_background') == 'light':
                                    enc.setopt(libsixel.SIXEL_OPTFLAG_BGCOLOR, "#fff")
                                enc.encode(name)
                            else:
                                text = data['text/plain']
                                self.text(text)
                        elif msg == 'interrupted':
                            cancel = True
                        elif 'ename' in msg:
                            cancel = self.error(**msg) #ename, evalue, traceback
                        elif msg.get('name') in ['stdout', 'stderr']:
                            self.stream(msg['text'], msg['name'])
                    msg = kc.get_shell_msg(timeout=1)
                    msg = msg['content']
                    for payload in msg.get('payload', []):
                        if 'data' in payload:
                            # ?print
                            data = payload['data']['text/plain']
                            self.immediate(data)
                    if cancel:
                        break
                    else:
                        prevs.append(part)

        yield dotdict(process=process, inspect=inspect, complete=complete)

class Handler(dict):
    def __getattr__(self, k):
        v = self.get(k)
        if v is None:
            return lambda *args, **kws: self.default(k, *args, **kws)
        else:
            return v

    def __getitem__(self, k):
        return self.__getattr__(k)

    __setattr__ = dict.__setitem__

    def default(self, k, *args, **kws):
        pprint((k, args, kws))

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

std = Handler()
std.executing = lambda part: print('\n>>>', '\n... '.join(shorter(part.strip().split('\n'))))
std.error     = lambda ename, evalue, traceback: print('\n'.join(traceback)) or True
std.stream    = lambda text, stream: print(text, end='')
std.text      = lambda text: print(text.strip('\n'))
std.immediate = lambda text: print(text.strip())

def test():
    with kernel() as k:
        self = Handler()
        self.executing = lambda part: None # print('>>>', part)
        self.error = lambda ename, evalue, traceback: o_hat.append(evalue)
        self.stream = lambda text, stream: o_hat.append(text)
        self.text = lambda text: o_hat.append(text)
        md5 = lambda text: o_hat.append(hashlib.md5(text.encode()).hexdigest()[:6])
        self.immediate = md5
        self.inspect = md5
        self.complete = lambda ms: o_hat.append(ms)
        for i, o in io:
            o_hat = []
            if isinstance(i, str):
                k.process(i, self)
            else:
                cmd, s = i
                for res in k[cmd](s, len(s), self):
                    self[cmd](res)
            if o != o_hat:
                print('BAD', o, o_hat)
            else:
                print('ok:', o_hat)

        print('\n-------------\n')
        for i, _o in io:
            if isinstance(i, str):
                k.process(i, std)
            else:
                cmd, s = i
                for msg in k[cmd](s, len(s), std):
                    print(msg)

if __name__ == '__main__':
    import sys
    from inotify.adapters import Inotify
    if sys.argv[1:2] == ['test']:
        test()
    else:
        i = Inotify()
        i.add_watch('.')
        watched_file = sys.argv[1]
        import os
        common = os.path.commonpath([os.getcwd(), watched_file])
        watched_file = watched_file[1+len(common):]
        with kernel() as k:
            try:
                k.process(open(watched_file, 'r').read(), std)
            except FileNotFoundError:
                pass
            for event in i.event_gen(yield_nones=False):
                (_, event_type, _, filename) = event
                # print(event_type, filename)

                if event_type == ['IN_CLOSE_WRITE'] and filename == watched_file:
                    k.process(open(watched_file, 'r').read(), std)

                if event_type == ['IN_CLOSE_WRITE'] and filename == '.requests':
                    request, body = open(filename, 'r').read().split('\n', 1)
                    cmd, pos, client, session, *args = request.split(' ')
                    pos = int(pos)

                    def send(msg):
                        msg = 'eval -client {} "{}"'.format(client, qq(msg))
                        p = Popen(['kak', '-p', str(session).rstrip()], stdin=PIPE)
                        p.stdin.write(msg.encode())
                        p.stdin.flush()
                        p.stdin.close()
                        p.wait()

                    if cmd == 'complete':
                        for matches in k.complete(body, pos, std):
                            msg = ['"' + qq(m) + '|neptyne_inspect|' + qq(m) + '"' for m in matches]
                            msg = ' '.join(args + msg)
                            send(msg)

                    elif cmd == 'inspect':
                        for text in k.inspect(body, pos, std):
                            print('\n' + text)
                            width, height = map(int, args)
                            msg = unansi(text)
                            msg = [line[:width-8] for line in msg.split('\n')]
                            msg = '\n'.join(msg[:height-8])
                            msg = 'info "{}"'.format(qq(msg))
                            send(msg)

                    else:
                        print('Invalid command: ', cmd)



