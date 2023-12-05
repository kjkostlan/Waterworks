# Patch system: Allows making and removing patches to variables.
#   (Also has functions that get variables from modules)
import sys, re, inspect, importlib
from . import global_vars

# Global variables used:
  # _gld['original_varss'] Saved in set_var, used by reset_var and temp_exec.
  # sys.modules: Used in get_var, set_var, temp_exec, get_vars, get_all_vars.
  #  Note: 'vars' are usually functions.
_gld = global_vars.global_get('ppaglobals', {'original_varss':{}, 'patchess':{}}) # Name-qual => function; name-qual => inputs-as-dict.

def modulename_varname_split(varname_full):
    # Will import modules if possible, since thats how we get vars from them.
    # The leaf name will have dots if it refers to a member of a class.
    pieces = varname_full.split('.')
    for i in range(len(pieces), 0, -1): # Longest first.
        k = '.'.join(pieces[0:i])
        if k not in sys.modules:
            try:
                importlib.import_module(k)
            except ModuleNotFoundError:
                pass
        if k in sys.modules:
            return k, varname_full[len(k)+1:]
    raise Exception('Cannot find as a module or class: '+varname_full)

def get_var(varname_full):
    # Gets the var object.
    module_name, varname_leaf = modulename_varname_split(varname_full)
    pieces = varname_leaf.split('.') # More than one piece if classes inside modules are used.
    y = sys.modules[module_name]
    for p in pieces:
        y = getattr(y,p)
    return y

def _v0(varname_full):
    module_name, varname_leaf = modulename_varname_split(varname_full)
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
    # Set_var is temporary in that it will not hold after module update. Use add_patch to maintain after module update.
    module_name, varname_leaf = modulename_varname_split(varname_full)
    if not is_modified(varname_full):
        _gld['original_varss'][module_name] = _gld['original_varss'].get(module_name,{})
        _gld['original_varss'][module_name][varname_leaf] = get_var(module_name, varname_leaf)

    pieces = varname_leaf.split('.')
    y = sys.modules[module_name]
    for p in pieces[0:-1]:
        y = getattr(y,p)
    setattr(y, pieces[-1], x)

def var_code(varname_full, assert_find_code=True):
    # assert_find_code False will allow None if it fails to find the code.
    module_name, varname_leaf = modulename_varname_split(varname_full)
    module = sys.modules[module_name]
    x = getattr(module, varname_leaf.split('.')[0])
    src = inspect.getsource(x).replace('\r\n','\n')

    # There is no easy way to extract the source of individual methods within a class, so the best way is to parse it.
    # This simple parser will be tricked with ''' ''' with various defs within it.
    lines = src.split('\n')
    for def_or_class in varname_leaf.split('.')[1:]:
        line_ix = -1
        for i in range(len(lines)):
            line = lines[i]
            if line.strip().startswith('def') or line.strip().startswith('class'):
                def_name = (line+' None').strip().split(' ')[1].split('(')[0].strip()
                if def_name==def_or_class:
                    line_ix = i
                    break
        if line_ix==-1:
            if assert_find_code:
                raise Exception(f'Cannot find the source code for the needed class member within {varname_leaf} (within module {module})')
            else:
                return None
        else:
            indents = len(lines[line_ix])-len(lstrip(lines[line_ix]))
            for i in range(line_ix+1, len(lines):
                line_ix1 = i
                indents1 = len(lines[i])-len(lstrip(lines[i]))
                if indents1<=indents:
                    if lines[i].strip().startswith('def') or lines[i].strip().startswith('class'):
                        break # Stop when there is a def or class that is *less* ro equal indented than or own.
            lines = lines[line_ix:line_ix1] # Narrow down.
    return '\n'.join(lines)

def reset_var(varname_full):
    module_name, varname_leaf = modulename_varname_split(varname_full)
    if is_modified(varname_full):
        set_var(varname_full, _gld['original_varss'][module_name][varname_leaf])

def add_patch(varname_full, make_patch_f, assert_find_code=True, always_reset_var=True):
    # Adds a patch which is persistent across module changes.
    # The function is f(varname_full, var_obj, var_code) => var_obj.
    if always_reset_var:
        reset_var(varname_full)
    module_name, varname_leaf = modulename_varname_split(varname_full)
    _gld['patchess'][module_name] = _gld['patchess'].get(module_name, {})
    _gld['patchess'][module_name][varname_leaf] = {'make_patch_f':make_patch_f, 'assert_src':assert_find_code}
    set_var(varname_full, f(varname_full, get_var(varname_full), var_code(varname_full, assert_find_code=assert_find_code)))

def remove_patch(varname_full):
    reset_var(varname_full)
    module_name, varname_leaf = modulename_varname_split(varname_full)
    _gld['patchess'][module_name] = _gld['patchess'].get(module_name, {})
    if varname_leaf in _gld['patchess'][module_name]:
        del _gld['patchess'][module_name][varname_leaf]

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

def just_after_module_update(module_name): # Re-add patches to the module.
    patches = _gld['patchess'].get(module_name, {})
    for k in patches.keys():
        varname_full = module_name+'.'+k
        mk_f = patches['make_patch_f']; assert_find_code = patches['assert_src']
        reset_var(varname_full)
        set_var(varname_full, mk_f(varname_full, get_var(varname_full), var_code(varname_full, assert_find_code=assert_find_code)))

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
