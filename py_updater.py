# Tools to keep track of changes, update Python modules after save, and represent said changes as a dict.
import os, sys, importlib, time
from . import global_vars, paths, file_io, modules, fittings, var_watch, ppatch
tprint = global_vars.tprint

# Use of global variables:
#  uglobals['filecontents_last_module_update'] is updated with the current contents during _module_update_core(). Used by needs_update()
   # Difference from file_io.fglobals['original_txts']: 'filecontents_last_module_update' is updated whenever the module is.
#  uglobals['filemodified_last_module_update'] has a similar lifecycle to 'filecontents_last_module_update' but stores the modified date.
#  uglobals['varflush_queue'] appended in _module_update_core, used in ppatch.function_flush()
#  sys.modules: Used in _fupdate, module_fnames, and update_python_interp
uglobals = global_vars.global_get('updater_globals', {'filecontents_last_module_update':{}, 'filemodified_last_module_update':{}, 'varflush_queue':[]})
try:
    printouts
except:
    printouts = True
    stringswap_fn = None # Optional f(modulename, txt) => txt => saved to disk. Allows tweaking the source code whenver a file is saved.
    module_update_callback = None # Optional f(ModuleUpdate) lets user code run when just after the point when the module is updated.

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
    def __init__(self, module_name, old_txt, new_txt, old_vars, new_vars):
        self.module_name = module_name
        self.old_txt = old_txt
        self.new_txt = new_txt

        self.old_new_pairs = {}
        for k in new_vars.keys():
            if k in old_vars and old_vars[k] is not new_vars[k]:
                self.old_new_pairs[k] = [old_vars[k], new_vars[k]]

def needs_update(module_name, update_on_first_see=True, use_date=False):
    fname = paths.abs_path(modules.module_file(module_name), True)
    if True not in ['!'+ph in '!'+fname for ph in paths.get_user_paths()]:
        return False # Active paths only.
    if fname not in uglobals['filecontents_last_module_update']: # first time seen.
        return update_on_first_see
    elif use_date:
        return uglobals['filemodified_last_module_update'][fname] < file_io.date_mod(fname)
    else:
        return uglobals['filecontents_last_module_update'][fname] != file_io.fload(fname)

def _module_update_core(fname, module_name):
    old_vars = ppatch.module_vars(module_name)
    fname = paths.abs_path(fname, True).replace('\\','/')

    file_io.clear_pycache(fname)
    try:
        importlib.reload(sys.modules[module_name])
    except Exception as e:
        if "spec not found for the module '__main__'" in str(e):
            print('Warning: Cannot reload the __main__ module; update skipped.')
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

    if stringswap_fn:
        new_txt1 = stringswap_fn(module_name, new_txt)
        if type(new_txt1) is not str:
            raise Exception('stringswap_fn must return a string object')
        if new_txt1 != new_txt:
            file_io.fsave(fname, new_txt1)
            new_txt = new_txt1

    new_vars = ppatch.module_vars(module_name)

    out = ModuleUpdate(module_name, old_txt, new_txt, old_vars, new_vars)
    uglobals['varflush_queue'].append(out)
    if module_update_callback:
        module_update_callback(out)
    return out

def update_one_module(module_name, fname=None, assert_main=True):
    # The module must already be in the file.
    if module_name == '__main__' and assert_main: # odd case, generates spec not found error.
        raise Exception('Python disallows updating the main module for some reason. Turn off assert_main to skip updating and not throw an error.')
    elif module_name == '__main__':
        return
    if fname is None:
        fname = modules.module_file(module_name)
    if fname is None:
        raise Exception('No fname supplied and cannot find the file.')
    tprint('Updating MODULE:', module_name, fname)

    out = _module_update_core(fname, module_name)
    var_watch.just_after_module_update(module_name)
    return out

def update_user_changed_modules(update_on_first_see=True, use_date=False, assert_main=False):
    # Updates modules that aren't pip packages or builtin.
    # use_date True should be faster but maybe miss some files?
    # Returns {mname: ModuleUpdate object}
    mod_fnames = modules.module_fnames(user_only=True)
    #print('Updating USER MODULES, '+str(len(uglobals['filecontents_last_module_update']))+' files currently cached,', str(len(fnames)), 'user modules recognized.')

    out = {}
    for m in mod_fnames.keys():
        fname = mod_fnames[m]
        file_io.contents_on_first_call(fname) # Store the contents if no original version is stored.
        if needs_update(m, update_on_first_see, use_date):
            out[m] = update_one_module(m, fname, assert_main=assert_main)
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
    inv_fnames = dict(zip([paths.rel_path(v) for v in fnames.values()], fnames.keys()))
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
                    fname1 = paths.rel_path(os.path.join(root, fname)).replace('\\','/')
                else:
                    fname1 = os.path.realpath(os.path.join(root, fname)).replace('\\','/')
                filelist.append(fname1)
    return filelist

def walk_all_user_paths(relative_paths=False):
    # Walk all subfolders within each user path.
    cat_lists_here = []
    phs = list(set(paths.get_user_paths())); phs.sort()
    for ph in phs:
        flist = py_walk_list(ph, relative_paths=relative_paths)
        cat_lists_here.extend(flist)
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
