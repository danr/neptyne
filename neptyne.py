from pprint import pprint, pformat

import jupyter_kernel_mgmt as jkm

import asyncio
import aionotify
import aiohttp
from aiohttp import web

import re
from itertools import zip_longest

import os

async def aseq(*futs):
    for fut in futs:
        await fut

class dotdict(dict):
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__


def id_stream(prevs=()):
    id = max([0] + [prev.id or 0 for prev in prevs])
    def bump():
        nonlocal id
        id += 1
        return id
    return bump


connections = []

kernels = []

async def Document(filename, kernel='spec/python3'):
    _m, k = await jkm.start_kernel_async('spec/python3')

    kernels.append(k)

    inbox = asyncio.Queue()

    def new_body(body):
        interrupt(body)

    def interrupt(new_body=[]):
        inbox.put_nowait(dotdict(type='interrupt', new_body=new_body))

    def handler(msg, where):
        enqueue = lambda **kws: inbox.put_nowait(dotdict(kws))
        try:
            type = msg.header['msg_type']
            content = msg.content
            if where == 'iopub' and type == 'execute_result':
                enqueue(type='data', data=content['data'], msg_type=type)
            elif where == 'iopub' and type == 'display_data':
                enqueue(type='data', data=content['data'], msg_type=type)
            elif where == 'iopub' and type == 'stream':
                enqueue(type='stream', data={'text/plain': content['text']}, stream=content['name'], msg_type=type)
            elif type == 'error':
                enqueue(type='error', data={'text/plain': '\n'.join(content['traceback'])}, **content, msg_type=type)
            elif type in 'execute_input status shutdown_reply'.split():
                pass
            else:
                enqueue(type='unknown', data={'text/plain': 'unknown: ' + pformat(dict(type=type, content=content))}, msg_type=type)
        except Exception as e:
            enqueue(type='internal_error', data={'text/plain': 'error: ' + str(e)}, msg_type=type)

    k.add_handler(handler, 'iopub')

    async def process():
        self = dotdict()
        self.next_id = id_stream()
        self.running = False
        self.interrupting = False
        self.connections = {}

        self.new_body = None
        self.done = []
        self.now = None
        self.scheduled = []

        def broadcast():
            all = self.done + ([self.now] if self.now else []) + self.scheduled
            state = dotdict(done=self.done, now=self.now, scheduled=self.scheduled, all=all)
            for c in connections: # self.connections.values():
                asyncio.create_task(c(filename, state))

        while True:
            msg = await inbox.get()
            print('interrupting:', int(bool(self.interrupting)), 'type:', msg.type)
            send_broadcast = False
            if msg.type == 'interrupt':
                if not self.running:
                    self.new_body = msg.new_body
                else:
                    if not self.interrupting:
                        # asyncio.create_task(k.interrupt())
                        k.interrupt()
                    self.interrupting = msg
            elif msg.type == 'execute_done':
                self.running = False
                if self.interrupting:
                    self.new_body = self.interrupting.new_body
                    self.interrupting = False
            elif msg.type in {'data', 'execute_result', 'stream', 'error'}:
                if not self.running:
                    # detached message
                    raise NotImplementedError
                self.now = dotdict(self.now, id=self.next_id(), msgs=[*self.now.msgs, msg])
                if msg.type == 'error':
                    cancelled = [
                        dotdict(s, id=self.next_id(), status='cancelled', msgs=s.msgs or s.prev_msgs, prev_msgs=None)
                        for s in [self.now, *self.scheduled]
                    ]
                    self.done = [*self.done, *cancelled]
                    self.now = None
                    self.scheduled = []
                send_broadcast = True

            if not self.running:
                if self.new_body:
                    queue = list(calculate_queue(self.new_body, self.done))
                    self.new_body = None
                    done = []
                    outdated = []
                    for i, q in enumerate(queue):
                        q.index = i
                    for i, q in enumerate(queue):
                        if q.status == 'done':
                            done.append(q)
                        else:
                            outdated = queue[i:]
                            break
                    self.done = done
                    self.now = None
                    self.scheduled = outdated
                    send_broadcast = True

                if self.now:
                    now = self.now
                    self.now = None
                    now = dotdict(now, id=self.next_id(), status='done')
                    if 'prev_msgs' in now:
                        del now['prev_msgs']
                    self.done = [*self.done, now]
                    send_broadcast = True

                if self.scheduled:
                    assert self.now is None
                    self.now, *self.scheduled = self.scheduled
                    self.now = dotdict(self.now, id=self.next_id(), status='executing', msgs=[])
                    asyncio.create_task(aseq(
                        k.execute(self.now.code),
                        inbox.put(dotdict(type='execute_done'))))
                    self.running = True
                    send_broadcast = True

            send_broadcast and broadcast()

    asyncio.create_task(process())

    return dotdict(locals())

def calculate_queue(body, prevs, movements={}):

    def trim(s):
        if s:
            return re.sub('\s*\n', '\n', re.sub('\#.*', '', s.strip()))
        return s

    def slices(s):
        return re.split(r'(?<=\S)(?=\n{2,}\S)', s)

    def line_count(s):
        return len(re.findall(r'\n', s))

    parts = slices(body)

    try:
        prevs_by_line = {p.line_end: p for p in prevs}
        prevs_by_line_range = {
            prevs_by_line[prev_line].id
            for _, prev_line in movements.items()
            if prev_line in prevs_by_line
        }
    except AttributeError as e:
        print('AttrError[', e, prevs, ']')
        prevs_by_line = {}
        prevs_by_line_range = {}

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
                id = next_id(),
                msgs = [],
            )
            if changed or (not prev or trim(prev.code) != trim(part) or prev.status == 'cancelled'):
                changed = True
                me.status = 'scheduled'
                moved_line = movements.get(line_end)
                if moved_line and moved_line in prevs_by_line:
                    # Here: check movements, prefer to pick the prev at this line
                    p = prevs_by_line[moved_line]
                    me.prev_msgs = p.msgs
                elif prev and prev.msgs and prev.id not in prevs_by_line_range:
                    me.prev_msgs = prev.msgs
            else:
                me.status = 'done'
                if prev and prev.msgs:
                    me.msgs = prev.msgs
            yield me
            line_begin = line_end

async def watch(connections, initial_files=None):

    docs = {}

    async def do(filename, body):
        if filename not in docs:
            docs[filename] = await Document(filename)
        docs[filename].new_body(body)

    for filename in initial_files or []:
        asyncio.create_task(do(filename, open(filename, 'r').read()))

    watcher = aionotify.Watcher()
    watcher.watch(path='.', flags=aionotify.Flags.CLOSE_WRITE)
    loop = asyncio.get_event_loop()
    await watcher.setup(asyncio.get_event_loop())
    while True:
        event = await watcher.get_event()
        # print('event:', event)
        filename = event.name
        if filename in (initial_files or []):
            body = open(filename, 'r').read()
            asyncio.create_task(do(filename, body))
        if filename == '.requests':
            contents = open('.requests', 'r').read()
            params = dotdict()
            lines = contents.split('\n')
            for i, line in enumerate(lines):
                if ' ' not in line:
                    continue
                k, v = line.split(' ', 1)
                if k == '---':
                    body = '\n'.join(lines[i+1:])
                    break
                params[k] = v
            # print(pformat(params))
            if params.type == 'process':
                asyncio.create_task(do(params.bufname, body))
            else:
                print('Unknown request:', pformat(params))

async def stdout_connection(filename, state):
    # print(chr(27) + "[2J")
    print(filename)
    for d in state.done:
        # print(d.line_begin, '-', d.line_end, ':', d.status)
        for msg in d.msgs or []:
            # break
            if msg.data and 'text/plain' in msg.data:
                print(msg.data['text/plain'], end='')
        if d.msgs: print()

    if state.now:
        # print(state.now.line_begin, '-', state.now.line_end, ':', state.now.status)
        for msg in state.now.msgs:
            # break
            if msg.data and 'text/plain' in msg.data:
                print(msg.data['text/plain'], end='')

        # pprint(state)

        D, S = map(len, [state.done, state.scheduled])

        # print(str(D) + '/' + str(1 + D + S))
    else:
        # print()
        print()

app = web.Application()
routes = web.RouteTableDef()

@routes.get('/ws')
async def websocket_connection(request):
    websocket = web.WebSocketResponse()
    await websocket.prepare(request)

    q = asyncio.Queue()

    async def fwd(filename, state):
        q.put_nowait((filename, state))

    connections.append(fwd)

    sent = set()

    while True:
        filename, state = await q.get()
        blobs = []
        for blob in state.all:
            f_id = filename, blob.id
            if f_id not in sent:
                sent.add(f_id)
            blobs.append(blob)
        # print('sending blobs', blobs)
        await websocket.send_json(dict(blobs=blobs, num_cells=len(state.all)))

    return websocket

def track(url):
    url = repr(url)
    track="""
        "use strict";
        {
          let i = 0
          const reimported = {}
          const sloppy = s => s.replace(/.*\//g, '')
          window.reimport = src => {
            // console.log('Reimporting', src)
            reimported[sloppy(src)] = true
            return import('./static/' + src + '#' + i++)
          }
          const tracked = {}
          window.track = src => {
            if (!tracked[src]) {
              console.log('Tracking', src)
              tracked[src] = true;
              reimport(src)
            }
          }
          try {
            if (window.track_ws.readyState != websocket.OPEN) {
              window.track_ws.close()
            }
          } catch {}
          const ws_url = 'ws://' + window.location.host + '/inotify'
          window.track_ws = new WebSocket(ws_url)
          window.track_ws.onmessage = msg => {
            // console.log(sloppy(msg.data), ...Object.keys(reimported))
            const upd = sloppy(msg.data)
            if (reimported[upd]) {
              Object.keys(tracked).forEach(src => {
                console.log('Reloading', src, 'because', upd, 'was updated')
                reimport(src)
              })
            }
          }
        }
    """
    text=f"""
    <html>
    <head>
    <script type="module">
        {track}
        track({url})
    </script>
    </head>
    <body></body>
    </html>
    """
    return web.Response(text=text, content_type='text/html')

@routes.get('/{track}.js')
def _track(request):
    return track(request.match_info.get('track') + '.js')

@routes.get('/')
def root(request):
    return track('index.js')


static_dir = os.environ.get('NEPTYNE_DEV_DIR', os.path.dirname(__file__))

print(f'Using {static_dir=}')

app.add_routes([
    web.static('/static/', static_dir, show_index=True, append_version=True),
])

@routes.get('/inotify')
async def inotify_websocket(request):
    print('request', request)
    websocket = web.WebSocketResponse()
    await websocket.prepare(request)

    watcher = aionotify.Watcher()
    watcher.watch(path='.', flags=aionotify.Flags.CLOSE_WRITE)

    loop = asyncio.get_event_loop()
    await watcher.setup(loop)
    while True:
        event = await watcher.get_event()
        # print(event)
        await websocket.send_str(event.name)

    watcher.close()
    return websocket

app.router.add_routes(routes)

async def main():
    import sys
    if sys.argv[1:2] == ['test']:
        print('oops, no tests')
    elif sys.argv[1:2] == ['kak_source']:
        print(open(os.path.join(static_dir, 'neptyne.kak'), 'r').read())
    else:
        # connections.append(stdout_connection)
        port = 8234
        runner = web.AppRunner(app, access_log_format='%t %a %s %r')
        await runner.setup()
        site = web.TCPSite(runner, 'localhost', port)
        await site.start()

        await watch(connections, sys.argv[1:])

        await runner.cleanup()

def sync_main():
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        for k in kernels:
            k.close()

if __name__ == '__main__':
    sync_main()

