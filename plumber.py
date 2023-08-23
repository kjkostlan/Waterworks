# Plumbers deal with pipes that *should be* working but *aren't* working.
import time, traceback
from . import eye_term, colorful, deep_stack
from . import plumb_packs

def compile_tasks(tasks, common_response_map, include_apt_init):
    # Compiles tasks into nodes, it is easier to send a list of tasks.
    # Tasks can have:
    #    'packages': Packages to install such as "pip numpy". Will be converted into nodes and tests.
    #    'commands': Generic commands to run.
    #    'lambda': f(plumber) => string, None, or True; can use plumber.lambda_state
                   # string = send the string.
                   # None = wait.
                   # True = we are done.
                   # Generic Turing-complete escape hatch so it runs every step.
    #    'response_map': Response to substring of last line of tasks. Combines with a global response_map option.
    #    'tests': [cmd, response] pairs in addition to package installation tests; if any fail the whole task is retried.
    if type(tasks) is dict: # Assume this means there is a single task
        tasks = [tasks]

    if include_apt_init:
        t0 = {'commands':['sudo apt update\nsudo apt upgrade']}#\n(restart)'}
        tasks = [t0]+tasks

    nodes = {}
    node_begin_ends = [] # [begin, end0, end1, ...]. In order, used to compile "->" into names.
    for task in tasks:
        add_to_ea_node = {'response_map':{**common_response_map, **task.get('response_map',{})}}
        if 'lambda' in task:
            add_to_ea_node['lambda'] = task['lambda']
        unrecognized_kys = set(task.keys())-set(['packages', 'commands', 'tests', 'lambda'])
        if len(unrecognized_kys)>0:
            raise Exception('Task must have only keys packages, commands, tests, lambda, not: '+str(unrecognized_kys))
        node_begin = None
        for p in task.get('packages', []):
            nodes1, n0 = plumb_packs.compile_package_cmd(p)
            if node_begin is None:
                node_begin = n0
            # This bit of code "uncaps" the ends so it can be glued into a larger pipeline:
            pk_ends = list(filter(lambda nd: nodes1[nd].get('end_node', False), nodes1.keys()))
            if len(pk_ends)==0:
                raise Exception('No end_node found for the compiled package command.')
            for ni in pk_ends:
                del nodes1[ni]['end_node']
                nodes1[ni]['jump'] = '->'
            node_begin_ends.append([n0]+pk_ends)
            for nk in nodes1:
                nodes1[nk].update(add_to_ea_node)
            nodes.update(nodes1)
        commands = task.get('commands', [])
        if type(commands) is str:
            commands = [commands]
        for cmd in commands:
            node_name = 'cmd/'+cmd
            if node_begin is None:
                node_begin = node_name
            nd = {'cmd':cmd, 'jump':'->'}
            nd.update(add_to_ea_node)
            nodes[node_name] = nd
            node_begin_ends.append([node_name, node_name])
        for t in task.get('tests',[]):
            node_name = 'test/'+t[0]
            if node_begin is None:
                raise Exception('Tests can only be used if there is at least one package or command.')
            nodes[node_name] = {'jump_branch':[t[0], {t[1]:'->', False:node_begin}]}
            nodes[node_name].update(add_to_ea_node)

    for i in range(len(node_begin_ends)-1): # Link endings up to beginnings by replacing '->' keys.
        begin1 = node_begin_ends[i+1][0]
        for e in node_begin_ends[i][1:]:
            nd = nodes[e]
            if 'jump' not in nd and 'jump_branch' not in nd: # All nodes default to jump.
                nd['jump'] = begin1
            if 'jump' in nd and nd['jump'] == '->':
                nd['jump'] = begin1
            if 'jump_branch' in nd:
                for ky in nd['jump_branch'][1].keys():
                    if nd['jump_branch'][1][ky] == '->':
                        nd['jump_branch'][1][ky] = begin1

    for ky in node_begin_ends[-1][1:]:
        nodes[ky]['end_node'] = True

    return nodes, node_begin_ends[0][0]

try:
    interactive_error_mode # Debug tool.
except:
    interactive_error_mode = False

def get_prompt_response(txt, response_map):
    # "Do you want to continue (Y/n); input AWS user name; etc"
    def _last_line(txt):
        return txt.replace('\r\n','\n').split('\n')[-1]
    lline = _last_line(txt.strip()) # First try the last line, then try everything since the last cmd ran.
    # (A few false positive inputs is unlikely to cause trouble).
    for otxt in [lline, txt]:
        for k in response_map.keys():
            if (callable(k) and k(otxt)) or (k in otxt or (k is True and otxt == txt)):
                x = response_map[k](otxt) if callable(response_map[k]) else response_map[k]
                if x:
                    return x

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

def bash_awake_test():
    TODO

def python_awake_test():
    TODO

class Plumber():
    # Plumbers are designed to perform *and verify* complex commands that require lots of dealing with mess.
    def __init__(self, tubo, tasks, common_response_map, dt=2.0, include_apt_init=True):
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
        self.cmd_history = []
        self.tubo = tubo
        self.tubo_history = [tubo] # Always includes the current tubo.
        self.nsteps = 0
        self.steps_this_node = 0

        self.nodes, self.current_node = compile_tasks(tasks, common_response_map, include_apt_init)
        debug_print_nodes = False
        if debug_print_nodes:
            print('<<<Nodes:', self.nodes, '>>>', '<<<Tasks:', self.nodes, '>>>')

        self.lambda_state = None
        self.node_state = 0 # For jump_branch nodes.
        self.node_visit_counts = {} # Too many revisits is a sign of a possible infinite loop.

    def _sshe(self, e):
        # Throws e if not a recognized "SSH pipe malfunctioning" error.
        # If it is, will return the remedy.
        e_txt = str(e)+' '+str(type(e))
        fix_f = plumb_packs.ssh_error(e_txt, self.cmd_history)
        if fix_f is None: # Only errors which can be thrown by ssh unreliabilities aren't thrown.
            maybe_interactive_error(self, e)
        return fix_f

    def restart_vm(self, penalize=True):
        # Preferable than using the tubo's restart fn because it resets rcounts_since_restart.
        if penalize and self.num_restarts==self.max_restarts:
            maybe_interactive_error(self, Exception('Max restarts exceeded, there appears to be an infinite loop that cant be broken.'))
        self.tubo.restart_fn()
        self.rcounts_since_restart = {}
        self.last_restart_time = time.time()
        if penalize:
            self.num_restarts = self.num_restarts+1

    def send_cmd(self, _cmd, add_to_packets=True):
        # Preferable than tubo.send since we store cmd_history and catch SSH errors.
        _cmd1 = _cmd.replace('(restart)','').strip()
        if _cmd =='\n':
            _cmd1 = _cmd

        if len(_cmd1)>0:
            try:
                self.tubo.send(_cmd1, add_to_packets=add_to_packets)
            except Exception as e:
                self.pipe_fix_fn = self._sshe(e)
                if self.tubo.printouts:
                    colorful.bprint('Sending command failed b/c of:', str(e)+'; will run the remedy.\n')
        if '(restart)' in _cmd: # Restart the virtual machine.
            self.restart_vm(penalize=False)

    def _restart_if_too_loopy(self, not_pipe_related=None):
        n = self.node_visit_counts.get(self.current_node, 0)
        slow = time.time() - self.last_restart_time > 90
        if (slow and n >= 4) or (not_pipe_related and n>8):
            if self.tubo.printouts:
                colorful.bprint('Installation may be stuck in a loop, restarting machine')
            self.restart_vm()
            self.task_packet_frusteration = 0

    def blit_based_response(self):
        # Responses based on the blit alone, including error handling.
        # None means that there is no need to give a specific response.
        txt = self.tubo.blit(False)
        z = get_prompt_response(txt, self.nodes[self.current_node].get('response_map',{})) # Do this last in case there is a false positive that actually is an error.
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

    def set_node(self, node_name):
        if node_name == '->':
            raise Exception('The destination node_name is "->" which is a placeholder and (bug) hasnt been replaced by an actual node name.')
        self.current_node = node_name
        self.steps_this_node = 0
        self.node_visit_counts[node_name] = self.node_visit_counts.get(node_name, 0)+1
        self.lambda_state = None
        self.node_state = 0
        if self.node_visit_counts[node_name]>6:
            raise Exception('Likely stuck in a loop going between nodes, current node = ', node_name)

    def step(self):
        if self.steps_this_node>8: # Steps does not include short_wait if we do nothing.
            raise Exception('Stuck in a single node most likely node name = ', self.current_node)

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
            if self.tubo.drought_len()>96:
                colorful.bprint('Long wait time for the shell to resurface, restaring vm.')
                self.restart_vm()
            return False
        self.steps_this_node += 1
        self.nsteps += 1

        # Logic of what to do for the current node:
        cur_node = self.nodes[self.current_node]
        if 'lambda' in cur_node:
            x = cur_node['lambda'](self)
            if x == '->': # Jump to next node.
                if cur_node.get('end_node', False):
                    return True
                if 'jump' in cur_node:
                    self.set_node(cur_node['jump'])
                if 'jump_branch' in cur_node:
                    for ky in cur_node['jump_branch'][1].keys():
                        if ky:
                            self.set_node(cur_node['jump_branch'][1][ky])
                raise Exception('Lambda returns a jump condition but the node does not provide a node name to jump to.')
            elif not x:
                pass # Do nothing, keep going with this step.
            elif x == 'break' or x == 'continue':
                return False # Restart this step.
            elif x == 'restart': # Alternative to restarting within the lambda function.
                self.restart_vm(penalize=False)
            else:
                raise Exception('Unrecognized output of a generic lambda.')

        # Response map which can introject randomally (i.e. the machine says "do you want to continue [Y/n].")
        send_this = self.blit_based_response()
        self._restart_if_too_loopy()
        if not send_this:
            pass
        elif callable(send_this): # Rare to return a function, generally lambda is preferred.
            send_this(self)
            return False
        elif send_this.startswith('(node)'):
            self.set_node(send_this.replace('(node)','').strip())
        elif send_this.startswith('(error)'):
            raise Exception(send_this.replace('(error)','').strip())
        elif send_this is not None:
            self.send_cmd(send_this)
            return False

        if 'cmd' in cur_node and self.node_state==0:
            self.node_state = 1
            self.send_cmd(cur_node['cmd'])
            return False

        def _setorend(nd): # End nodes are allowed to have '->' jumps which indicate we are all done.
            if nd == '->' and cur_node.get('end_node', False):
                return nd
            else:
                self.set_node(nd)
                return nd

        if 'jump_branch' in cur_node and 'jump' in cur_node:
            raise Exception('Only one of "jump_branch" or "jump" may be specified.')
        if 'jump' in cur_node:
            set_node = _setorend(cur_node['jump'])
            return bool(set_node == '->' and cur_node.get('end_node', False))
        if 'jump_branch' in cur_node: # The main way to test nodes.
            if self.node_state==1:
                self.send_cmd(cur_node['jump_branch'][0])
                self.node_state = 2
            elif self.node_state == 2:
                txt = self.tubo.blit(False)
                set_node = False
                for ky in cur_node['jump_branch'][1].keys():
                    if (callable(ky) and ky(txt)) or (type(ky) is str and ky in txt): # Functions are hashable and can be used for dict keys.
                        set_node = _setorend(cur_node['jump_branch'][1][ky])
                        break
                if not set_node:
                    for falsey in [None, False]:
                        if falsey in cur_node['jump_branch'][1]:
                            set_node = _setorend(cur_node['jump_branch'][1][falsey])
            return bool(set_node == '->' and cur_node.get('end_node', False))

        raise Exception('The node specified no "jump" or "jump_branch", and is not an "end_node".')

    def run(self):
        while not self.step():
            pass
        return self.tubo
