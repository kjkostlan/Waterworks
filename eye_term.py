# Shell is centered around a human seeing things, and it feeds streams.
# The human often has to respond mid stream with "y" to continue, for example, or timeout if things are taking too long.
# Programming languages, on the other hand, are sequential at thier core (often with tools to multitask).
# *Of course* the 2023+ solution is AI, but this one should be fairly simple.
#https://www.linode.com/docs/guides/use-paramiko-python-to-ssh-into-a-server/
#https://hackersandslackers.com/automate-ssh-scp-python-paramiko/
import time, re, os, sys, threading
import proj
from . import fittings

_glbals = proj.global_get('eye_term_globals', {'log_pipes':[]})
log_pipes = _glbals['log_pipes']

try:
    rm_ctrl_chars_default
except:
    rm_ctrl_chars_default = False

class Sbuild:
    # String builder class which avoids O(n^2). Also works for bytes array.
    # Python has an unreliable anti-O(n^2) for string cat, this is more robust.
    def __init__(self, is_bytes):
        self.vals = []
        self.is_bytes = is_bytes

    def add(self, x):
        self.vals.append(x)

    def val(self):
        if self.is_bytes:
            out = b''.join(self.vals)
            self.vals = [out.copy()]
            return out
        else:
            out = ''.join(self.vals)
            self.vals = [out]
            return out

######################Small functions######################################

def bprint(*txt):
    # Use our own color to differentiate from the data dump that is the ssh/bash stream.
    txt = ' '.join([str(t) for t in txt])
    print('\033[94m'+txt+'\033[0m', end='')

def non_empty_lines(txt):
    txt = txt.replace('\r\n','\n').strip()
    return list(filter(lambda x: len(x)>0, txt.split('\n')))

def quoteless(the_path):
    # Quotes prevent the nice convienent ~ and * syntax of directories.
    # So escaping spaces helps.
    return the_path.replace('\\','/').replace(' ',' \\')

def remove_control_chars(txt, label=True, rm_bash_escapes=False):
    # They have a powerful compression effect that can prevent newlines from ever bieng printed again.
    for cix in list(range(32))+[127]:
        if cix not in [9, 10]: # [9, 10] = [\t, \n]
            if label:
                txt = txt.replace(chr(cix),'֍'+hex(cix)+'֍')
            else:
                txt = txt.replace(chr(cix),'')
    if rm_bash_escapes:
        txt = txt.replace('[', '֍') # Removes bash control chars.
    return txt

def termstr(cmds, _out, _err):
    # Prints it in a format that is easier to read.
    pieces = []
    for i in range(len(_out)):
        c = cmds[i] if type(cmds[i]) is str else cmds[i][0]
        pieces.append('→'+c+'←')
        pieces.append(_out[i])
        if _err is not None:
            pieces.append(_err[i])
    txt = '\n'.join(pieces)
    txt = txt.replace('\r\n','\n')
    txt = txt.replace('\n\n','\n')
    return txt

####################Tier 1 Pipe output processing fns###########################

def looks_like_blanck_prompt(line):
    # When most cmds finish they return to foo/bar/baz$, or xyz>, etc.
    # This determines whether the line is one of these.
    line = line.strip()
    for ending in ['$', '>', '#']:
        if line.endswith(ending):
            return True
    return False

def txt_poll(txt, f_polls):
    # Polls txt for a particular output, return the key in f_polls, if any.
    for k in f_polls.keys():
        if f_polls[k](txt):
            return k

def last_line(txt):
    # Last non-empty line (empty if no such line exists).
    lines = non_empty_lines(txt)
    if len(lines)==0:
        return ''
    return lines[-1]

def standard_is_done(txt):
    # A default works-most-of-the-time pipe dryness detector.
    # Will undergo a lot of tweaks that try to extract the spatial information.
    #lines = txt.replace('\r\n','\n').split('\n')
    #if len(txt)>0 and len(lines[-1].strip()) == 0:
    #    return True
    lines = txt.strip().split('\n')
    return len(txt.strip())>0 and looks_like_blanck_prompt(lines[-1])

################################Pipe mutation fns###############################

class ThreadSafeList(): # TODO: deprecated.
    # Fill in a read loop on another thread and then use pop_all()
    # https://superfastpython.com/thread-safe-list/
    def __init__(self):
        self._list = list()
        self._lock = threading.Lock()
    def append(self, value):
        with self._lock:
            self._list.append(value)
    def pop(self):
        with self._lock:
            return self._list.pop()
    def get(self, index):
        with self._lock:
            return self._list[index]
    def length(self):
        with self._lock:
            return len(self._list)
    def pop_all(self):
        with self._lock:
            out = self._list.copy()
            self._list = []
            return out

def pipe_loop(tubo, is_err): # For ever watching... untill the thread gets closed.
    dt0 = 0.001
    dt1 = 2.0
    dt = dt0
    while not tubo.closed:
        try:
            while tubo.update(is_err)>0:
                dt = dt0
        except Exception as e:
            tubo.loop_err = e # Gets thrown during the blit stage.
        time.sleep(dt)
        dt = min(dt1, dt*1.414)

################################Which-pipe specific fns###############################

def _init_terminal(self):
    #https://stackoverflow.com/questions/375427/a-non-blocking-read-on-a-subprocess-pipe-in-python/4896288#4896288
    #https://stackoverflow.com/questions/156360/get-all-items-from-thread-queue
    import subprocess, pty
    terminal = 'cmd' if os.name=='nt' else 'bash' # Windows vs non-windows.
    posix_mode = 'posix' in sys.builtin_module_names
    if not proc_args:
        procX = terminal
    elif type(proc_args) is str:
        procX = proc_args
    elif type(proc_args) is list or type(proc_args) is tuple:
        procX = ' '.join(proc_args)
    elif type(proc_args) is dict:
        procX = ' '.join([k+' '+proc_args[k] for k in proc_args.keys()])
    else:
        raise Exception('For the shell, the type of proc args must be str, list, or dict.')
    def _read_loop(the_pipe, safe_list):
        while True:
            safe_list.append(ord(the_pipe.read(1)) if self.binary_mode else fittings.utf8_one_char(the_pipe.read))

    use_pty = False # Why does pexpect work so much better than vanilla? Is this the secret sauce? But said sauce is hard to use, thus it's False for now.
    #https://gist.github.com/thomasballinger/7979808
    if use_pty:
        peacock, tail = pty.openpty(); stdin=tail
        pty_input = os.fdopen(peacock, 'w')
    else:
        pty_input = None
        stdin = subprocess.PIPE

    p = subprocess.Popen(procX, stdin=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=posix_mode) # shell=True has no effect?

    def _stdouterr_f(is_err):
        p_std = p.stderr if is_err else p.stdout
        p_std.flush()
        if self.binary_mode:
            return p_std.read(1)
        else:
            return fittings.utf8_one_char(p_std.read)

    self._close = lambda self: p.terminate()

    def _send(x, include_newline=True):
        x = self._to_input(x, include_newline=include_newline)
        if use_pty:
            if type(x) is bytes:
                x = x.decode('UTF-8')
            pty_input.write(x)
            pty_input.flush()
        else:
            if type(x) is str: # Bash subprocesses always take binary bytes?
                x = x.encode()
            p.stdin.write(x)
            p.stdin.flush()
    self.send_f = _send

    self.stdout_f = lambda: _stdouterr_f(False)
    self.stderr_f = lambda: _stdouterr_f(True)

def _init_paramiko(self):
    # Paramiko terminals.
    #https://unix.stackexchange.com/questions/70895/output-of-command-not-in-stderr-nor-stdout?rq=1
    #https://stackoverflow.com/questions/55762006/what-is-the-difference-between-exec-command-and-send-with-invoke-shell-on-para
    #https://stackoverflow.com/questions/40451767/paramiko-recv-ready-returns-false-values
    #https://gist.github.com/kdheepak/c18f030494fea16ffd92d95c93a6d40d
    import paramiko
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy()) # Being permissive is quite a bit easier...
    #if not proc_args:
    #    proc_args['banner_timeout'] = 32 # Does this help?
    client.connect(**proc_args) #password=passphrase) #proc_args['hostname'],
    use_keepalive=True
    if use_keepalive: #https://stackoverflow.com/questions/5402919/prevent-sftp-ssh-session-timeout-with-paramiko
        transport = client.get_transport()
        transport.set_keepalive(30)
    channel = client.invoke_shell()
    self._streams = channel

    def _send(x, include_newline=True):
        channel.send(self._to_input(x, include_newline=include_newline))
    self.send_f = _send
    def _get_elements(ready_fn, read_fn):
        out = []
        while ready_fn():
            out.append(ord(read_fn(1)) if self.binary_mode else fittings.utf8_one_char(read_fn))
        return ''.join(out).encode() if self.binary_mode else ''.join(out)
    self.stdout_f = lambda: _get_elements(channel.recv_ready, channel.recv)
    self.stderr_f = lambda: _get_elements(channel.recv_stderr_ready, channel.recv_stderr)

    #chan = client.get_transport().open_session() #TODO: what does this do and is it needed?
    self._close = lambda self: client.close()

def _init_core(self, proc_type, proc_args=None, binary_mode=False):
    self.send_f = None # Send strings OR bytes.
    self.stdout_f = None # Returns an empty bytes if there is nothing to get.
    self.stderr_f = None
    self._streams = None # Mainly used for debugging.
    self.color = 'linux'
    self.remove_control_chars = rm_ctrl_chars_default # **Only on printing** Messier but should prevent terminal upsets.
    self._close = None
    self.loop_threads =[threading.Thread(target=pipe_loop, args=[self, False]), threading.Thread(target=pipe_loop, args=[self, True])]

    if proc_type == 'shell':
        _init_terminal(self)
    elif proc_type == 'ssh' or proc_type == 'paramiko':
        _init_paramiko(self)
    else: # TODO: more kinds of pipes.
        raise Exception('proc_type must be "shell" or "ssh"')

    if self.stdout_f is None or self.stderr_f is None:
        raise Exception('stdout_f and/or stderr_f not set.')

    for lot in self.loop_threads:
        lot.daemon = True; lot.start() # This must only happen when the setup is complete.
    self.is_init = True

    tweak_prompt = True
    if proc_type=='shell' and tweak_prompt:
        #https://ss64.com/bash/syntax-prompt.html
        for var in ['PS0','PS1','PS2','PS3','PS4','PROMPT_COMMAND']:
            txt = f"export {var}='$'"
            self.send(txt, include_newline=True, suppress_input_prints=False, add_to_packets=True)

################################The core MessyPipe##############################

class MessyPipe:
    # The low-level basic messy pipe object with a way to get [output, error] as a string.
    def _to_output(self, x):
        if type(x) is bytes and not self.binary_mode:
            x = bytes.decode('utf-8')
        elif type(x) is str and self.binary_mode:
            x = x.encode()
        return x

    def _to_input(self, x, include_newline=True):
        x = self._to_output(x)
        if include_newline and not self.binary_mode:
            x = x+'\n'
        return x

    def ensure_init(self):
        # Will raise some sort of paramiko Exception if the pipe isn't ready yet.
        if self.is_init:
            return
        _init_core(self, proc_type=self.proc_type, proc_args=self.proc_args, binary_mode=self.binary_mode)

    def __init__(self, proc_type, proc_args=None, printouts=True, binary_mode=False):
        # Defers creation of the pipe; creation can cause errors if done before i.e. a reboot is complete.
        # the plumber class deals with such erros but needs a MessyPipe object.
        self.lock = threading.Lock()
        self.printouts = printouts
        self.is_init = False
        self.closed = False
        self.binary_mode = binary_mode
        self.proc_type = proc_type
        self.proc_args = proc_args
        self.loop_err = None
        self.packets = [[b'' if binary_mode else '', Sbuild(self.binary_mode), Sbuild(self.binary_mode), time.time(), time.time()]] # Each command: [cmd, out, err, time0, time1]

        self.machine_id = None # Optional user data.
        self.restart_fn = None # Optional fn allowing any server to be restarted.

    def blit(self, include_history=True):
        # Mash the output and error together.
        self.assert_no_loop_err()
        with self.lock:
            if include_history:
                if self.binary_mode:
                    out = b''
                    for pak in self.packets:
                        out.extend(pak[1].val()+pak[2].val())
                    return out
                else:
                    return ''.join([pk[1].val()+pk[2].val() for pk in self.packets])
            else:
                return self.packets[-1][1].val()+self.packets[-1][2].val()

    def update(self, is_std_err): # Returns the len of the data.
        def _boring_txt(txt):
            txt = txt.replace('\r\n','\n')
            if self.remove_control_chars:
                txt = remove_control_chars(txt, True)
            return txt
        _outerr = self.stderr_f() if is_std_err else self.stdout_f()
        if self.printouts:
            if len(_outerr)>0:
                txt = _boring_txt(_outerr)
                with self.lock: # Does this prevent interleaving out and err prints?
                    print(txt, end='') # Newlines should be contained within the feed so there is no need to print them directly.
        with self.lock:
            if len(_outerr)>0:
                ix = 2 if is_std_err else 1
                self.packets[-1][ix].add(_outerr)
                self.packets[-1][4] = time.time() # Either stdout or stderr.
            return len(_outerr)

    def drought_len(self):
        # How long since neither stdout nor stderr spoke to us.
        return time.time() - self.packets[-1][4]

    def send(self, txt, include_newline=True, suppress_input_prints=False, add_to_packets=True):
        # The non-blocking operation.
        #https://stackoverflow.com/questions/6203653/how-do-you-execute-multiple-commands-in-a-single-session-in-paramiko-python
        self.ensure_init()
        if type(txt) is not str and type(txt) is not bytes:
            raise Exception(f'The input must be a string or bytes object, not a {type(txt)}')
        if self.closed:
            raise Exception('The pipe has been closed and cannot accept commands; use pipe.remake() to get a new, open pipe.')
        if self.printouts and not suppress_input_prints:
            if self.color=='linux':
                #https://stackoverflow.com/questions/287871/how-do-i-print-colored-text-to-the-terminal
                if add_to_packets:
                    print('\x1b[0;33;40m'+'→'+'\x1b[6;30;42m'+txt+'\x1b[0;33;40m'+'←'+'\x1b[0m')
                else:
                    print('\x1b[0;33;40m'+'→'+'\033[97;104m'+txt+'\x1b[0;33;40m'+'←'+'\x1b[0m')
            else:
                print('→'+txt+'←')
        if add_to_packets:
            self.packets.append([txt, Sbuild(self.binary_mode), Sbuild(self.binary_mode), time.time(), time.time()])
        self.send_f(txt, include_newline=include_newline)

    def API(self, txt, f_polls=None, timeout=8.0):
        # Behaves like an API, returning out, err, and information about which polling fn suceeded.
        # Includes a timeout setting if none of the polling functions work properly.
        use_echo = True
        if self.binary_mode:
            use_echo = False
        ky = 'eye_term_done_mark' # Shell prompts don't seem to have the $ so we must get an echo back instead.
        self.send(txt)
        if f_polls is None:
            f_polls = {'default':standard_is_done}
        elif callable(f_polls):
            f_polls = {'user':f_polls}
        elif type(f_polls) is list or type(f_polls) is tuple:
            f_polls = dict(zip(range(len(f_polls)), f_polls))

        which_poll=None
        while which_poll is None:
            blit_txt = self.blit(include_history=False)
            for k in f_polls.keys():
                if f_polls[k](blit_txt):
                    which_poll=k # Break out of the loop
                    break
            if use_echo and self.proc_type == 'shell' and blit_txt.endswith('\n'):
                if ky in blit_txt:
                    which_poll = 'default'
                else:
                    self.send('echo '+ky, add_to_packets=False)
            time.sleep(0.1)
            td = self.drought_len()
            if self.printouts:
                if td>min(6, 0.75*timeout):
                    if self.color=='linux':
                        # Colors: https://misc.flogisoft.com/bash/tip_colors_and_formatting
                        print('\x1b[0;33;40m'+f'{td} seconds has elapsed with dry pipes.'+'\x1b[0m')
                    else:
                        print(f'{td} seconds has elapsed with dry pipes.')
            if timeout is not None and td>timeout:
                raise Exception(f'API timeout on cmd {txt}; ')

        self.assert_no_loop_err()
        def _clean_ky(txt):
            if not use_echo:
                return txt
            if txt.endswith(ky):
                txt = txt[0:len(txt)-len(ky)]
            if txt.endswith(ky+'\n'):
                txt = txt[0:len(txt)-len(ky+'\n')]
            return txt
        return _clean_ky(self.packets[-1][1].val()), _clean_ky(self.packets[-1][2].val()), which_poll

    def assert_no_loop_err(self):
        if self.loop_err:
            print('Polling loop exception:')
            raise self.loop_err

    def multi_API(self, cmds, f_polls=None, timeout=8):
        # For simplier series of commands.
        # Returns output, errors. f_poll can be a list of fns 1:1 with cmds.
        outputs = []; errs = []; polls_info = []
        self.empty()
        for i in range(len(cmds)):
            out, err, poll_info = self.API(cmds[i], f_polls=f_polls, timeout=timeout)
            outputs.append(out)
            errs.append(err)
            polls_info.append(poll_info)
        return outputs, errs, polls_info

    def close(self):
        if not self.is_init:
            raise Exception('Attempt to close a pipe which has not been initalized.')
        log_pipes.append(self)
        self._close(self)
        self.closed = True

    def sure_of_EOF(self):
        # Only if we are sure! Not all that useful since it isn't often triggered.
            #https://stackoverflow.com/questions/35266753/paramiko-python-module-hangs-at-stdout-read
        #    ended_list = [False, False] # TODO: fix this.
        #    return len(list(filter(lambda x: x, ended_list)))==len(ended_list)
        return False # TODO: maybe once in a while there are pipes that are provably closable.

    def remake(self):
        # If closed, opens a new pipe to the same settings and returns it.
        # Recommended to put into a loop which may i.e. restart vms or otherwise debug things.
        if self.is_init and not self.closed:
            self.close()
        out = MessyPipe(proc_type=self.proc_type, proc_args=self.proc_args, printouts=self.printouts, binary_mode=self.binary_mode)
        out.machine_id = self.machine_id
        out.restart_fn = self.restart_fn
        return out
