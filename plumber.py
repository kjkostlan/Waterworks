# Plumbers deal with pipes that *should be* working but *aren't* working.
import time, traceback
from . import eye_term, colorful, deep_stack
from . import plumb_packs

try:
    interactive_error_mode # Debug tool.
except:
    interactive_error_mode = False

def _last_line(txt):
    return txt.replace('\r\n','\n').split('\n')[-1]

def get_prompt_response(txt, response_map):
    # "Do you want to continue (Y/n); input AWS user name; etc"
    lline = _last_line(txt.strip()) # First try the last line, then try everything since the last cmd ran.
    # (A few false positive inputs is unlikely to cause trouble).
    for otxt in [lline, txt]:
        for k in response_map.keys():
            if k in otxt:
                if callable(response_map[k]):
                    return response_map[k](otxt)
                return response_map[k]

#def cmd_list_fixed_prompt(tubo, cmds, response_map, timeout=16): # LIkely deprecated fn.
#    TODO #get_prompt_response(txt, response_map)
#    x0 = tubo.blit()
#    def _check_line(_tubo, txt):
#        lline = _last_line(_tubo.blit(include_history=False))
#        return txt in lline
#    line_end_poll = lambda _tubo: looks_like_blanck_prompt(_last_line(_tubo.blit(include_history=False)))
#    f_polls = {'_vanilla':line_end_poll}
#
#    for k in response_map.keys():
#        f_polls[k] = lambda _tubo, txt=k: _check_line(_tubo, txt)
#    for cmd in cmds:
#        _out, _err, poll_info = tubo.API(cmd, f_polls, timeout=timeout)
#        while poll_info and poll_info != '_vanilla':
#            txt = response_map[poll_info]
#            if type(txt) is str:
#                _,_, poll_info = tubo.API(txt, f_polls, timeout=timeout)
#            else:
#                txt(tubo); break
#    x1 = tubo.blit(); x = x1[len(x0):]
#    return tubo, x

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
        stderr_blit = '\n'.join([tubo.blit(stdout=False, stderr=True) for tubo in plumber.tubo_history])
        msg0 = deep_stack.from_stream(stdout_blit, stderr_blit, compress_multible=True, helpful_id=plumber.tubo.machine_id)
        msg1 = deep_stack.from_exception(e)
        msg = msg1 if (not msg0) else deep_stack.concat(msg, msg1)
        deep_stack.raise_from_message(msg)

def compile_tasks(tasks):
    # Compiles tasks into seperate steps and tests.
    # They solve tasks in order. Each task can have:
       # 'packages': Packages to install (includes built-in tests to make sure the packages actually installed).
       # 'commands': Other cmds to run.
       # 'tests': Tests to run; if they fail the cmds are re-tried up to a few times.
    # This compiles to a list:
    #  ['command', the_cmd]
    #  ['test', test_cmd, test_results]
    #  ['checkpoint']
    #  If all tests fail.
    # Multible tests can be splayed out as well.
    more_responses = {}
    out = []
    if type(tasks) is dict:
        tasks = [tasks]
    for task in tasks:
        if len(set(task.keys())-set(['packages', 'commands', 'tests']))>0:
            raise Exception('Task must have only keys packages, commands, tests.')
        for p in task.get('packages', []):
            pkg = p.strip(); ppair = pkg.split(' ')
            if ppair[0] == 'apt':
                _quer = plumb_packs.apt_query; _err = plumb_packs.apt_error; _ver = plumb_packs.apt_verify
                _cmd = 'sudo apt install '+ppair[1]
                #No apt package "foo-bar", but there is a snap with that name.
                #Try "snap install foo-bar"
                more_responses[f'Try "snap install {ppair[1]}"'] = f'sudo snap install {ppair[1]} --classic' # Classic gives snap full access, which is OK since VMs can be torn down if anything breaks.
            elif ppair[0] == 'pip' or ppair[0] == 'pip3':
                _quer = plumb_packs.pip_query; _err = plumb_packs.pip_error; _ver = plumb_packs.pip_verify
                _cmd = 'pip3 install '+ppair[1]
            else:
                raise Exception(f'Package must be of the format "apt foo" or "pip3 bar" (not "{pkg}"); no other managers are currently supported.')
            out.append(['command', _cmd])
            if (ppair[0] != 'pip' and ppair[0] != 'pip3') or ('_' not in pkg and '-' not in pkg): # Not sure how to handle pip and _.
                out.append(['test', _quer(pkg), lambda txt: _ver(pkg, txt)])
        for cmd in task.get('commands', []):
            out.append(['command', cmd])
        for t in task.get('tests',[]):
            out.append(['test', t[0], t[1]])
    return out, more_responses

def bash_awake_test():
    TODO

def python_awake_test():
    TODO

class Plumber():
    # Plumbers are designed to perform *and verify* complex commands that require lots of dealing with mess.
    def __init__(self, tubo, tasks, response_map, fn_override=None, dt=2.0):
        # test_pairs is a vector of [cmd, expected] pairs.
        if tubo.closed: # Make sure the pipe is open.
            tubo = tubo.remake()
        self.last_restart_time = -1e100 # Wait for it to restart!
        self.rcounts_since_restart = {}
        self.num_restarts = 0
        self.max_restarts = 3
        self.pipe_fix_fn = None

        #self.err_counts = {} # Useful?
        self.dt = dt # Time-step when we need to wait, if the cmd returns faster we will respond faster.
        self.fn_override = fn_override
        self.cmd_history = []
        self.tubo = tubo
        self.tubo_history = [tubo] # Always includes the current tubo.
        self.nsteps = 0
        self.task_packet_frusteration = 0

        self.remaining_tasks, more_responses = compile_tasks(tasks)
        self.response_map = {**more_responses, **response_map}
        self.rem_task_ix = 0
        self.completed_tasks = []

        self.mode = 'green' # Finite state machine.

    def _sshe(self, e):
        # Throws e if not a recognized "SSH pipe malfunctioning" error.
        # If it is, will return the remedy.
        e_txt = str(e)+' '+str(type(e))
        fix_f = plumb_packs.ssh_error(e_txt, self.cmd_history)
        if fix_f is None: # Only errors which can be thrown by ssh unreliabilities aren't thrown.
            maybe_interactive_error(self, e)
        return fix_f

    def send_cmd(self, _cmd, add_to_packets=True):
        # Preferable than tubo.send since we store cmd_history and catch SSH errors.
        try:
            self.tubo.send(_cmd, add_to_packets=add_to_packets)
        except Exception as e:
            self.pipe_fix_fn = self._sshe(e)
            if self.tubo.printouts:
                colorful.bprint('Sending command failed b/c of:', str(e)+'; will run the remedy.\n')

    def restart_vm(self, penalize=True):
        # Preferable than using the tubo's restart fn because it resets rcounts_since_restart.
        if penalize and self.num_restarts==self.max_restarts:
            maybe_interactive_error(self, Exception('Max restarts exceeded, there appears to be an infinite loop that cant be broken.'))
        self.tubo.restart_fn()
        self.rcounts_since_restart = {}
        self.last_restart_time = time.time()
        if penalize:
            self.num_restarts = self.num_restarts+1

    def _restart_if_too_loopy(self, not_pipe_related=None):
        n = self.task_packet_frusteration
        slow = time.time() - self.last_restart_time > 90
        if (slow and n >= 3) or (not_pipe_related and n>8):
            if self.tubo.printouts:
                colorful.bprint('Installation may be stuck in a loop, restarting machine')
            self.restart_vm()
            self.task_packet_frusteration = 0

    def blit_based_response(self):
        # Responses based on the blit alone, including error handling.
        # None means that there is no need to give a specific response.
        txt = self.tubo.blit(False)
        z = get_prompt_response(txt, self.response_map) # Do this last in case there is a false positive that actually is an error.
        if z is not None:
            return z
        return None

    def blit_all(self):
        # Blits across multible tubos.
        return ''.join([tubo.blit(include_history=True) for tubo in self.tubo_history])

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

    def step_tests(self, the_cmd, look_for_this):
        # False means failed, None means in progress.
        if self.mode == 'green':
            self.send_cmd(the_cmd)
            self.mode = 'magenta'
            return None
        elif self.mode == 'magenta':
            self.mode = 'green' # Another reset loop if we fail.
            txt = self.tubo.blit(False)
            if type(look_for_this) is str or callable(look_for_this):
                look_for_this = [look_for_this]

            miss = False
            for look_for in look_for_this:
                if callable(look_for):
                    if look_for(txt):
                        continue
                elif look_for in txt:
                    continue
                miss = True
            if not miss:
                return True
            return False
        else:
            self.mode = 'green'
            return None
        return None

    def step(self):
        if 'Which services should be restarted?' in self.tubo.blit(include_history=False):
            # This menu appears during installation and is *very annoying*, so it makes sense to restart the vm.
            colorful.bprint('The "Which services should be restarted?" box really, really, REALLY wants to be a GUI. So why is it hanging out in the CLI? Either way its restart VM time.')
            time.sleep(1.5)
            self.restart_vm(penalize=False) # Do not count it toward the max restarts.

        if self.fn_override is not None: # For those occasional situations where complete control of everything is needed.
            if self.fn_override(self):
                return False
        t0 = time.time()
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
            # Random sleep time:
            t1 = time.time()
            import random
            sleep_time = (0.1+random.random()*random.random())*(t1-t0)
            if self.tubo.printouts and sleep_time>0.25:
                colorful.bprint('Random pipe fix sleep (seems to help break out of some not-yet-ready-after-fix loops):', sleep_time)
            time.sleep(sleep_time)

        if not self.short_wait():
            return False

        # Restart if we seem stuck in a loop:
        send_this = self.blit_based_response() # These can introject randomally (if i.e. the SSH pipe goes down and need a reboot).
        self._restart_if_too_loopy()

        if callable(send_this): # Sometimes the response is a function of the plumber, not a simple txt prompt.
            send_this(self)
            self.nsteps += 1
            return False
        elif send_this is not None:
            self.send_cmd(send_this)
            self.nsteps += 1
            return False
        if len(self.remaining_tasks)<=self.rem_task_ix: # All done!
            self.completed_tasks.extend(self.remaining_tasks)
            self.remaining_tasks = []
            return True # We are done with all the tasks and tests thereof.

        tsk = self.remaining_tasks[self.rem_task_ix]
        ty = tsk[0].lower()
        if ty == 'checkpoint':
            self.completed_tasks.extend(self.remaining_tasks[0:self.rem_task_ix])
            self.remaining_tasks = self.remaining_tasks[self.rem_task_ix+1:]
            self.rem_task_ix = 0
        elif ty == 'command' or ty == 'cmd':
            self.send_cmd(tsk[1])
            self.rem_task_ix = self.rem_task_ix+1
            self.nsteps += 1
        elif ty == 'test':
            tresult = self.step_tests(tsk[1], tsk[2])
            if tresult:
                self.rem_task_ix = self.rem_task_ix+1
            elif tresult is False: # None isn't a fail, but False is.
                colorful.bprint('Test for this task failed, retrying task.')
                self.task_packet_frusteration += 1
                self.rem_task_ix = 0
                if self.task_packet_frusteration>16:
                    raise Exception('Cant get the test working.')
            self.nsteps += 1
        else:
            raise Exception('Unknown (compiled) task type: '+ty)
        return False

    def run(self):
        while not self.step():
            pass
        return self.tubo
