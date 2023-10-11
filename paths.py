# Handles paths.
import sys, os
from . import global_vars

# Global variables:
  # original_cwd = set once to realpath('.')
  # user_paths = set to [realpath('.')]
  # sys.path = set by add_user_path, rm_user_path; considered a superset of user_paths.
ph = os.path.realpath('.').replace('\\','/')
pglobals = global_vars.global_get('paths_globals', {'user_paths':[ph], 'original_cwd':ph})

def linux_if_str(txt):
    if type(txt) is str:
        return txt.replace('\r\n','\n')
    else:
        return txt

def folder_file(fname):
    # Splits into absolute folder and file.
    fname = abs_path(fname)
    pieces = fname.split('/')
    return '/'.join(pieces[0:-1]), pieces[-1]

def is_folder(fname):
    fname = abs_path(fname)
    return os.path.isdir(fname)

def is_path_absolute(fname):
    # Different rules for linux and windows.
    fname = fname.replace('\\','/')
    linux_abspath = fname[0]=='/'
    win_abspath = len(fname)>2 and fname[1]==':' # C:/path/to/folder
    if linux_abspath or win_abspath: # Two ways of getting absolute paths.
        return True
    return False

def abs_path(fname, use_orig_working_directory=False):
    # The absolute path, using either the current working directory OR the original working directory.
    # The former option will change if os.ch_dir() is called.
    if is_path_absolute(fname) or not use_orig_working_directory:
        return os.path.realpath(fname).replace('\\','/')
    else:
        out = os.path.realpath(pglobals['original_cwd']+'/'+fname).replace('\\','/')
        if not is_path_absolute(out):
            raise Exception('Assert failed: Output path not absolute but in this code.')
        return out

def rel_path(fname, use_orig_working_directory=False):
    # Relative path (NOT realpath, which is an absolute path!).
    # Will default to abs_path if not inside the current working directory (less messy than double dots).
    a = abs_path(fname, use_orig_working_directory)
    ph = abs_path('.', use_orig_working_directory)
    n = len(ph)

    if ph in a:
        return ('./'+a[n:]).replace('//','/')
    else:
        return a

############################# User interaction sets the paths ##################

def add_user_path(ph):
    # Put your project folders here. Both updates our own user_paths and sys.path
    #   (not everything in sys.path should be in user_paths, thus )
    # https://docs.python.org/3/library/sys.html#sys.path
    ph = abs_path(ph, True)
    if ph not in pglobals['user_paths']:
        pglobals['user_paths'].append(ph)
    if folder_name not in set(sys.path):
        sys.path = [abs_path(folder_name, True)]+sys.path

def get_user_paths():
    return pglobals['user_paths'].copy()

def rm_user_path(ph):
    # Remove from both the system path and from user_paths.
    ph = abs_path(ph, True)
    f = lambda ph1: abs_path(ph1) != ph
    pglobals['user_paths'] = list(filter(f, pglobals['user_paths']))
    sys.path = list(filter(f, sys.path))

def pop_from_path(): # Remove the last path. Used for temporary testing.
    if len(pglobals['user_paths'])>1:
        last_ph = pglobals['user_paths'][-1]
        rm_user_path(last_ph)
