# Plumbers deal with pipes that *should be* working but *aren't* working.
import time, traceback
from . import eye_term, colorful, deep_stack
from . import plumber_tools as ptools

try:
    interactive_error_mode # Debug tool.
except:
    interactive_error_mode = False

def default_prompts():
    # Default line end prompts and the needed input (str or function of the pipe).
    def _super_advanced_linux_shell(): # Newfangled menu where.
        # What button do you press to continue?
        import random
        out = []
        for i in range(256): # We are getting frusterated...
            chs = ['\033[1A','\033[1B','\033[1C','\033[1D','o','O','y','Y','\n']
            out.append(random.choice(chs))
        return ''.join(out)

    return {'Pending kernel upgrade':'\n\n\n','continue? [Y/n]':'Y',
            'Continue [yN]':'Y', 'To continue please press [ENTER]':'\n', # the '\n' actually presses enter twice b/c linefeeds are added.
            'continue connecting (yes/no)?':'Y',
            'Which services should be restarted?':_super_advanced_linux_shell()}

def loop_try(f, f_catch, msg, delay=4):
    # Waiting for something? Keep looping untill it succedes!
    # Useful for some shell/concurrency operations.
    if not callable(f):
        raise Exception(f'{f} which is type {type(f)} is not a callable')
    while True:
        try:
            return f()
        except Exception as e:
            if f_catch(e):
                if callable(msg):
                    msg = msg()
                if len(msg)>0:
                    print('Loop try ('+'\033[90m'+str(e)+'\033[0m'+') '+msg)
            else:
                raise e
        time.sleep(delay)

def with_timeout(tubo, f, timeout=6, message=None):
    # Uses f (f(pipe)=>bool) as an expect with a timeout.
    # Alternative to calling pipe.API with a timeout.
    x = {}
    if message is None:
        message = str(f)
    if f(tubo) or tubo.sure_of_EOF():
        x['reason'] = 'Detected '+str(message)
        return True
    if tubo.drought_len()>timeout:
        raise Exception('Timeout')
    return False

def manual_labor(plumber):
    while True:
        print('\n')
        x = input("\033[38;2;255;255;0;48;2;0;0;139mInput text to send to pipe (or quit or continue or .foo to query plumber.foo):\033[0m").strip()
        if len(x)==0:
            continue
        if x.lower()=='quit' or x.lower()=='quit()':
            return
        if x.lower()=='continue':
            return True
        try:
            if x[0]=='.':
                print(exec('plumber'+x))
            else:
                plumber.tubo.send(x)
        except Exception as e:
            print('Error:', e)

def maybe_interactive_error(plumber, e):
    # Lets the user manually input the error.
    print('Plumber encountered an error that should be debugged:')
    print('\n'.join(traceback.format_exception(None, e, e.__traceback__)))
    print(f"\033[38;2;255;255;0;48;2;0;0;139mError: {e}; entering interactive debug session.\033[0m")
    x = interactive_error_mode and manual_labor(plumber)
    if x:
        plumber.num_restarts = 0; plumber.rcounts_since_restart = {} # Reset this.
    else:
        stdout_blit = '\n'.join([tubo.blit(stdout=True, stderr=False) for tubo in plumber.tubo_history]) # Sometimes stderr can go into stdout, so a total blit is OK.
        sterr_blit = '\n'.join([tubo.blit(stdout=False, stderr=True) for tubo in plumber.tubo_history])
        msg0 = deep_stack.from_stream(stdout_blit, stderr_blit, compress_multible=True, helpful_id=plumber.tubo.machine_id)
        msg1 = deep_stack.from_exception(e)
        msg = msg1 if (not msg0) else deep_stack.concat(msg, msg1)
        deep_stack.raise_from_message(msg)

class Plumber():
    def __init__(self, tubo, packages, response_map, other_cmds, test_pairs, fn_override=None, dt=2.0):
        # test_pairs is a vector of [cmd, expected] pairs.
        if tubo.closed: # Make sure the pipe is open.
            tubo = tubo.remake()
        self.last_restart_time = -1e100 # Wait for it to restart!
        self.rcounts_since_restart = {}
        self.num_restarts = 0
        self.max_restarts = 3
        self.pipe_fix_fn = None

        #self.broken_record = 0 # Num times the last err appeared.
        #self.err_counts = {} # TODO: use.
        if test_pairs is None or len(test_pairs)==0:
            test_pairs = []
        if test_pairs == 'default':
            test_pairs = [['echo foo{bar,baz}', 'foobar foobaz']]
        if other_cmds is None:
            other_cmds = []
        self.dt = dt # Time-step when we need to wait, if the cmd returns faster we will respond faster.
        self.response_map = response_map
        self.fn_override = fn_override
        self.cmd_history = []
        self.tubo = tubo
        self.tubo_history = [tubo] # Always includes the current tubo.
        self.nsteps = 0

        self.remaining_packages = list(packages)
        self.remaining_misc_cmds = other_cmds
        self.remaining_tests = test_pairs

        self.completed_packages = []
        self.completed_misc_cmds = []
        self.completed_tests = []

        self.mode = 'green' # Finite state machine.

    def _sshe(self, e):
        # Throws e if not a recognized "SSH pipe malfunctioning" error.
        # If it is, will return the remedy.
        e_txt = str(e)+' '+str(type(e))
        fix_f = ptools.ssh_error(e_txt, self.cmd_history)
        if fix_f is None: # Only errors which can be thrown by ssh unreliabilities aren't thrown.
            maybe_interactive_error(self, e)
        return fix_f

    def _restart_if_too_loopy(self, k, not_pipe_related=None):
        # k indentifies the error or the prompt, etc.
        if k is None:
            return
        k = str(k)
        self.rcounts_since_restart[k] = self.rcounts_since_restart.get(k,0)+1
        n = self.rcounts_since_restart[k]
        slow = time.time() - self.last_restart_time > 90
        if (slow and n >= 3) or (not_pipe_related and n>8):
            if self.tubo.printouts:
                colorful.bprint('Installation may be stuck in a loop, restarting machine')
            self.restart_vm()

    def send_cmd(self, _cmd, add_to_packets=True):
        # Preferable than tubo.send since we store cmd_history and catch SSH errors.
        try:
            self.tubo.send(_cmd, add_to_packets=add_to_packets)
        except Exception as e:
            self.pipe_fix_fn = self._sshe(e)
            if self.tubo.printouts:
                colorful.bprint('Sending command failed b/c of:', str(e)+'; will run the remedy.\n')

    def restart_vm(self, raise_max_restart_error=True):
        # Preferable than using the tubo's restart fn because it resets rcounts_since_restart.
        if raise_max_restart_error and self.num_restarts==self.max_restarts:
            maybe_interactive_error(self, Exception('Max restarts exceeded, there appears to be an infinite loop that cant be broken.'))
        self.tubo.restart_fn()
        self.rcounts_since_restart = {}
        self.last_restart_time = time.time()
        self.num_restarts = self.num_restarts+1

    def blit_based_response(self):
        # Responses based on the blit alone, including error handling.
        # None means that there is no need to give a specific response.
        pkg = 'Nonepkg'
        if len(self.remaining_packages)>0:
            pkg = self.remaining_packages[0]
        txt = self.tubo.blit(False)
        #w = ptools.ssh_error(txt, self.cmd_history) # SSH errors are handled by catching exceptions instead.
        #if w is not None:
        #    return w
        x = ptools.apt_error(txt, pkg, self.cmd_history)
        if x is not None:
            return x
        y = ptools.pip_error(txt, pkg, self.cmd_history)
        if y is not None:
            return y
        z = ptools.get_prompt_response(txt, self.response_map) # Do this last in case there is a false positive that actually is an error.
        if z is not None:
            return z
        return None

    def short_wait(self):
        # Waits up to self.dt for the tubo, hoping that the tubo catches up.
        # Returns True for if the command finished or if a response was caused.
        sub_dt = 1.0/2048.0
        t0 = time.time(); t1 = t0+self.dt
        while time.time()<t1:
            if eye_term.standard_is_done(self.tubo.blit(include_history=False)) or self.blit_based_response():
                return True
            sub_dt = sub_dt*1.414
            ts = min(sub_dt, t1-time.time())
            if ts>0:
                time.sleep(ts)
            else:
                break
        if self.tubo.drought_len()>8:
            self.send_cmd('Y\necho waiting_for_shell', add_to_packets=False) # Breaking the ssh pipe will make this cause errors.
        return False

    def step_packages(self):
        # Returns True once installation and testing is completed.
        pkg = self.remaining_packages[0].strip(); ppair = pkg.split(' ')
        if ppair[0] == 'apt':
            _quer = ptools.apt_query; _err = ptools.apt_error; _ver = ptools.apt_verify
            _cmd = 'sudo apt install '+ppair[1]
        elif ppair[0] == 'pip' or ppair[0] == 'pip3':
            _quer = ptools.pip_query; _err = ptools.pip_error; _ver = ptools.pip_verify
            _cmd = 'pip3 install '+ppair[1]
        else:
            raise Exception(f'Package must be of the format "apt foo" or "pip bar" (not "{pkg}"); no other managers are currently supported.')

        if self.mode == 'green':
            self.send_cmd(_cmd)
            self.mode = 'blue'
        elif self.mode == 'blue':
            self.send_cmd(_quer(pkg))
            self.mode = 'orange'
        elif self.mode == 'orange':
            txt = self.tubo.blit(False)
            self.mode = 'green' # Done OR restart loop.
            v = _ver(pkg, txt)
            if v:
                return True
            safe_no_pipe = v is False # Exclude None.
            self._restart_if_too_loopy(pkg+'_'+_quer(pkg), not_pipe_related=safe_no_pipe) # safe_no_pipe means that the SSH pipe is safely up and running.

            if ppair[0]=='apt':
                self.send_cmd('sudo apt update\nudo apt upgrade')
            elif ppair[0] == 'pip' or ppair[0] == 'pip3':
                self.send_cmd('pip3 install --upgrade pip')
        else:
            self.mode = 'green'
        return False

    def step_tests(self):
        the_cmd, look_for_this = self.remaining_tests[0]
        if self.mode == 'green':
            self.send_cmd(the_cmd)
            self.mode = 'magenta'
        elif self.mode == 'magenta':
            self.mode = 'green' # Another reset loop if we fail.
            txt = self.tubo.blit(False)
            if type(look_for_this) is str or callable(look_for_this):
                look_for_this = [look_for_this]

            miss = False
            for look_for in look_for_this:
                if callable(look_for) and look_for(txt): # Function or string.
                    pass
                elif look_for in txt:
                    pass
                else:
                    miss = True
            if not miss:
                return True

            self._restart_if_too_loopy(the_cmd+'_'+'_'.join(look_for_this))
        else:
            self.mode = 'green'
        return False

    def step(self):
        if self.fn_override is not None: # For those occasional situations where complete control of everything is needed.
            if self.fn_override(self):
                return False
        try:
            self.tubo.ensure_init()
        except Exception as e:
            self.pipe_fix_fn = self._sshe(e)
            if self.tubo.printouts:
                colorful.bprint('Init the pipe failed b/c:', str(e), '. It may not be ready yet.\n')
        if self.pipe_fix_fn is not None:
            # Attempt to pipe_fix_fn, but the fn itself may cause an error (i.e. waiting for a vm to restart).
            try:
                tubo1 = self.pipe_fix_fn(self)
                if tubo1 is not self.tubo:
                    self.tubo_history.append(tubo1)
                    self.tubo = tubo1
                if type(self.tubo) is not eye_term.MessyPipe:
                    raise Exception('The remedy fn returned not a MessyPipe.')
                elif self.tubo.closed:
                    raise Exception('The remedy fn returned a closed MessyPipe.')
                if self.tubo.printouts:
                    colorful.bprint('Ran remedy to fix pipe\n')
                self.pipe_fix_fn = None
            except Exception as e:
                self.pipe_fix_fn = self._sshe(e)
                if self.tubo.printouts:
                    colorful.bprint('Running remedy failed b/c of:', str(e), '. This may be b/c the machine is rebooting, etc. Will run remedy for remedy.\n')

        if not self.short_wait():
            return False

        # Restart if we seem stuck in a loop:
        send_this = self.blit_based_response() # These can introject randomally (if i.e. the SSH pipe goes down and need a reboot).
        self._restart_if_too_loopy(send_this)

        if callable(send_this): # Sometimes the response is a function of the plumber, not a simple txt prompt.
            send_this(self)
        elif send_this is not None:
            self.send_cmd(send_this)
        elif len(self.remaining_packages)>0:
            if self.step_packages():
                self.completed_packages.append(self.remaining_packages[0])
                self.remaining_packages = self.remaining_packages[1:]
        elif len(self.remaining_misc_cmds)>0:
            # Commands that are ran after installation.
            self.send_cmd(self.remaining_misc_cmds[0])
            self.completed_misc_cmds.append(self.remaining_misc_cmds[0])
            self.remaining_misc_cmds = self.remaining_misc_cmds[1:]
        elif len(self.remaining_tests)>0:
            # Extra tests, beyond the specific verifications.
            if self.step_tests():
                self.completed_tests.append(self.remaining_tests[0])
                self.remaining_tests = self.remaining_tests[1:]
        else:
            self.nsteps += 1
            return True
        self.nsteps += 1
        return False

    def run(self):
        while not self.step():
            pass
        return self.tubo

    def blit_all(self):
        # Blits all the history from all the tubos.
        return ''.join([tubo.blit(include_history=True) for tubo in self.tubo_history])
