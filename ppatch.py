# Patch system: Allows making and removing patches to variables.
#   (Also has functions that get variables from modules)
import sys, re
from . import global_vars

# Global variables used:
  # _gld['original_varss'] Saved in set_var, used by reset_var and temp_exec.
  # sys.modules: Used in get_var, set_var, temp_exec, get_vars, get_all_vars.
  #  Note: 'vars' are usually functions.
_gld = global_vars.global_get('ppaglobals', {'original_varss':{}}) # Name-qual => function; name-qual => inputs-as-dict.

def module_name_of(varname_full):
    pieces = varname_full.split('.')
    for i in range(len(pieces), 0, -1): # Longest first.
        k = '.'.join(pieces[0:i])
        if k in sys.modules:
            return k
    return None

def get_var(varname_full):
    # Gets the var object.
    module_name = module_name_of(varname_full)
    varname_leaf = varname_full[len(module_name)+1:]
    pieces = varname_leaf.split('.') # More than one piece if classes inside modules are used.
    y = sys.modules[module_name]
    for p in pieces:
        y = getattr(y,p)
    return y

def _v0(varname_full):
    module_name = module_name_of(varname_full)
    varname_leaf = varname_full[len(module_name)+1:]
    return _gld['original_varss'].get(module_name,{}).get(varname_leaf,None)

def is_modified(varname_full):
    # Any modifications.
    v0 = _v0(varname_full)
    return v0 is not None and v0 is not get_var(varname_full)

def original_var(varname_full):
    v0 = _v0(varname_full)
    if v0 is None:
        return get_var(varname_full)
    return v0

def set_var(varname_full, x):
    pieces = var_name.split('.')
    module_name = module_name_of(varname_full)
    varname_leaf = varname_full[len(module_name)+1:]
    y = sys.modules[module_name]
    if not is_modified(varname_full):
        _gld['original_varss'][module_name] = _gld['original_varss'].get(module_name,{})
        _gld['original_varss'][module_name][varname_leaf] = get_var(module_name, varname_leaf)
    for p in pieces[0:-1]:
        y = getattr(y,p)
    setattr(y, pieces[-1], x)

def reset_var(varname_full):
    module_name = module_name_of(varname_full)
    varname_leaf = varname_full[len(module_name)+1:]
    if is_modified(varname_full):
        set_var(varname_full, _gld['original_varss'][module_name][varname_leaf])

def temp_exec(module_name, class_name, the_code):
    # Temporary exec, inside a class or inside a module.
    # Can be undone with "reset_module_vars(module_name)"
    _gld['original_varss'][module_name] = _gld['original_varss'].get(module_name, {})
    var_store = _gld['original_varss'][module_name]

    if not class_name or class_name == '':
        pieces = []
    else:
        pieces = class_name.split('.')

    y = sys.modules[module_name]
    globals = y.__dict__
    locals = {}
    for p in pieces:
        y = getattr(y,p)
        locals = {**locals, **dict(y.__dict__)} # Class dicts aren't dicts and must be cast to dicts.

    prepend = '' if len(pieces) == 0 else '.'.join(pieces)+'.'
    vars0 = dict(y.__dict__)
    exec(the_code, globals, locals)
    vars1 = dict(y.__dict__)
    for k in set(vars0.keys()).union(set(vars1.keys())):
        if k.endswith('__') or prepend+k in var_store:
            continue
        v0 = vars0.get(k, None); v1 = vars1.get(k, None)
        if v0 is not v1:
            var_store[prepend+k] = v0 # Store the old var, since the new one has changed. Will store None for created vars.

############################### Multible var updates ###############################

def _module_vars_core(out, x, subpath, nest, usedids):
    d = x.__dict__ # Found in both modules and classes.
    kys = list(d.keys()); kys.sort()
    for k in kys:
        if str(type(d[k])) == "<class 'module'>":
            continue # Exclude imports, etc.
        if id(d[k]) in usedids:
            continue # Avoids infinite loops with circular class references.
        if k.startswith('__') and k.endswith('__'): # Oddball python stuff we do not need.
            continue
        out[subpath+k] = d[k]
        usedids.add(id(d[k]))
        if nest and type(d[k]) is type: # Classes.
            _module_vars_core(out, d[k], subpath+k+'.', nest, usedids)

def module_vars(module_name, nest_inside_classes=True):
    # Map from symbol to name.
    out = {}
    usedids = set()
    y = sys.modules[module_name]
    _module_vars_core(out, y, '', nest_inside_classes, usedids)
    return out

def reset_module_vars(module_name):
    for var_name in list(_gld['original_varss'].get(module_name, {}).keys()):
        reset_var(module_name, var_name)

def get_all_vars(nest_inside_classes=True): # For each module.
    return dict(zip(sys.modules.keys(), [module_vars(m, nest_inside_classes) for m in sys.modules.values()]))

def reset_all_vars():
    for module_name in list(_gld['original_varss'].keys()):
        reset_module_vars(module_name)

def get_vars_recursive(stub, nest_inside_classes=True):
    # "foo.bar" and "foo.baz" modules both start with "foo".
    modules = list(filter(lambda m: stub.startswith(m), sys.modules.keys())); modules.sort()
    out = []
    for m in modules:
        out.extend(module_vars(m, nest_inside_classes))
    return out

######## Object/instance updates, very much pre-alpha ##########################

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
