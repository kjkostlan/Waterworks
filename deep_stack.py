# Why can't a stack trace span across multible processes? Or even into the cloud?
# It can! Just remember to err_prop.pprint to make nice printouts.
# Filtering the error from the actual message is a pain, hopefully our fns work here!
import traceback
import re
from . import colorful, fittings, global_vars
tprint = global_vars.tprint

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

################################# String processing fns (stream concat) ################################

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

################## String processing fns (from pipe blits and exception objects) #######################

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

def from_cur_stack(): # Does not include the frame inside deep_stack.py
    lines = list(traceback.format_stack())
    lines = [l.replace('\r','').replace('\n',' ').replace('\t',' ') for l in lines]
    lines = [' '.join(l.split()) for l in lines]
    lines = lines[0:-1]
    return '\n'.join(lines)

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
    if type(stderr_blit) is bytes:
        stderr_blit = stderr_blit.decode('utf-8')
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
    if type(stdout_blit) is bytes: # Error reporting requires human-readable
        stdout_blit = stdout_blit.decode('utf-8')
    if type(stderr_blit) is bytes:
        stderr_blit = stderr_blit.decode('utf-8')
    total_blit = stdout_blit+'\n'+stderr_blit
    greeble_mode = from_greebled_stderr(total_blit, compress_multible=compress_multible)
    detect_vanilla_stdout_exceptions = True
    out = None
    if greeble_mode: # Case 1: A verbose error was raised or printed out; supposed to stderr but many people send errors to stdout instead:
        # This is a strong error report, so it is safer to suppress the "vanilla" case below
        out = greeble_mode
    else: # Case 2: Stderr output with a vanilla Exception. Will ignore stdout (Python sends raised exceptions to stderr)
        out = from_vanilla_stderr(total_blit if detect_vanilla_stdout_exceptions else stderr_blit)
    if out:
        return prepend_helpful_id(out, helpful_id) if helpful_id is not None else out
    elif 'raise VerboseError' in total_blit: # A bit of a DEBUG.
        print('WARNING: Verbose error in the stream not detected')

########################### Exception handling #################################

class VerboseError(Exception): # Verbose = Stack trace is in the message.
    pass

def raise_from_message(stack_message):
    raise VerboseError(_basic_txt(stack_message))

############################### Code evaluation ################################

def _issym(x): # Is x a (single) symbol?
    x = x.strip()
    if len(x)==0 or x=='pass':
        return False
    if '"' in x or "'" in x:
        return False
    if x.startswith('#'):
        return False
    for ch in '=+-/*%{}()[]\n ^@:':
        if ch in x:
            return False
    return True

def eval_better_report(code_line, *args, **kwargs):
    # Error reports that show what code was evaled.
    try:
        return eval(code_line, *args, **kwargs)
    except Exception as e:
        msg = f'Eval error in: "{code_line}": {repr(e)}'
        raise Exception(msg)

def exec_better_report(code_txt, *args, **kwargs):
    # Raises reports that show what code was executed.
    # In addition, if the last line is a symbol it will return the value.
    code_txt = code_txt.replace('\r\n','\n')
    try:
        exec(code_txt, *args, **kwargs)
    except Exception as e: # Raise modified errors that provide better information.
        report = the_old_way(e)
        code_lines = code_txt.split('\n')
        err_lines = report.split('\n')
        line_nums = [None for _ in range(len(err_lines))]
        for i in range(len(err_lines)):
            re_hit = re.search('line \d+', err_lines[i].replace('Line','line'))
            if re_hit is not None and 'File "<string>"' in err_lines[i]:
                _num = int(re_hit.group().replace('line','').strip())
                if _num < len(code_lines):
                    line_nums[i] = _num
        non_none_line_nums = list(filter(lambda x: x is not None, line_nums))
        # The stacktrace includes the error message:
        broken_code_msg = (f'exec() error running {len(code_lines)} lines of code, bad line: "'+code_lines[non_none_line_nums[-1]-1]+'"') if len(non_none_line_nums)>0 else 'exec() error running this code: "'+code_txt+'"'

        raise raise_from_message(broken_code_msg+': '+repr(e))
    lines = code_txt.strip().split('\n')
    if _issym(lines[-1]): # Will only run if the var exists, otherwise exec will have raised 'is not defined'.
        return eval(lines[-1], *args, **kwargs)
    else:
        return None

def exec_here(modulename, code_txt, delete_new_vars=False):
    # Runs code_txt in modulename. Returns any vars that are created (added to the __dict__)
    # (which means that it returns an empty dict for purely side-effect-free code).
    # Option to delete new vars to "clean up"
    #https://stackoverflow.com/questions/2220699/whats-the-difference-between-eval-exec-and-compile
    m = modulename if type(modulename) is type(sys) else sys.modules[modulename]

    vars0 = set(m.__dict__.keys())
    exec_better_report(code_txt, vars(m)) # Store events.
    new_vars = list(set(m.__dict__.keys())-vars0); new_vars.sort()

    out = {}
    for new_var in new_vars:
        out[new_var] = getattr(m, new_var)
        if delete_new_vars:
            delattr(m, new_var)
    return out

def exec_feed(in_place_array, line, *args, **kwargs):
    # Consumes code line-by-line and evals any code once the code becomes un-indented.
    # Will throw any errors raised by the code, both syntax and Exceptions.
    # Returns any "simple varaible" declarations such as a=b+c.
    if type(line) is bytes: # Extra protection, not sure if it is needed.
        line = line.decode('utf-8')
    line = line.replace('\r\n','\n')
    if line.endswith('\n'): # Trailing newlines will be added in the join statement.
        line = line[0:-1]
    unindented = len(line.lstrip()) == len(line) and len(line.strip())>0
    more_than_comment = not line.strip().startswith('#')
    code = '\n'.join(in_place_array)+'\n'+line; code = code.replace('\r\n','\n')
    even_triples = (len(code)-len(code.replace('"""','').replace("'''",'')))%6==0 # Can be broken with unuasual nested triple quotes.
    its_running_time = even_triples and more_than_comment and unindented
    debug_exec_feed = False
    if debug_exec_feed:
        print('EXEC FEED:', repr(line), even_triples, unindented, in_place_array, 'run?', its_running_time)
    if its_running_time:
        if debug_exec_feed:
            print('RUN THIS CODE:', repr(code))
        del in_place_array[:]
        return exec_better_report(code, *args, **kwargs)
    else:
        in_place_array.append(line)
