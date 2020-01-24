from pprint import pprint, pformat

import jupyter_kernel_mgmt as jkm

import asyncio
import aionotify
import aiohttp
from aiohttp import web

import re
from itertools import zip_longest

async def aseq(*futs):
    for fut in futs:
        await fut

def kernel_executor(k):
    q = asyncio.Queue()

    # todo: handle messages that are out of order (not obviously connected to a section)

    done = object()

    def handler(msg, where):
        try:
            type = msg.header['msg_type']
            content = msg.content
            if where == 'iopub' and type == 'execute_result':
                q.put_nowait(dotdict(type='data', data=content['data'], msg_type=type))
            elif where == 'iopub' and type == 'display_data':
                q.put_nowait(dotdict(type='data', data=content['data'], msg_type=type))
            elif where == 'iopub' and type == 'stream':
                q.put_nowait(dotdict(type='stream', data={'text/plain': content['text']}, stream=content['name'], msg_type=type))
            elif type == 'error':
                q.put_nowait(dotdict(type='error', data={'text/plain': '\n'.join(content['traceback'])}, **content, msg_type=type))
            elif type in 'execute_input status shutdown_reply'.split():
                pass
            else:
                q.put_nowait(dotdict(type='unknown', data={'text/plain': 'unknown: ' + pformat(dict(type=type, content=content))}, msg_type=type))
        except Exception as e:
            q.put_nowait(dotdict(type='internal_error', data={'text/plain': 'error: ' + str(e)}, msg_type=type))

    k.add_handler(handler, 'iopub')

    async def execute(code):
        asyncio.create_task(aseq(k.execute(code), q.put(done)))
        while True:
            item = await q.get()
            if item is done:
                break
            else:
                yield item

    return execute

async def one(name):
    async with jkm.run_kernel_async('spec/python3') as k:
        execute = kernel_executor(k)

        async def logged_execute(code):
            async for msg in execute(code):
                print(name + ':', msg, end='')

        await logged_execute('"Hello world!"')

        await asyncio.gather(
            logged_execute('import asyncio; await asyncio.sleep(1000)'),
            aseq(asyncio.sleep(0.3), k.interrupt()),
        )

        await logged_execute('import time\nfor i in range(5): time.sleep(0.3) or print(i)\n5')

        await logged_execute('err')

class dotdict(dict):
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__


def id_stream(prevs):
    id = max([0] + [prev.id or 0 for prev in prevs])
    def bump():
        nonlocal id
        id += 1
        return id
    return bump


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

    prevs_by_line = {p.line_end: p for p in prevs}
    prevs_by_line_range = {
        prevs_by_line[prev_line].id
        for _, prev_line in movements.items()
        if prev_line in prevs_by_line
    }

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

async def runner():
    # async with jkm.run_kernel_async('spec/python3') as k:
    _m, k = await jkm.start_kernel_async('spec/python3')
    execute = kernel_executor(k)

    async def process_queue(queue):
        # pprint(queue)
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
        next_id = id_stream(queue)
        def state(done, now=None, scheduled=[]):
            all = done + ([now] if now else []) + scheduled
            return dotdict(done=done, now=now, scheduled=scheduled, all=all)
        errored = False
        for i, now in enumerate(outdated):
            scheduled = outdated[i+1:]
            now = dotdict(now, id=next_id(), status='executing', msgs=[])
            yield state(done, now, scheduled)

            async for msg in execute(now.code):
                now = dotdict(now, id=next_id(), msgs=[*now.msgs, msg])
                yield state(done, now, scheduled)
                # TODO
                # if msg.type == 'error' or msg.type == 'cancel':
                #     errored = True

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
    async def rerun(body):
        nonlocal prevs
        queue = list(calculate_queue(body, prevs))
        async for state in process_queue(queue):
            yield state
            prevs = state.done

    return rerun


async def watch(connections, initial_files=None):

    runners = {}

    async def do(filename, body):
        if filename not in runners:
            runners[filename] = await runner()
        async for state in runners[filename](body):
            for c in connections:
                asyncio.create_task(c(filename, state))

    for filename in initial_files or []:
        asyncio.create_task(do(filename))

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
            if msg.data and 'text/plain' in msg.data:
                print(msg.data['text/plain'], end='')
        if d.msgs: print()

    if state.now:
        # print(state.now.line_begin, '-', state.now.line_end, ':', state.now.status)
        for msg in state.now.msgs:
            if msg.data and 'text/plain' in msg.data:
                print(msg.data['text/plain'], end='')

        # pprint(state)

        D, S = map(len, [state.done, state.scheduled])

        print(str(D) + '/' + str(1 + D + S))
    else:
        print()
        print()

app = web.Application()
routes = web.RouteTableDef()

connections = []

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
        print('sending blobs', blobs)
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

app.add_routes([
    web.static('/static/', '.', show_index=True, append_version=True),
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
        print(event)
        await websocket.send_str(event.name)

    watcher.close()
    return websocket

app.router.add_routes(routes)

async def main():
    import sys
    if sys.argv[1:2] == ['test']:
        await asyncio.gather(
            one('A'),
            one('B')
        )
    else:
        connections.append(stdout_connection)
        port = 8234
        runner = web.AppRunner(app, access_log_format='%t %a %s %r')
        print('a1')
        await runner.setup()
        print('a2')
        site = web.TCPSite(runner, 'localhost', port)
        print('a3')
        await site.start()
        print('a4')

        await watch(connections, sys.argv[1:])

        # await runner.cleanup()
        # print('a5')
        # web.run_app(app, host='127.0.0.1', port=port)

asyncio.run(main())
