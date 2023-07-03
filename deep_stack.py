# Why can't a stack trace span across multible processes? Or even into the cloud?
# It can! Just remember to err_prop.pprint to make nice printouts.
# Filtering the error from the actual message is a pain, hopefully our fns work here!
import traceback
import re
from . import colorful

_head = '{{WaterworksErrPropStack}}' # Identifiers "greebles" used to detect Exceptions in the stream.
_linehead = '<<Waterworks_ERR>>'
_tail = '[[ENDWaterworksErrPropStack]]'

################## String processing fns (Idempotent) ##########################

def _basic_txt(x):
    # Basic idempotent txt.
    if type(x) is list or type(x) is tuple:
        msg = '\n'.join([_basic_txt(xi) for xi in x])
    if type(x) is bytes:
        x = x.decode('utf-8', errors='ignore')
    x = str(x)
    x = x.replace('\r\n','\n')
    return x

def remove_greebles(msg):
    msg = _basic_txt(msg)
    lines = msg.split('\n')
    lines1 = []
    for l in lines:
        l = l.strip()
        if len(l)>0:
            lines1.append(l)
    msg = '\n'.join(lines1)
    return msg.replace(_head,'').replace(_tail,'').replace(_linehead,'').strip()

def add_greebles(txt):
    # Adds a line for the _head, the _tail, and adds _lineheads to each line in the middle.
    # These are used to.
    txt = remove_greebles(txt)
    lines = _basic_txt(txt).split('\n')
    return '\n'.join([_head]+[_linehead+l for l in lines]+[_tail])

def pprint(msg):
    msg = _basic_txt(str(msg))
    msg = remove_greebles(msg)
    lines = ['   '+l for l in msg.split('\n')]

    return '\n'.join(['Deep Traceback:']+lines)

################################# Stream concat ################################

def prepend_helpful_id(msg, helpful_id):
    # Does nothing if the helpful_id is None.
    if not helpful_id or len(helpful_id.strip())==0:
        return add_greebles(msg)
    msg = remove_greebles(msg)
    helpful_id = helpful_id.strip()
    lines = msg.split('\n')
    lines1 = [l.replace('File', 'File '+helpful_id) for l in lines]
    return add_greebles('\n'.join(lines1))

def concat(older, newer): # Two stacktraces; "most recent call last"!
    return add_greebles(remove_greebles(older)+'\n'+remove_greebles(newer))

def append1(older, line2add): # Adds a single line
    line2add = line2add.strip()
    return add_greebles(remove_greebles(older)+'\n'+line2add)

def _block_compress(blocks):
    blocks1 = []; _d = set()
    for b in blocks:
        if b not in _d:
            blocks1.append(b); _d.add(b)
    return blocks1

################## String processing fns (streams and exception objects) #######################

def the_old_way(e): # Includes the traceback.
    if type(e) is str:
        return e
    return ''.join(traceback.format_exception(None, e, e.__traceback__)).strip().replace('\r\n','\n')

def likely_traceline(line): # Location.
    return 'File' in line and bool(re.search('line \d+, in', line))

def _squish_lines(lines):
    lines2 = []
    for _line in lines[1:-1]:
        _line = _line.strip()
        if _line.startswith('File'):
            lines2.append(_line)
        else:
            if len(lines2)==0: # Hopefully doesn't happen.
                lines2 = ['']
            lines2[-1] = (lines2[-1]+': '+_line).strip()
    return lines2+[lines[-1].strip()] # No need to include the first line which says "Traceback"

def from_exception(e):
    # Gets the verbose error message from an exception object.
    if type(e) is VerboseError:
        return str(e) # How to get the message of the Exception.
    else:
        #https://stackoverflow.com/questions/62952273/catch-python-exception-and-save-traceback-text-as-string
        lines = the_old_way(e).split('\n') #(traceback header) + where and/or line pairs + (Type+message)
        lines = _squish_lines(lines)
        return add_greebles('\n'.join(lines))

def from_greebled_stderr(stderr_blit, compress_multible=False):
    # None if it can't find anything.
    # compress_multible is useful if the same error was raised more than once.
    stderr_blit = _basic_txt(stderr_blit)

    ky = '(?s)'+re.escape(_head)+'.+?'+re.escape(_tail)
    blocks0 = re.findall(ky, stderr_blit)
    blocks = []
    for b in blocks0:
        lines = list(filter(lambda l: _head in l or _tail in l or _linehead in l, b.split('\n')))
        blocks.append('\n'.join(lines))
    if len(blocks)==0:
        return None
    blocks1 = _block_compress(blocks) if compress_multible else blocks
    out = blocks1[0]
    for b in blocks1[1:]:
        out = concat(out, b)
    return out

def from_vanilla_stderr(stderr_blit, compress_multible=False):
    # Vanilla exceptions
    err_ky = 'Traceback (most recent call last)'
    pieces = ('tmp_header_I_want_to_be_excised\n'+_basic_txt(stderr_blit)).split(err_ky)
    if len(pieces)==1:
        return None
    for i in range(1, len(pieces)):
        txt = colorful.unwrap_all(pieces[i])
        lines = txt.split('\n')
        # A bit of a heuristic to filter lines:
        gap = -1; max_gap = -1; ever_found = False
        lines1 = []
        for l in lines:
            gap = gap+1; max_gap = max(max_gap, gap)
            if likely_traceline(l):
                gap = 0
                lines1.append(l)
            elif gap==1 and l.startswith('  '): # Line just after the.
                lines1.append(l)
            elif gap == 2 and max_gap == 2: # The last line.
                lines1.append(l)
                ever_found = True
        if len(lines1)==0:
            lines1 = ['Cant find any stack trace elements from the pipe;', 'cant find and file elements from the pipe']
        if not ever_found:
            lines1.append('Cant extract the Exception message from the pipe.')
        lines2 = _squish_lines([err_ky]+lines1)
        pieces[i] = '\n'.join(lines2)

    blocks1 = _block_compress(pieces[1:]) if compress_multible else pieces[1:]
    return add_greebles('\n'.join(blocks1))

def from_stream(stdout_blit, stderr_blit, compress_multible=False, helpful_id=None):
    # Picks out error messages from a stream; optional helpful_id which will be prepended.
    # Returns None if no error is found.
    greeble_mode = from_greebled_stderr(stdout_blit+'\n'+stderr_blit, compress_multible=compress_multible)
    out = None
    if greeble_mode: # Case 1: A verbose error was raised or printed out; supposed to stderr but many people send errors to stdout instead:
        # This is a strong error report, so it is safer to suppress the "vanilla" case below
        out = greeble_mode
    else: # Case 2: Stderr output with a vanilla Exception. Will ignore stdout (Python sends raised exceptions to stderr)
        out =  from_vanilla_stderr(stderr_blit)
    if out:
        return prepend_helpful_id(out, helpful_id) if helpful_id is not None else out

########################### Exception handling #################################

class VerboseError(Exception): # Verbose = Stack trace is in the message.
    pass

def raise_from_message(stack_message):
    raise VerboseError(_basic_txt(stack_message))
