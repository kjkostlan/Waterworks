# Note: most tests are not in Waterworks (due to the difficulty testing things), there are in other projects that use waterworks.
from . import fittings, deep_stack, colorful

def test_colorful():
    out = True
    r1 = colorful.wrap('foo')
    r2 = colorful.wrap(r1)
    r0_A = colorful.unwrap_all(r1)
    r0_B = colorful.unwrap_all(r2)
    out = out and len(r1)>len('foo') and len(r2)>len(r1) and r0_A == 'foo' and r0_B == 'foo'
    s0 = 'bar baz'; s1 = 'bar\nbaz'
    rs0 = colorful.wrap(s0); rs1 = colorful.wrap(s1)
    out = out and len(rs1)>len(rs0) and colorful.unwrap(rs1)== s1

    return out

def test_deep_stack():
    # Simple test of error propagation.
    out = True
    def f1(x):
        if x<128:
            return x/0
        else:
            return ERROR
    def f2(x):
        return f1(x)*2
    def f3(x):
        return f2(x)*3

    try:
        f3(2)
        exc = None
    except Exception as e:
        exc = e

    try:
        try:
            f3(2)
        except:
            f3(2000)
        exc_nest = None
    except Exception as e:
        exc_nest = e

    msg = deep_stack.from_exception(exc)
    out = out and 'ZeroDivisionError' in msg and 'division by zero' in msg and '\n' in msg and 'line ' in msg and 'in f3: return f2(x)*3' in msg

    try:
        f3(256)
        exc2 = None
    except Exception as e:
        exc2 = e
    msg2 = deep_stack.from_exception(exc2)
    msg12 = deep_stack.concat(msg, msg2)
    out = out and 'ERROR' in msg12 and 'ZeroDivisionError' in msg12 and msg12.count(deep_stack._head) == 1 and msg12.count(deep_stack._tail) == 1

    msg1 = deep_stack.from_greebled_stderr('foo\n'+msg+'\nbar', compress_multible=False)
    out = out and msg1.strip() == msg.strip() and (not deep_stack.from_greebled_stderr('foo bar baz'))

    msg_nest = deep_stack.from_exception(exc_nest)
    out = out and "name 'ERROR' is not defined" in msg_nest and 'ZeroDivisionError' in msg_nest

    try:
        deep_stack.raise_from_message(msg)
        e1 = None
    except Exception as _e:
        e1 = _e
    msg11 = deep_stack.from_exception(e1)
    out = out and msg11==msg

    vanilla_extract = deep_stack.from_vanilla_stderr('foo\n'+deep_stack.the_old_way(exc)+'\nbar', compress_multible=True)
    out = out and deep_stack.from_exception(exc)==vanilla_extract

    msg_ez = deep_stack.remove_greebles(msg)
    out = out and 'ZeroDivisionError' in msg_ez and 'division by zero' in msg_ez and '\n' in msg_ez and 'line ' in msg_ez and 'in f3: return f2(x)*3' in msg_ez
    out = out and len(msg_ez)<len(msg) and deep_stack.remove_greebles(msg_ez) == msg_ez and deep_stack.add_greebles(msg_ez) == msg
    return out