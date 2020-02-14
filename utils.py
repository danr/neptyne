class dotdict(dict):
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__


async def aseq(*futs):
    for fut in futs:
        await fut


def id_stream(prevs=()):
    id = max([0] + [prev.id or 0 for prev in prevs])
    def bump():
        nonlocal id
        id += 1
        return id
    return bump


def traverseKVs(d, f):
    if isinstance(d, dict):
        return type(d)(
            (k, f(k, traverseKVs(v, f)))
            for k, v in d.items()
        )
    elif isinstance(d, list) or isinstance(d, tuple):
        return type(d)(traverseKVs(x, f) for x in d)
    else:
        return d

x = traverseKVs([dotdict(a=1), (dict(b=2),)], lambda k, v: str(k) + str(v))

assert type(x) == list

assert type(x[0]) == dotdict
assert x[0] == dotdict(a='a1')

assert type(x[1]) == tuple
assert type(x[1][0]) == dict
assert x[1][0] == dict(b='b2')
