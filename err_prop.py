# Error propagation, within and across different programs.
import traceback
import re

_head = '{{WaterworksErrPropStack}}' # Used to detect where the error is in a stream.
_tail = '[[ENDWaterworksErrPropStack]]'
_linehead = '<<Waterworks_ERR>>:'

def verbose_message2pprint(txt):
    txt = str(txt)
    return txt.replace(_head,'').replace(_tail,'').replace(_linehead,'').strip()

class VerboseError(Exception):
    # Verbose = Stack trace is in the message.
    def pprint(self):
        # Pretty-print a verbose exception (by converting the message into multiline text).
        # Will include a traceback.
        print(verbose_message2pprint('VerboseErrorTrace\n'+str(self)))

def ex2verbose_message(e):
    # Gets the verbose error message from an exception object (which may or may not be a VerboseError).
    if type(e) is VerboseError:
        return str(e) # How to get the message of the Exception.
    else:
        #https://stackoverflow.com/questions/62952273/catch-python-exception-and-save-traceback-text-as-string
        lines1 = ''.join(traceback.format_exception(None, e, e.__traceback__)).strip().replace('\r\n','\n').split('\n') #(traceback header) + where and/or line pairs + (Type+message)

        lines2 = []
        for _line in lines1[1:-1]:
            _line = _line.strip()
            if _line.startswith('File'):
                lines2.append(_line)
            else:
                if len(lines2)==0: # Hopefully doesn't happen.
                    lines2 = ['']
                lines2[-1] = lines2[-1]+': '+_line

        problem = _linehead+lines1[-1]
        lines_out = [_head]+[_linehead+_line for _line in lines2]+[problem]+[_tail]
        return '\n'.join(lines_out)

def _by2str(x):
    if type(x) is bytes:
        return x.decode('utf-8', errors='ignore').replace('\r\n','\n')
    return x

def concat(older, newer):
    # Concat verbose messages.
    def _msg_strip(msg):
        msg = _by2str(msg)
        if type(msg) is not str:
            msg = ex2verbose_message(msg)
        lines = msg.strip().split('\n')
        if len(lines)<3:
            return msg
        return '\n'.join(lines[1:-1]) # Remove the head and tail line.
    return _head+'\n'+_msg_strip(older)+'\n'+_msg_strip(newer)+'\n'+_tail

def stderr2verbose_message(stderr_blit, compress_multible=False, helpful_id=None):
    # Gets the verbose (containing stack) message from an stderr_blit (or stdout+sterr blit in case errors go to stdout).
    # None if it can't find anything.
    # compress_multible is useful if the error was called many times.
    # Optional helpful_id to make debugging easier.
    stderr_blit = _by2str(stderr_blit)

    ky = '(?s)'+re.escape(_head)+'.+?'+re.escape(_tail)
    blocks0 = re.findall(ky, stderr_blit)
    blocks = []
    for b in blocks0:
        lines = list(filter(lambda l: _head in l or _tail in l or _linehead in l, b.split('\n')))
        blocks.append('\n'.join(lines))
    if len(blocks)==0:
        return None
    if compress_multible: # remove redundant errors.
        blocks1 = []; _d = set()
        for b in blocks:
            if b not in _d:
                blocks1.append(b); _d.add(b)
    else:
        blocks1 = blocks
    out = blocks1[0]
    for b in blocks1[1:]:
        out = concat(out, b)
    return out

def raise_from_message(stack_message):
    # Raises a Verbose_error object from a message.
    # Only includes the stack trace from the message.
    stack_message = _by2str(stack_message)
    raise VerboseError(stack_message)
