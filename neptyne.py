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

async def watch(connections, initial_files=[]):

    assert not docs, 'Watch already started'

    async def doc(filename):
        if filename not in docs:
            docs[filename] = await Document(filename, connections)
        return docs[filename]

    async def do(filename, body):
        d = await doc(filename)
        d.new_body(body)

    for filename in initial_files:
        await do(filename, open(filename, 'r').read())

    watcher = aionotify.Watcher()
    watcher.watch(path='.', flags=aionotify.Flags.CLOSE_WRITE)
    loop = asyncio.get_event_loop()
    await watcher.setup(asyncio.get_event_loop())
    while True:
        event = await watcher.get_event()
        # print('event:', event)
        filename = event.name
        if filename in initial_files:
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
            params.body = body
            for k, v in params.items():
                if 'cursor_' in k:
                    params[k] = int(v)
            # print(pformat(params))
            if params.type == 'process':
                await do(params.bufname, body)
            elif params.type in {'restart', 'complete', 'inspect'}:
                d = await doc(params.bufname)
                await d[params.type](**params)
            else:
                print('Unknown request:', pformat(params))

app = web.Application()
routes = web.RouteTableDef()

@routes.get('/ws')
async def websocket_connection(request):
    websocket = web.WebSocketResponse()
    await websocket.prepare(request)

    print(request)

    q = asyncio.Queue()

    async def fwd(filename, state):
        await q.put((filename, state))

    connections.append(fwd)
    for _, d in docs.items():
        d.broadcast()

    sent = set()

    while True:
        filename, state = await q.get()
        print('sending to ws')
        await websocket.send_json(state.all)
        print('sending to ws, done!')

    return websocket

@routes.get('/')
def root(request):
    text=f"""
    <!DOCTYPE html>
    <html>
    <head>
    <script type="module">
      console.error("todo add bundled file here")
    </script>
    </head>
    <body>
    <div id=root/>
    </body>
    </html>
    """
    return web.Response(text=text, content_type='text/html')

# static_dir = os.environ.get('NEPTYNE_DEV_DIR', os.path.dirname(__file__) or '.')

# app.add_routes([
    # web.static('/static/', static_dir, show_index=True, append_version=True),
# ])

app.router.add_routes(routes)

async def async_main():
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
        browser = False
        while len(args) >= 1 and args[0].startswith('-'):
            two = len(args) >= 2
            if args[0] == '--browser':
                browser = True
                args = args[1:]
            elif two and args[0].startswith('-p'):
                port = int(args[1])
                args = args[2:]
            elif two and args[0].startswith('-b'):
                host = args[1]
                args = args[2:]
            elif two and args[0].startswith('-h'):
                print('neptyne [-p PORT] [-b BIND_ADDR] --browser [FILES...]')
                sys.exit(0)
            else:
                raise 'Unknown flag: ' + args[0]
        if browser:
            import subprocess
            subprocess.Popen(f'chromium --app=http://localhost:{port} & disown', shell=True)
        runner = web.AppRunner(app, access_log_format='%t %a %s %r')
        await runner.setup()
        site = web.TCPSite(runner, host, port)
        await site.start()

        await watch(connections, args)

        await runner.cleanup()

def main():
    try:
        asyncio.run(async_main())
    except Exception as e:
        import traceback as tb
        tb.print_exc()
        asyncio.run(document.close_documents())

if __name__ == '__main__':
    main()

