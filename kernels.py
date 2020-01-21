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

    done = object()

    def handler(msg, where):
        try:
            type = msg.header['msg_type']
            content = msg.content
            if where == 'iopub' and type == 'execute_result':
                q.put_nowait(content['data']['text/plain'] + '\n')
            elif where == 'iopub' and type == 'stream':
                q.put_nowait(content['text'])
            elif type == 'error':
                q.put_nowait('\n'.join(content['traceback']) + '\n')
            elif type in 'execute_input status shutdown_reply'.split():
                pass
            else:
                q.put_nowait(pformat([type, content]) + '\n')
        except Exception as e:
            q.put_nowait('error: ' + str(e) + '\n')

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



def render(state):
    print(chr(27) + "[2J")
    for d in state.done:
        for msg in d.msgs or []:
            print(msg, end='')
        if d.msgs: print()

    if state.now:
        for msg in state.now.msgs:
            print(msg, end='')
        print()

        # pprint(state)

        D, S = map(len, [state.done, state.scheduled])

        print(str(D) + '/' + str(1 + D + S))
    else:
        print()
        print()

async def watch(filename):
    async with jkm.run_kernel_async('spec/python3') as k:
        execute = kernel_executor(k)

        async def process_queue(queue):
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

        watcher = aionotify.Watcher()
        watcher.watch(path='.', flags=aionotify.Flags.CLOSE_WRITE)
        loop = asyncio.get_event_loop()
        await watcher.setup(asyncio.get_event_loop())
        prevs = []
        while True:
            body = open(filename, 'r').read()
            queue = list(calculate_queue(body, prevs))
            async for state in process_queue(queue):
                render(state)
                prevs = state.done
            event = await watcher.get_event()


async def main():
    import sys
    if len(sys.argv) == 2:
        await watch(sys.argv[-1])
    else:
        await asyncio.gather(
            one('A'),
            one('B')
        )

import asyncio
asyncio.run(main())
