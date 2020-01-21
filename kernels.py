from pprint import pprint

import jupyter_client as jc
import jupyter_kernel_mgmt as jkm

import zmq.asyncio
import zmq

def pm(msg):
    try:
        return (msg.header['msg_type'], msg.content)
    except Exception as e:
        return str(e)

async def one(name):
    async with jkm.run_kernel_async('spec/python3') as k:
        def printer(msg, where):
            try:
                type, content = pm(msg)
                if where == 'iopub' and type == 'execute_result':
                    print(name + ':', content['data']['text/plain'])
                elif where == 'iopub' and type == 'stream':
                    print(name + ':', content['text'], end='')
                elif type in 'execute_input status shutdown_reply'.split():
                    pass
                elif type == 'execute_reply':
                    print('execute_reply', content)
                elif type == 'error':
                    print('\n'.join(content['traceback']))
                else:
                    pprint((name, where, *pm(msg)))
            except Exception as e:
                print('error', str(e))

        k.add_handler(printer, 'iopub')

        await k.execute('5')

        # return

        # await k.execute('import time\nfor i in range(5): time.sleep(0.3) or print(i)\n5')

        # x = await k.execute('import asyncio; await asyncio.sleep(1) or "first"')
        # printer(x, 'execute')

        await k.execute('err')

        async def seq(*futs):
            for fut in futs:
                await fut

        x, y = await asyncio.gather(
            k.execute('import asyncio; await asyncio.sleep(1000)'),
            seq(asyncio.sleep(0.3), k.interrupt()),
        )

        # print(x)

async def main():
    await one('A')
    # await asyncio.gather(
    #     one('A'),
    #     one('B')
    # )

import asyncio
asyncio.run(main())
