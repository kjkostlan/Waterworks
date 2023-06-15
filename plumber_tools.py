# These plumbertools are used in plumber, and are generally less useful outside of plumber.
import re

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

def apt_error(txt, pkg, cmd_history):
    # Errors and the recommended response after running an apt cmd.
    # Dealing with the lock:
    if 'ps aux | grep -i apt' in str((['']+cmd_history)[-1]):
        # Forceful cleanup.
        # Note: sudo rm /var/lib/dpkg/lock would be the nuclear option.
        lines = list(filter(lambda l: 'grep' not in l and len(l.strip())>0, txt.split('\n')))
        lines = [re.sub('\s+', ' ', l) for l in lines]
        ids = [(l+' 000 000').strip().split(' ')[1] for l in lines]
        ids = list(filter(lambda pid: pid not in ['', '000'], ids))
        if len(ids)>0:
            return '\n'.join(['sudo kill -9 '+pid for pid in ids])

    msgs = {'Unable to acquire the dpkg frontend lock':'ps aux | grep -i apt --color=never',
            "you must manually run 'sudo dpkg --configure -a'":'sudo dpkg --configure -a',
            'Unable to locate package':'sudo apt update\nsudo apt upgrade',
            'has no installation candidate':'sudo apt update\nsudo apt upgrade',
            'Some packages could not be installed. This may mean that you have requested an impossible situation':'sudo apt update\nsudo apt upgrade'}
    for k in msgs.keys():
        if k in txt:
            return msgs[k]
    return None

def pip_error(txt, pkg, cmd_history):
    # Scan for errors in pip.
    # TODO: better handling of --break-system-packages option
    if "Command 'pip' not found" in txt or 'pip: command not found' in txt:
        return 'sudo apt install python3-pip'
    if 'No matching distribution found for' in txt:
        return 'package not found'
    if 'Upgrade to the latest pip and try again' in txt:
        return 'pip3 install --upgrade pip'
    if '--break-system-packages' in txt and 'This environment is externally managed' in txt:
        pkg1 = pkg.split(' ')[-1]
        return f'sudo apt install {pkg1} --break-system-packages'
    return None

def ssh_error(e_txt, cmd_history):
    # Scan for errors in creating the ssh pipe (if making the pipe causes an Exception)
    f_re = lambda plumber: plumber.tubo.remake()
    def banner_err_handle(plumber): # Oh no not this one!
        if not hasattr(plumber, 'SSH_banner_annoy'):
            plumber.SSH_banner_annoy = 0
        plumber.SSH_banner_annoy = plumber.SSH_banner_annoy + 1
        if plumber.SSH_banner_annoy<12:
            plumber.tubo.remake()
        else:
            if plumber.tubo.printouts:
                print('12 banner errors in a row, restarting and hope for the best!')
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

def apt_query(pkg):
    package_name = pkg.split(' ')[-1]
    return f'dpkg -s {package_name}'

def pip_query(pkg):
    #https://askubuntu.com/questions/588390/how-do-i-check-whether-a-module-is-installed-in-python-and-install-it-if-needed
    package_name = pkg.split(' ')[-1]
    return f'python3\nimport sys\nimport {package_name}\nx=456*789 if "{package_name}" in sys.modules else 123*456\nprint(x)\nquit()'

def apt_verify(pkg, txt):
    # Is the pkg installed properly (run after apt_query).
    if 'install ok installed' in txt or 'install ok unpacked' in txt:
        return True
    if 'is not installed' in txt:
        return False

def pip_verify(pkg, txt):
    # Is the pkg installed properly (run after apt_query).
    package_name = pkg.split(' ')[-1]
    if 'Successfully installed ' in txt or 'Requirement already satisfied' in txt:
        return True # Queries by re-running the installation cmd
    if str(456*789) in txt:
        return True # Our Python-based queries.
    if str(123*456) in txt or f"ModuleNotFoundError: No module named '{package_name}'" in txt:
        return False # Our Python-based queries.
    return None
