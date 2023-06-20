# Loading new modules and updating modules (but not file io)
import sys, os, importlib, io, re
import proj
from . import file_io, py_updater

mglobals = proj.global_get('modules_globals', {'varflush_queue':[]})

def add_to_path(folder_name):
    # Also adds the py_updater paths.
    # https://docs.python.org/3/library/sys.html#sys.path
    folder_name = file_io.abs_path(folder_name, True)
    if folder_name not in set(sys.path):
        sys.path = [file_io.abs_path(folder_name, True)]+sys.path
    py_updater.add_user_path(folder_name)

def pop_from_path():
    # Used much less often.
    if len(py_updater.uglobals['user_paths'])>1:
        py_updater.uglobals['user_paths'] = py_updater.uglobals['user_paths'][1:]
        sys.path = sys.path[1:]

def is_user(modulename):
    # Only change user files.
    fname = module_file(sys.modules[modulename])
    if fname is not None:
        phs = py_updater.get_user_paths()
        for ph in phs:
            if ph in fname:
                return True
        return False
    return False

def module_file(m):
    if type(m) is str:
        m = sys.modules[m]
    if '__file__' not in m.__dict__ or m.__file__ is None:
        return None
    return file_io.abs_path(m.__file__, True).replace('\\','/')

def module_fnames(user_only=False):
    # Only modules that have files, and dict values are module names.
    # Also can restrict to user-only files.
    out = {}
    for k in sys.modules.keys():
        fname = module_file(sys.modules[k])
        if fname is not None and (not user_only or is_user(k)):
            out[k] = fname.replace('\\','/')
    return out

def module_from_file(modulename, pyfname, exec_module=True):
    # Creates a module from a file. Generally the modulename will be foo.bar if the
    # file is path/to/external/project/foo/bar.py
    if modulename in sys.modules: # already exists, just update it.
        pyfname0 = module_file(modulename)
        if pyfname0 == pyfname:
            #update_one_module(modulename, False) # Shouldn't be necessary as long as update_user_changed_modules is bieng called.
            return sys.modules[modulename]
        elif pyfname0 is not None:
            pyfname = file_io.abs_path(pyfname, True).replace('\\','/')
            if pyfname != pyfname0:
                raise Exception('Shadowing modulename: '+modulename+' Old py.file: '+pyfname0+ 'New py.file '+pyfname)

    folder_name = os.path.dirname(file_io.abs_path(pyfname, True))
    add_to_path(folder_name)

    #https://stackoverflow.com/questions/67631/how-can-i-import-a-module-dynamically-given-the-full-path
    spec = importlib.util.spec_from_file_location(modulename, pyfname)
    if spec is None:
        raise Exception('None spec')
    foo = importlib.util.module_from_spec(spec)
    sys.modules[modulename] = foo
    if exec_module:
        spec.loader.exec_module(foo)
    return foo
