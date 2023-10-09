# Tools to keep track of changes, update Python modules after save, and represent said changes as a dict.
import os, sys, importlib, time
from . import file_io, modules, fittings, var_watch, ppatch, global_vars
tprint = global_vars.tprint

# Use of global variables:
#  uglobals['filecontents_last_module_update'] is updated with the current contents during _module_update_core(). Used by needs_update()
   # Difference from file_io.fglobals['original_txts']: 'filecontents_last_module_update' is updated whenever the module is.
#  uglobals['filemodified_last_module_update'] has a similar lifecycle to 'filecontents_last_module_update' but stores the modified date.
#  uglobals['varflush_queue'] appended in _module_update_core, used in ppatch.function_flush()
#  uglobals['user_paths'] startis as [os.realpath('.')], added to with add_user_path, queried with get_user_paths, used by needs_update.
#  sys.modules: Used in _fupdate, module_fnames, and update_python_interp
uglobals = global_vars.global_get('updater_globals', {'filecontents_last_module_update':{}, 'filemodified_last_module_update':{}, 'varflush_queue':[], 'user_paths':[file_io.abs_path('.', True)]})
printouts = True

class ModuleUpdate:
    # How to look up var from id:
    # https://stackoverflow.com/questions/15011674/is-it-possible-to-dereference-variable-ids
    '''
    import _ctypes

    def di(obj_id):
        return _ctypes.PyObj_FromPtr(obj_id)

    # OR this:
    import ctypes
    a = "hello world"
    print ctypes.cast(id(a), ctypes.py_object).value
    '''
    # (But this is dangerous, so lets not rely on it unless we really need to).
    # Stores the module updating.
    def __init__(self, modulename, old_txt, new_txt, old_vars, new_vars):
        self.modulename = modulename
        self.old_txt = old_txt
        self.new_txt = new_txt

        self.old_new_pairs = {}
        for k in new_vars.keys():
            if k in old_vars and old_vars[k] is not new_vars[k]:
                self.old_new_pairs[k] = [old_vars[k], new_vars[k]]

def add_user_path(ph):
    # Put your project folders here.
    ph = file_io.abs_path(ph, True)
    if ph not in uglobals['user_paths']:
        uglobals['user_paths'].append(ph)

def get_user_paths():
    return uglobals['user_paths'].copy()

def needs_update(modulename, update_on_first_see=True, use_date=False):
    fname = file_io.abs_path(modules.module_file(modulename), True)
    if True not in ['!'+ph in '!'+fname for ph in uglobals['user_paths']]:
        return False # Active paths only.
    if fname not in uglobals['filecontents_last_module_update']: # first time seen.
        return update_on_first_see
    elif use_date:
        return uglobals['filemodified_last_module_update'][fname] < file_io.date_mod(fname)
    else:
        return uglobals['filecontents_last_module_update'][fname] != file_io.fload(fname)

def _module_update_core(fname, modulename):
    old_vars = ppatch.get_vars(modulename)
    fname = file_io.abs_path(fname, True).replace('\\','/')

    file_io.clear_pycache(fname)
    try:
        importlib.reload(sys.modules[modulename])
    except Exception as e:
        if "spec not found for the module '__main__'" in str(e):
            print('Warning: Cannot reload the __main__ module.')
            pass
        else:
            raise e
    new_txt = file_io.fload(fname)
    if fname in uglobals['filecontents_last_module_update']:
        old_txt = uglobals['filecontents_last_module_update'][fname]
        if old_txt != new_txt:
            if old_txt is None:
                raise Exception('None old_text; files should be preloaded.')
    else:
        old_txt = None
    uglobals['filecontents_last_module_update'][fname] = new_txt
    uglobals['filemodified_last_module_update'][fname] = file_io.date_mod(fname)

    new_vars = ppatch.get_vars(modulename)

    out = ModuleUpdate(modulename, old_txt, new_txt, old_vars, new_vars)
    uglobals['varflush_queue'].append(out)
    return out

def update_one_module(modulename, fname=None, assert_main=True):
    # The module must already be in the file.
    if modulename == '__main__' and assert_main: # odd case, generates spec not found error.
        raise Exception('Cannot update the main module for some reason. Need to restart when the Termpylus_main.py file changes.')
    elif modulename == '__main__':
        return
    if fname is None:
        fname = modules.module_file(modulename)
    if fname is None:
        raise Exception('No fname supplied and cannot find the file.')
    tprint('Updating MODULE:', modulename, fname)

    out = _module_update_core(fname, modulename)
    var_watch.just_after_module_update(modulename)
    return out

def update_user_changed_modules(update_on_first_see=True, use_date=False):
    # Updates modules that aren't pip packages or builtin.
    # use_date True should be faster but maybe miss some files?
    # Returns {mname: ModuleUpdate object}
    mod_fnames = modules.module_fnames(user_only=True)
    #print('Updating USER MODULES, '+str(len(uglobals['filecontents_last_module_update']))+' files currently cached,', str(len(fnames)), 'user modules recognized.')

    out = {}
    for m in mod_fnames.keys():
        fname = mod_fnames[m]
        if needs_update(m, update_on_first_see, use_date):
            out[m] = update_one_module(m, fname, not update_on_first_see)
        else:
            uglobals['filecontents_last_module_update'][fname] = file_io.fload(fname) # These may not be set if update_on_first_see is False.
            uglobals['filemodified_last_module_update'][fname] = file_io.date_mod(fname)
    return out

def module_fnames(): # Code from Termpylus.
    # Only modules that have files, and dict values are module names.
    # Also can restrict to user-only files.
    out = {}
    kys = list(sys.modules.keys()) # Once in a while sys.modules can get a new module during this loop.
    for k in kys:
        fname = sys.modules[k].__dict__.get('__file__', None)
        if fname is not None:
            out[k] = fname.replace('\\','/')
    return out

def update_python_interp(delta):
    # Keep the Python intrepretator up to date
    fnames = module_fnames()
    inv_fnames = dict(zip([file_io.rel_path(v) for v in fnames.values()], fnames.keys()))
    for fname in delta.keys():
        if fname in inv_fnames:
            mname = inv_fnames[fname]
            if mname in sys.modules:
                update_one_module(inv_fnames[fname], fname)

############################Walking source files##################################

def py_walk_list(root='.', relative_paths=True):
    # Recursivly look for .py files.
    # Gets the src cache from the disk, filename => contents with local cache.
    # Looks for all python files within this directory. Paths are relative.
    filelist = []
    for root, dirs, files in os.walk(root, topdown=False): # TODO: exclude .git and __pycache__ if the time cost becomes significant.
        for fname in files:
            if fname.endswith('.py'):
                if relative_paths:
                    fname1 = file_io.rel_path(os.path.join(root, fname)).replace('\\','/')
                else:
                    fname1 = os.path.realpath(os.path.join(root, fname)).replace('\\','/')
                filelist.append(fname1)
    return fname1

def walk_all_user_paths(relative_paths=False):
    # Walk all subfolders within each user path.
    cat_lists_here = []
    phs = set(uglobals['user_paths']); phs.sort()
    for ph in phs:
        cat_lists_here.extend(ph, relative_paths=relative_paths)
    return cat_lists_here

def py_walk_getcache(root='.', relative_paths=True):
    # Dict from path to file list.
    files = py_walk_list(root, relative_paths)
    return dict(zip(files, [file_io.fload(fname) for fname in files]))

def cache_diff(old_cache, new_cache=None):
    # Changed file local path => contents; deleted files map to None
    if new_cache is None:
        new_cache = py_walk_getcache()

    out = {}
    for k in old_cache.keys():
        if k not in new_cache:
            out[k] = None
    for k in new_cache.keys():
        if new_cache[k] != old_cache.get(k,None):
            out[k] = new_cache[k]
    return out

def unpickle64_and_update(txt64, update_us=True, update_vms=True):
    old_cache = py_walk_getcache(root='.', relative_paths=True)
    file_io.disk_unpickle64(txt64)
    new_cache = py_walk_getcache(root='.', relative_paths=True)
    delta = cache_diff(old_cache, new_cache)
    if update_us:
        update_python_interp(delta)
    if update_vms:
        try:
            import vm # delay the import because install_core has to run as standalone for fresh installs.
            vm.update_vms_skythonic(delta)
        except ModuleNotFoundError:
            tprint("Not in a project that uses Skythonic's vm module, skipping this step.")
