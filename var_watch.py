# Watch vars for certain effects, uses the functionality of ppatch.py
#  Note: Functions for *finding* vars are in ppatch.py
import sys, time, difflib
from . import ppatch, global_vars

# Use of global variables:
   # vglobals['logss'] = Dict of lists of logs. Written to by variables if said variable has been add_fn_watcher()'ed.
     # Stores *per variable* rather than *per file* changes.
   # vglobals['module_watcher_codes']: Optional, if add_fn_watcher specifies custom code to run.
   # sys.modules: Used by add_fn_watcher, add_all_watchers_global, remove_fn_watcher
vglobals = global_vars.global_get('var_watch_uwglobals', {'logss':{}, 'module_watcher_codes':{}})

############################ Var mutation watching #############################

def add_mutation_watch():
    # Vars logged on mutation (how to do this???)
    # (well-written code shouldn't have to hunt down mutations, but should != reality).
    TODO

###################### Fn watching callbacks ###################################

def disk_log(*x):
    # Code freezing up? Use this function to pinpoint where.
    if not global_vars.dump_folder:
        raise Exception('waterworks.global_vars.dump_folder must be set in order to use waterworks.var_watch.disk_log.')
    fname = global_vars.dump_folder+'/var_watch_disklog.txt'
    with open(fname, 'a' if os.path.exists(fname) else 'w') as file:
        file.write(' '.join([str(xi) for xi in x])+'\n')

def logged_fn(varname_full, f_obj):
    # Makes a logged version of the function, which behaves the same but adds to logs.
    def f(*args, _SYM_name=varname_full, **kwargs):
        #print('Logged fn call:', _SYM_name, len(args))
        kwargs1 = kwargs.copy()
        for i in range(len(args)):
            kwargs1[i] = args[i] # Number args turn into dict keys with numerical values.
        time0 = time.time()
        out = f_obj(*args, **kwargs)
        kwargs1['_time'] = [time0, time.time()]
        kwargs1['return'] = out # return is a reserved keyword.
        if _SYM_name not in vglobals['logss']:
            vglobals['logss'][_SYM_name] = []
        vglobals['logss'][_SYM_name].append(kwargs1)
        return out
    return f

########################### Adding and removing watchers #######################

def rm_fn_watcher(varname_full):
    ppatch.remove_patch(varname_full)

def add_fn_watcher(varname_full, f_code=None):
    # Changes the function in var_name to record it's inputs and outputs.
    # Idempotent: removes any old watchers before adding them.
    mname, _ = ppatch.modulename_varname_split(varname_full)

    def make_patch_f(varname_full, var_obj, var_code, f_code=f_code):
        ppatch.reset_var(varname_full)

        if f_code is None:
            f_obj = var_obj
        else:
            f_obj = eval(f_code, locals=None, globals=m.__dict__) # Since globals is top-level, not sure how it will work inside of a class.
        f_with_logs = logged_fn(varname_full, f_obj)
        return f_with_logs

    ppatch.add_patch(varname_full, make_patch_f, assert_find_code=False, always_reset_var=True) # No need to assert find code since it is not used.
    vglobals['module_watcher_codes'][varname_full] = f_code
    return f

def remove_module_watchers(module_name):
    var_dict = ppatch.module_vars(module_name, nest_inside_classes=True)
    for vn in var_dict.keys():
        rm_fn_watcher(module_name+'.'+vn)

def add_module_watchers(module_name):
    #Watches all functions in a module, including class methods (although class nstances may need to be re-instanced).
    remove_module_watchers(module_name) # Reset the module.
    var_dict = ppatch.module_vars(module_name, nest_inside_classes=True)
    for vn in var_dict.keys():
        if callable(var_dict[vn]):
            add_fn_watcher(module_name, vn)

def add_all_watchers_global():
    # Adds all watchers to every module (except this one!)
    # Rarely used since it generally destroys performance.
    for k in sys.modules.keys():
        if k != __name__:
            add_module_watchers(k)

def remove_all_watchers():
    for k in sys.modules.keys():
        if k != __name__:
            remove_module_watchers(k)

def with_watcher(varname_full, args, return_log=False):
    # Add watcher, run code, remove watcher.
    # Option to return_log.
    # TODO: will get more useful if we.
    logs0 = vglobals['logss'].get(varname_full,[])
    add_fn_watcher(varname_full)
    f_obj = ppatch.get_var(varname_full)
    out = f_obj(*args)
    remove_fn_watcher(varname_full)
    logs1 = vglobals['logss'][varname_full]
    return logs1[len(logs0):] if return_log else out

########################### Watchers create logs ###############################

def get_all_logs():
    return vglobals['logss'].copy()

def get_logs(varname_full):
    return vglobals['logss'].get(varname_full,[]).copy()

def remove_all_logs():
    vglobals['logss'] = {}
