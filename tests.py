# Note: most tests are not in Waterworks (due to the difficulty testing things), there are in other projects that use waterworks.
from . import fittings, err_prop

def test_error_prop():
    # Simple test of error propigation.
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

    out = True
    msg = err_prop.ex2verbose_message(exc)
    out = out and 'ZeroDivisionError' in msg and 'division by zero' in msg and '\n' in msg and 'line ' in msg and 'in f3: return f2(x)*3' in msg

    try:
        f3(256)
        exc2 = None
    except Exception as e:
        exc2 = e
    msg2 = err_prop.ex2verbose_message(exc2)
    msg12 = err_prop.concat(msg, msg2)
    out = out and 'ERROR' in msg12 and 'ZeroDivisionError' in msg12 and msg12.count(err_prop._head) == 1 and msg12.count(err_prop._tail) == 1

    msg1 = err_prop.stderr2verbose_message('foo\n'+msg+'\nbar', compress_multible=False, helpful_id=None)
    out = out and msg1.strip() == msg.strip()

    try:
        err_prop.raise_from_message(msg)
        e1 = None
    except Exception as _e:
        e1 = _e
    msg11 = err_prop.ex2verbose_message(e1)
    out = out and msg11==msg

    msg_ez = err_prop.verbose_message2pprint(msg)
    out = out and 'ZeroDivisionError' in msg_ez and 'division by zero' in msg_ez and '\n' in msg_ez and 'line ' in msg_ez and 'in f3: return f2(x)*3' in msg_ez
    out = out and len(msg_ez)<len(msg)
    return out
