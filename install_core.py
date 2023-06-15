# TODO: this is kind of orphaned code.
############################ Bootstrapping an installation #####################

def bootstrap_txt(windows, pickle64, pyboot_txt=True, import_txt=True, github_txt=False):

    def joinlines(lines, windows=False):
        if windows:
            out = '\r\n'+'\r\n'.join(lines)+'\r\n'
        else:
            out = '\n'+'\n'.join(lines)+'\n'
        return out

    lines = ['cd ~', 'mkdir Skythonic', 'cd ~/Skythonic', 'python3=3','python3','python=3','python'] # In or out of python shell.
    quote3 = "''"+"'" # Can't appear in file.

    if pyboot_txt: # Diff will only change the differences.
        lines.append('import sys, os, time, subprocess')
        for py_file in ['install_core.py', 'file_io.py']:
            boot_txt = file_io.fload(py_file)
            varname = py_file[0:-3]+'_src'
            if quote3 in boot_txt:
                raise Exception('This ad-hoc paste-in system cannot handle files with triple single quotes.')
            lines.append(f'{varname}=r{quote3}{boot_txt}{quote3}') # works because no triple """ in boot_txt.
            lines.append(f'pyboot_f_obj = open("{py_file}","w")')
            lines.append(f'pyboot_f_obj.write({varname})')
            lines.append('pyboot_f_obj.close()')
    lines.append(f'obj64 = r"""{pickle64}"""')
    if import_txt:
        lines.append('import install_core')
    lines.append('install_core.unpickle_and_update(obj64, True, True)')
    if github_txt: # This is an interactive tool => use dev branch not main.
        lines.append("import install_core")
        #lines.append("sudo apt-get install git") # Would this help to have?
        lines.append("install_core.install_git_fetch(branch='dev')")
    if import_txt:
        lines.append('from pastein import *')
    return joinlines(lines, windows)

def gitHub_bootstrap_txt(windows=False):
    txt = """
cd ~
mkdir Skythonic
cd ~/Skythonic
python3=3 # Python vs Python3.
python3
python=3
python
import os
branch = 'dev'
fnames = ['file_io.py', 'install_core.py']
#os.system('sudo apt install curl -y') # Make sure curl is installed first!
urls = [f'https://raw.githubusercontent.com/kjkostlan/Skythonic/{branch}/{fname}' for fname in fnames]
[os.unlink('./'+fname) if os.path.exists(fname) else None for fname in fnames]
curl_cmds = [f'curl "{urls[i]}" -o "./{fnames[i]}"' for i in range(len(fnames))]
[os.system(curl_cmd) for curl_cmd in curl_cmds]
bad_fnames = list(filter(lambda fname: not os.path.exists(fname), fnames))
print('WARNING: the curl bootstrap may have failed.') if len(bad_fnames)>0 else None
print(f'Curled github bootstrap branch {branch} to folder {os.path.realpath(".")}; the GitHub curl requests may be a few minutes out of date.')
import install_core # Now that the file has been created.
install_core.install_git_fetch(branch=branch)
    """
    if windows:
        txt = txt.replace('\n','\r\n')
    return txt
