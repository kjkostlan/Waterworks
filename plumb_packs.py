# Functions and rulesets for how the plumber can install packages.
import re
from . import global_vars
tprint = global_vars.tprint

# Each plumber has a workflow which is a dict of nodes: (tubo has node_state which is set to None upon entering each node).
# "lambda": f(tubo) => called every step if present.
  # Return '->' to jumpt to next node.
  # Return False to do nothing.
  # Return 'break' or 'continue' to stop the current step.
# "cmd": String or list of strings to send as commands.
   # can be/include a "(restart)" to restart the VM
# "response_map": Response to substrings of the last line of blit. Such as "Input Y/n" => "Y".
   # Special responses: "(restart)" to restart, "(node)" to jump to node, and "(error)" to raise an error.
   # AWS and Azure recommend calling the API restart VM function instead of a restart command from inside the shell.
   # Function-values will return response(blit_txt) of None/False.
   # True keys always return the value response, which means it should be a function.
# "jump": Next node to do once done with cmd and response map. "->" means jump to next node (this is compiled away)
# "jump_branch": [test cmd, (dict from look for to branch. False is a catch-all)]. Ran last. Generally will jump back if the test is false.
# "end_node": If True marks the end of the tree.

def default_prompts():
    # Default line end prompts and the needed input (str or function of the pipe).

    return {'Pending kernel upgrade':'\n\n\n','continue? [Y/n]':'Y',
            'Continue [yN]':'Y', 'To continue please press [ENTER]':'\n', # the '\n' actually presses enter twice b/c linefeeds are added.
            'continue connecting (yes/no)?':'Y',
            #The "Which services should be restarted?" box really, really, REALLY wants to be a GUI. So why is it hanging out in the CLI? Either way its restart VM time.
            'Which services should be restarted?':'(restart)'}

def ssh_error(e_txt, cmd_history):
    # Use this if the SSH protocol raises an Exception.
    # If an error isn't recognized an Exception will be thrown.
    f_re = lambda plumber: plumber.tubo.remake()
    def banner_err_handle(plumber): # Oh no not this one!
        if not hasattr(plumber, 'SSH_banner_annoy'):
            plumber.SSH_banner_annoy = 0
        plumber.SSH_banner_annoy = plumber.SSH_banner_annoy + 1
        if plumber.SSH_banner_annoy<12:
            plumber.tubo.remake()
        else:
            if plumber.tubo.printouts:
                tprint('12 banner errors in a row, restarting and hope for the best!')
            plumber.restart_vm()
            plumber.tubo.remake()
            plumber.SSH_banner_annoy = 0
    # The menagerie of ways the pipe can fail:
    msgs = {'Unable to connect to':f_re, 'timed out':f_re,
            'encountered RSA key, expected OPENSSH key':f_re,
            'Connection reset by peer':f_re,
            'Error reading SSH protocol banner':banner_err_handle,
            'Socket is closed':f_re,
            'EOFError':f_re,
            'paramiko.ssh_exception.NoValidConnectionsError':f_re}
    for k in msgs.keys():
        if k in e_txt:
            return msgs[k]
    return None

############################### The world of apt ###############################

def make_snap_nodes(pkg):
    # Snap installation. Can be used if app installation fails.
    # f'sudo snap install {ppair[1]} --classic' # Gives full access.
    pkg = pkg.strip().split(' ')[-1]
    name_main = 'snap '+pkg+' main'
    name_test = 'snap '+pkg+' test'
    nodes = {}
    nodes[name_main] = {'cmd':f'sudo snap install {pkg} --classic', 'jump':name_test}
    nodes[name_test] = {'jump_branch':[f'snap info {pkg}', {False:name_main, 'error:':name_main, 'name:':'->', 'summary:':'->'}]}

    snappy_response_map = {} # In case anything needs to go here.

    for nk in nodes.keys(): # Common response map.
        nodes[nk]['response_map'] = {**default_prompts(), **snappy_response_map}
    return nodes, name_main

def make_apt_nodes(pkg):
    # Apt installation nodes.
    pkg = pkg.strip().split(' ')[-1]
    name_main = 'apt '+pkg+' main'
    name_test = 'apt '+pkg+' test'
    name_kill0 = 'apt '+pkg+' kill_apt_lock_node0'
    name_kill1 = 'apt '+pkg+' kill_apt_lock_node1'

    snap_nodes, snap_node_main = make_snap_nodes(pkg) # Snap is sometimes used instead of apt.

    wants_snap = f'Try "snap install {pkg}"'
    old_apt_f = lambda txt: ('Unable to locate package' in txt or 'has no installation candidate' in txt) and wants_snap not in txt
    response_map = {"you must manually run 'sudo dpkg --configure -a'":'sudo dpkg --configure -a',
                    wants_snap:'(node)'+snap_node_main,
                    old_apt_f:'sudo apt update\nsudo apt upgrade',
                    'Some packages could not be installed. This may mean that you have requested an impossible situation':'sudo apt update\nsudo apt upgrade'}
    response_map = {**default_prompts(), **response_map}
    kl_node_name = pkg+' kill_lock_node' # Lock error => kill process having lock. A VM restart may also work.
    response_map['Unable to acquire the dpkg frontend lock'] = f'(node){kl_node_name}'

    nodes = {}
    nodes[name_main] = {'cmd':f'sudo apt install {pkg}', 'jump':name_test}
    nodes[name_kill0] = {'cmd':'ps aux | grep -i apt --color=never', 'jump':name_kill1}
    def _krespond(txt):
        lines = list(filter(lambda l: 'grep' not in l and len(l.strip())>0, txt.split('\n')))
        lines = [re.sub('\s+', ' ', l) for l in lines]
        ids = [(l+' 000 000').strip().split(' ')[1] for l in lines]
        ids = list(filter(lambda pid: pid not in ['', '000'], ids))
        if len(ids)>0:
            return '\n'.join(['sudo kill -9 '+pid for pid in ids])
    nodes[name_kill1] = {'response_map':{True:_krespond}, 'jump':name_main}

    nodes[name_test] = {'jump_branch':[f'dpkg -s {pkg}', {False:name_main, 'is not installed':name_main, 'install ok installed':'->', 'install ok unpacked':'->'}]}

    for nk in nodes.keys(): # Common response map.
        nodes[nk]['response_map'] = {**response_map, **nodes[nk].get('response_map', {})}

    nodes = {**nodes, **snap_nodes}

    return nodes, name_main

def make_pip_nodes(pkg, verify_name='default'):
    # Verification of installation can be disabled with verift_name = False.
    pkg = pkg.strip().split(' ')[-1]
    response_map = {}
    response_map["Command 'pip' not found"] = 'sudo apt install python3-pip'
    response_map['pip: command not found'] = 'sudo apt install python3-pip'
    response_map['No matching distribution found for'] = '(error)package not found'
    response_map['Upgrade to the latest pip and try again'] = 'pip3 install --upgrade pip'
    response_map[lambda txt:'--break-system-packages' in txt and 'This environment is externally managed' in txt] = f'sudo apt install {pkg} --break-system-packages'

    response_map = {**default_prompts(), **response_map}

    if verify_name == 'default':
        verify_name = pkg # Verify_name will have to occasionally be changed. Use "sys" to disable verification.
        if '-' in pkg or '_' in pkg:
            raise Exception('Not sure if the default verify name will work for pacakges with _ or - in thier name such as: '+pkg)

    name_main = 'pip3 '+pkg+' main'
    name_test = 'pip3 '+pkg+' test'
    nodes = {}
    nodes[name_main] = {'cmd':f'sudo pip3 install {pkg}', 'jump':name_test if verify_name else '->'}
    if verify_name:
        test_cmd = f'python3\npython\nimport sys\nimport {verify_name}\nx=456*789 if "{verify_name}" in sys.modules else 123*456\nprint(x)\nquit()'
        nodes[name_test] = {'jump_branch': [test_cmd, {str(456*789):'->', str(123*456):name_main, False:name_main}]}

    for nk in nodes.keys(): # Common response map.
        nodes[nk]['response_map'] = {**response_map, **nodes[nk].get('response_map', {})}

    return nodes, name_main

################## Make a simple node tree for the plumber #####################

def compile_package_cmd(package_cmd, verify_name='default'):
    ty = package_cmd.strip().split(' ')[0]
    if ty=='apt':
        return make_apt_nodes(package_cmd)
    elif ty=='pip' or ty == 'pip3':
        return make_pip_nodes(package_cmd, verify_name=verify_name)
    else:
        raise Exception('For now, only "apt" and "pip" packages are supported.')
