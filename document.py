from pprint import pprint, pformat

import jupyter_kernel_mgmt as jkm
import asyncio

import re
from itertools import zip_longest

from utils import *

import time

_documents = []

async def close_documents():
    for d in _documents:
        await d.close()

next_id = id_stream()

# new_body: str
# prevs: [{code: str, id: str, status, msgs, prev_msgs}]
# returns: [{code: str, id: str, status, msgs, prev_msgs}]
# For now actually does not make any diff, just checks which cells are equal
def diff_new_body(new_body, prevs):

    def trim(s):
        if s:
            return re.sub('\s*\n', '\n', re.sub('\#.*', '', s.strip()))
        return s

    def slices(s):
        return re.split(r'(?<=[^\n])(?=\n{2,}\S)', s)

    def line_count(s):
        return len(re.findall(r'\n', s))

    new_codes = slices(new_body)

    out = dotdict(
        done = [],
        scheduled = []
    )

    changed = False
    for code, prev in zip_longest(new_codes, prevs):
        if code is not None:
            me = dotdict(
                code=code,
                msgs=[],
                id=next_id(),
            )
            if changed or (not prev or trim(prev.code) != trim(code) or prev.status == 'cancelled'):
                changed = True
                me.status = 'scheduled'
                if prev:
                    me.prev_msgs = prev.msgs or prev.prev_msgs or []
            else:
                me.status = 'done'
                if prev:
                    me.msgs = prev.msgs
                    me.prev_msgs = prev.prev_msgs
            out[me.status].append(me)

    # pprint(dotdict(out, new_body=new_body))

    return out

IDs = 0

async def Document(filename, connections, kernel='spec/python3'):

    global IDs
    ID = IDs
    IDs += 1

    active = await _Document(filename, connections, kernel, ID)

    self = dotdict()

    for f in active.keys():
        self[f] = (lambda f=f: lambda *args, **kws: active[f](*args, **kws))()

    async def watcher():
        nonlocal active
        while True:
            await asyncio.sleep(0.1)
            y = await active.k.is_alive()
            if active.closed:
                return
            if not y:
                print(ID, 'Kernel has died, restarting')
                last_body = active.last_body
                active = await _Document(filename, connections, kernel, ID)
                active.new_body(last_body)

    asyncio.create_task(watcher())

    return self


async def _Document(filename, connections, kernel, ID):
    m, k = await jkm.start_kernel_async(kernel)

    inbox = asyncio.Queue()

    async def close():
        self.closed = True
        _documents.remove(self)
        inbox.put_nowait(dotdict(type='shutdown'))
        await k.shutdown()
        k.close()
        await m.wait()

    prio = 0

    def new_body(body):
        self.last_body = body
        nonlocal prio
        prio += 1
        inbox.put_nowait(dotdict(type='interrupt', new_body=body, prio=prio))

    def handler(msg, where):
        enqueue = lambda **kws: inbox.put_nowait(dotdict(kws))
        try:
            type = msg.header['msg_type']
            content = msg.content
            # print(type, msg.content['execution_state'] if type == 'status' else '')
            if where == 'iopub' and type == 'execute_result':
                enqueue(type='data', data=content['data'], msg_type=type)
            elif where == 'iopub' and type == 'display_data':
                enqueue(type='data', data=content['data'], msg_type=type)
            elif where == 'iopub' and type == 'stream':
                enqueue(type='stream', data={'text/plain': content['text']}, stream=content['name'], msg_type=type)
            elif type == 'error':
                enqueue(type='error', data={'text/plain': '\n'.join(content['traceback'])}, **content, msg_type=type)
            elif type == 'status':
                enqueue(type='status', state=msg.content['execution_state'])
            elif type == 'execute_input':
                pass
            elif type in 'shutdown_reply'.split():
                # print(time.monotonic(), ID, 'Unhandled:', msg, msg.content)
                pass
            else:
                raise ValueError('Unknown type:' + type)
        except Exception as e:
            print(time.monotonic(), ID, '*** INTERNAL ERROR in iopub handler ***')
            import traceback as tb
            tb.print_ID, exc()

    k.add_handler(handler, 'iopub')

    async def process():
        self = dotdict()
        self.running = False
        self.interrupting = False

        self.new_body = None
        self.done = []
        self.now = None
        self.scheduled = []

        self.last_interrupt = time.monotonic() - 1
        self.body_prio = -1

        self.busy = False

        async def broadcast():
            all = self.done + ([self.now] if self.now else []) + self.scheduled
            state = dotdict(self, all=all) # done=self.done, now=self.now, scheduled=self.scheduled, all=all)
            for c in connections:
                await c(filename, state)

        while True:
            msg = await inbox.get()
            send_bropdcast = False
            cancel_queue = False
            # pprint((ID, msg, self), compact=True)
            # print(ID, time.monotonic(), msg.type, self.max_interrupt, msg.prio, self.body_prio, self.finished)
            if not await k.is_alive():
                pprint(('not alive:', ID, msg, self), compact=True)
                return
            if msg.type == 'shutdown':
                return
            elif msg.type == 'status':
                self.busy = msg.state == 'busy'
            elif msg.type == 'interrupt':
                if not self.interrupting or msg.prio >= self.interrupting.prio:
                    if not self.running and msg.prio > self.body_prio:
                        self.body_prio = msg.prio
                        self.new_body = msg.new_body
                    elif self.running and msg.prio > self.body_prio:
                        self.interrupting = msg
                        # reschedule this in case kernel is not ready to be interrupted
                        if self.busy:
                            self.busy = False
                            await k.interrupt()
                            # print(ID, time.monotonic(), 'interrupt sent', msg.prio)
                        else:
                            asyncio.create_task(aseq(
                                asyncio.sleep(0.5),
                                inbox.put(dotdict(msg, rerun=True))))
                            # print(ID, time.monotonic(), 'too early to interrupt', msg.prio)
            elif msg.type == 'execute_done':
                self.finished = self.now.id if self.now else self.finished
                self.running = False
                if self.interrupting and self.interrupting.prio > self.body_prio:
                    self.body_prio = self.interrupting.prio
                    self.new_body = self.interrupting.new_body
                    self.interrupting = False
                    cancel_queue = True
            elif msg.type in {'data', 'execute_result', 'stream', 'error'}:
                # if msg.type == 'error':
                #     print(msg.ename)
                #     print(msg.data['text/plain'])
                # if msg.type == 'stream': print(time.monotonic(), ID, msg)
                if not self.running:
                    print('detached message:', msg)
                interrupted = msg.type == 'error' and msg.ename == 'KeyboardInterrupt'
                msg.id = next_id()
                if not interrupted:
                    self.now = dotdict(self.now, msgs=[*self.now.msgs, msg])
                if msg.type == 'error':
                    cancel_queue = True

            if cancel_queue:
                cancelled = [
                    dotdict(s, status='cancelled', msgs=s.msgs or s.prev_msgs, prev_msgs=None)
                    for s in [self.now, *self.scheduled] if s
                ]
                self.done = [*self.done, *cancelled]
                self.now = None
                self.scheduled = []
                send_broadcast = True

            if not self.running:
                if self.new_body:
                    d = diff_new_body(self.new_body, self.done)
                    self.new_body = None
                    self.done = d.done
                    self.now = None
                    self.scheduled = d.scheduled
                    send_broadcast = True

                if self.now:
                    now = self.now
                    self.now = None
                    now = dotdict(now, status='done')
                    self.done = [*self.done, now]
                    send_broadcast = True

                if self.scheduled:
                    assert self.now is None
                    self.now, *self.scheduled = self.scheduled
                    self.now = dotdict(self.now, status='executing', msgs=[])
                    # print(ID, 'executing', repr(self.now.code), self.body_prio)
                    asyncio.create_task(aseq(
                        k.execute(self.now.code, store_history=False),
                        inbox.put(dotdict(type='execute_done', state=dotdict(self)))))
                    self.running = True
                    send_broadcast = True

            send_broadcast and await broadcast()

    asyncio.create_task(process())

    self = dotdict(locals())
    self.closed = False

    _documents.append(self)

    return self

async def stdout_connection(filename, state, seen=set()):
    for d in state.all:
        for msg in d.msgs or []:
            if msg.data and 'text/plain' in msg.data:
                if msg.id not in seen:
                    if d.id not in seen:
                        seen.add(d.id)
                        print()
                    seen.add(msg.id)
                    print(msg.data['text/plain'].rstrip())

def output(state):
    # pprint(state)
    return [m.data['text/plain'].strip() for cell in state.all for m in cell.msgs if cell.status != 'cancelled']

def prev_output(state):
    # pprint(state)
    return [m.data['text/plain'].strip() for cell in state.all for m in cell.prev_msgs or []]


def assert_eq(a, b, obj=None):
    assert a == b, str(a) + ' != ' + str(b) + ('' if obj is None else ' ' + pformat(obj))
    print(str(a) + ' == ' + str(b))


async def test_kernel():
    q = asyncio.Queue()
    async def c(filename, state):
        if state.running == False:
            await q.put(state)

    cs = [c]
    d = await Document('test.py', cs)
    return q, d


async def test_kernel_with_all_finished():
    q = asyncio.Queue()
    last = None
    async def c(filename, state):
        nonlocal last
        if state.finished != last:
            last = state.finished
            await q.put(state)

    cs = [c]
    d = await Document('test.py', cs)
    return q, d




async def test_abc():
    q, d = await test_kernel()

    d.new_body('print("a")')
    s = await q.get()
    assert_eq([], prev_output(s))
    assert_eq(['a'], output(s))

    d.new_body('print("b")')
    s = await q.get()
    assert_eq(['a'], prev_output(s))
    assert_eq(['b'], output(s))

    d.new_body('print("c")')
    s = await q.get()
    assert_eq(['b'], prev_output(s))
    assert_eq(['c'], output(s))

    await d.close()


async def test_keep():
    q, d = await test_kernel()

    d.new_body('x = 0; x\n\nx += 1; x\n\nx += 2; x')
    s = await q.get()
    assert_eq(['0', '1', '3'], output(s))

    d.new_body('x = 0; x\n\nx += 1; x\n\nx += 3; x')
    s = await q.get()
    assert_eq([          '3'], prev_output(s))
    assert_eq(['0', '1', '6'], output(s))

    d.new_body('x = 0; x\n\nx += 2; x\n\nx += 3; x')
    s = await q.get()
    assert_eq([     '1', '6'], prev_output(s))
    assert_eq(['0', '8', '11'], output(s))

    await d.close()


async def test_interrupt():
    q, d = await test_kernel()
    d.new_body('while True: print(len(list(range(10**6))))')
    print('Interrupting...')
    d.new_body('print("interrupted 1!")')
    d.new_body('print("interrupted 2!")')
    d.new_body('print("interrupted 3!")')
    d.new_body('print("interrupted 4!")')
    d.new_body('print("interrupted 5!")')
    d.new_body('print("interrupted 6!")')
    d.new_body('print("interrupted 7!")')
    d.new_body('print("interrupted 8!")')
    s = await q.get()
    assert_eq(['interrupted 8!'], output(s))

    await d.close()


async def test_a_interrupt_c():
    q, d = await test_kernel()

    d.new_body('print("a")')
    assert_eq(['a'], output(await q.get()))

    d.new_body('while True: pass')
    print('Interrupting...')

    d.new_body('print("c")')
    s = await q.get()
    assert_eq(['a'], prev_output(s))
    assert_eq(['c'], output(s))

    print('ok!')

    await d.close()

async def test_prios():
    q, d = await test_kernel_with_all_finished()

    d.new_body('1')
    assert_eq(['1'], output(await q.get()))

    for X in range(5, 15):
        d.new_body('\n\n'.join(f"print(len(list(range(1000000))) and {i}, end='')" for i in range(X)))
        out = []
        for i in range(3):
            # print(f'slow {i}')
            out.append(str(i))
            s = await(q.get())
            assert_eq(out, output(s), s)

        d.new_body('\n\n'.join(f"print(len(list(range(100000))) and {i}, end='')" for i in range(X)))
        out = []
        for i in range(X + 1):
            # print(f'quick {i}')
            s = await(q.get())
            assert_eq(out, output(s), s)
            out.append(str(i))

    await d.close()

async def test():
    await test_abc()
    await test_keep()
    for i in range(5):
        await test_interrupt()
    for i in range(5):
        await test_a_interrupt_c()
    await test_prios()

    return

    await asyncio.gather(
        *(aseq(asyncio.sleep(i*0.6), test_interrupt()) for i in range(2)),
        *(aseq(asyncio.sleep(i*0.6+0.3), test_a_interrupt_c()) for i in range(2)),
    )

    #async def crash():
    #    m, k = await jkm.start_kernel_async('spec/python3')
    #    k.add_handler(lambda *args, **kws: print(*args, **kws), 'iopub')
    #    asyncio.create_task(aseq(k.execute('while True: pass')))
    #    while True:
    #        await asyncio.sleep(0.01)
    #        await k.interrupt()
    #        a = await k.is_alive()
    #        # print(a)
    #        if not a:
    #            break
    #    await k.shutdown()
    #    k.close()

    # await asyncio.gather(
    #     *(aseq(asyncio.sleep(i*0.1), crash()) for i in range(50)),
    # )

    print('done')
