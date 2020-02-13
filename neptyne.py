from pprint import pprint, pformat

import jupyter_kernel_mgmt as jkm

import asyncio
import aionotify
import aiohttp
from aiohttp import web

import os

from utils import *

import document
from document import Document

connections = []

docs = {}

async def watch(connections, initial_files=None):

    assert not docs, 'Watch already started'

    async def do(filename, body):
        if filename not in docs:
            docs[filename] = await Document(filename, connections)
        docs[filename].new_body(body)

    for filename in initial_files or []:
        await do(filename, open(filename, 'r').read())

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
            await do(filename, body)
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
                await do(params.bufname, body)
            else:
                print('Unknown request:', pformat(params))

app = web.Application()
routes = web.RouteTableDef()

@routes.get('/ws')
async def websocket_connection(request):
    websocket = web.WebSocketResponse()
    await websocket.prepare(request)

    q = asyncio.Queue()

    async def fwd(filename, state):
        await q.put((filename, state))

    connections.append(fwd)
    for _, d in docs.items():
        d.broadcast()


    sent = set()

    while True:
        filename, state = await q.get()
        await websocket.send_json(state.all)

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

app.add_routes([
    web.static('/static/', static_dir, show_index=True, append_version=True),
])

@routes.get('/inotify')
async def inotify_websocket(request):
    print('request', request)
    websocket = web.WebSocketResponse()
    await websocket.prepare(request)

    watcher = aionotify.Watcher()
    watcher.watch(path=static_dir, flags=aionotify.Flags.CLOSE_WRITE)

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
        await document.test()
    elif sys.argv[1:2] == ['kak_source']:
        print(open(os.path.join(static_dir, 'neptyne.kak'), 'r').read())
    else:
        connections.append(document.stdout_connection)
        port = 8234
        host = '127.0.0.1'
        args = list(sys.argv[1:])
        while len(args) >= 2 and args[0].startswith('-'):
            if args[0].startswith('-p'):
                port = int(args[1])
                args = args[2:]
            elif args[0].startswith('-b'):
                host = args[1]
                args = args[2:]
            elif args[0].startswith('-h'):
                print('neptyne [-p PORT] [-b BIND_ADDR] [FILES...]')
                sys.exit(0)
            else:
                raise 'Unknown flag: ' + args[0]
        runner = web.AppRunner(app, access_log_format='%t %a %s %r')
        await runner.setup()
        site = web.TCPSite(runner, host, port)
        await site.start()

        await watch(connections, args)

        await runner.cleanup()

def sync_main():
    try:
        asyncio.run(main())
    except Exception as e:
        import traceback as tb
        tb.print_exc()
        asyncio.run(document.close_documents())

if __name__ == '__main__':
    sync_main()

