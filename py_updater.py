import os, sys, importlib, time
from . import file_io, modules, fittings, var_watch, ppatch, global_vars

uglobals = global_vars.global_get('updater_globals', {'filecontents':{}, 'filemodified':{}, 'varflush_queue':[], 'user_paths':[file_io.abs_path('.', True)]})
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

def _fupdate(fname, modulename):
    old_vars = ppatch.get_vars(modulename)
    fname = file_io.abs_path(fname, True).replace('\\','/')

    file_io.clear_pycache(fname)
    importlib.reload(sys.modules[modulename])
    new_txt = file_io.fload(fname)
    if fname in uglobals['filecontents']:
        old_txt = uglobals['filecontents'][fname]
        if old_txt != new_txt:
            if old_txt is None:
                raise Exception('None old_text; files should be preloaded.')
            var_watch.record_txt_update(modulename, fname, fittings.txt_edits(old_txt, new_txt))
    else:
        old_txt = None
    uglobals['filecontents'][fname] = new_txt
    uglobals['filemodified'][fname] = time.time() # Does date modified use the same as our own time?

    new_vars = ppatch.get_vars(modulename)

    out = ModuleUpdate(modulename, old_txt, new_txt, old_vars, new_vars)
    uglobals['varflush_queue'].append(out)
    return out

def save_py_file(py_file, contents, assert_py_module=False):
    # Saves a python file and makes all the needed updates to the modules.
    py_file = file_io.abs_path(py_file, True).replace('\\','/')

    old_txt = file_io.fload(py_file)
    file_io.fsave(py_file, contents)

    f = modules.module_fnames(True)
    for k in f: # a little inefficient to loop through each modulename.
        if f[k] == py_file and old_txt != contents:
            if printouts:
                print('Saving to module:', k)
            return _fupdate(py_file, k)
    if assert_py_module:
        raise Exception('Filename not in listed modules:' + py_file)

def needs_update(modulename, update_on_first_see=True, use_date=False):
    fname = file_io.abs_path(modules.module_file(modulename), True)
    if True not in ['!'+ph in '!'+fname for ph in uglobals['user_paths']]:
        return False # Active paths only.
    if fname not in uglobals['filecontents']: # first time seen.
        return update_on_first_see
    elif use_date:
        return uglobals['filemodified'][fname] < file_io.date_mod(fname)
    else:
        return uglobals['filecontents'][fname] != file_io.fload(fname)

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
    print('Updating MODULE:', modulename, fname)

    out = _fupdate(fname, modulename)
    var_watch.just_after_module_update(modulename)
    return out

def update_user_changed_modules(update_on_first_see=True, use_date=False):
    # Updates modules that aren't pip packages or builtin.
    # use_date True should be faster but maybe miss some files?
    # Returns {mname: ModuleUpdate object}
    fnames = modules.module_fnames(user_only=True)
    #print('Updating USER MODULES, '+str(len(uglobals['filecontents']))+' files currently cached,', str(len(fnames)), 'user modules recognized.')

    out = {}
    for m in fnames.keys():
        if needs_update(m, update_on_first_see, use_date):
            out[m] = update_one_module(m, fnames[m], not update_on_first_see)
    return out

def startup_cache_sources(modulenames=None):
    # Stores the file contents and date-mod to compare against for updating.
    if modulenames is None:
        filenames = modules.module_fnames(True).values()
    else:
        filenames = [modules.module_file(m) for m in modulenames]
    for fname in filenames:
        if fname is not None and fname.endswith('.py'):
            uglobals['filecontents'][fname] = file_io.fload(fname) # no need to call full _fuptate.
            uglobals['filemodified'][fname] = file_io.date_mod(fname)

def startup_python(modulename, pyfname, exec_module=True):
    out = modules.module_from_file(modulename, pyfname, exec_module)
    uglobals['filecontents'][pyfname] = file_io.fload(pyfname) # no need to call full _fuptate.
    uglobals['filemodified'][pyfname] = file_io.date_mod(pyfname)
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

####################### Updating the python objects directly ###################

def default_update_object(x, kvs):
    # Updates x by setting all keys in kvs to thier values.
    TODO

def same_inst_method(x,y):
    # Are x and y the same methods of the same object instance? (False unless both are methods).
    # Python generates methods dynamically on an attribute look-up so "is" won't work.
    if str(type(x)) == "<class 'method'>" and str(type(y)) == "<class 'method'>":
        return x.__self__ is y.__self__
    return False

def default_eq_for_update(x,y):
    # True here means we need to update the values.
    return x is y or same_inst_method(x,y)

def recursive_obj_update(todict_result, replace_pair, update_fn=default_update_object, eq_fn=default_eq_for_update):
    # Recursivly applies replace_pair to todict_result, changing objects held in
    # todict_result[<some path>][todict.ob_key].
    TODO

def function_flush():
    # Looks high and low to the far corners of the Pythonverse for references to out-of-date module functions.
    # Replaces them with the newest version when necessary.
    # Can be an expensive and slow function, run when things seem to not be updated.
    # Will NOT work on class methods passed as a fn param, since these attributes are generated dynamicalls.
    uglobals['varflush_queue']
    TODO

######################################The src cache#############################

def src_cache_from_disk():
    # Gets the src cache from the disk, filename => contetns with local cache.
    # Looks for all python files within this directory.
    fname2contents = {}
    for root, dirs, files in os.walk(".", topdown=False): # TODO: exclude .git and __pycache__ if the time cost becomes significant.
        for fname in files:
            if fname.endswith('.py'):
                fnamer = file_io.rel_path(os.path.join(root, fname))
                fname2contents[fnamer] = file_io.fload(fnamer)
    return fname2contents

def src_cache_diff(old_cache, new_cache=None):
    # Changed file local path => contents; deleted files map to None
    if new_cache is None:
        new_cache = src_cache_from_disk()

    out = {}
    for k in old_cache.keys():
        if k not in new_cache:
            out[k] = None
    for k in new_cache.keys():
        if new_cache[k] != old_cache.get(k,None):
            out[k] = new_cache[k]
    return out

def unpickle64_and_update(txt64, update_us=True, update_vms=True):
    old_cache = src_cache_from_disk()
    file_io.disk_unpickle64(txt64)
    new_cache = src_cache_from_disk()
    delta = src_cache_diff(old_cache, new_cache)
    if update_us:
        update_python_interp(delta)
    if update_vms:
        try:
            import vm # delay the import because install_core has to run as standalone for fresh installs.
            vm.update_vms_skythonic(delta)
        except ModuleNotFoundError:
            print("Not in a project that uses Skythonic's vm module, skipping this step.")
