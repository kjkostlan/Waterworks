# Patch system: Allows making and removing patches to variables.
# (Of course this requires functions that get variables from modules)
import sys
import proj

_gld = proj.global_get('ppaglobals', {'original_varss':{}}) # Name-qual => function; name-qual => inputs-as-dict.

def _v0(modulename, var_name):
    return _gld['original_varss'].get(modulename,{}).get(var_name,None)

def get_var(modulename, var_name):
    # Gets the var.
    pieces = var_name.split('.')
    y = sys.modules[modulename]
    for p in pieces:
        y = getattr(y,p)
    return y

def is_modified(modulename, var_name):
    # Any modifications.
    v0 = _v0(modulename, var_name)
    return v0 is not None and v0 is not get_var(modulename, var_name)

def original_var(modulename, var_name):
    v0 = _v0(modulename, var_name)
    if v0 is None:
        return get_var(modulename, var_name)
    return v0

def set_var(modulename, var_name, x):
    pieces = var_name.split('.')
    y = sys.modules[modulename]
    if not is_modified(modulename, var_name):
        _gld['original_varss'][modulename] = _gld['original_varss'].get(modulename,{})
        _gld['original_varss'][modulename][var_name] = get_var(modulename, var_name)
    for p in pieces[0:-1]:
        y = getattr(y,p)
    setattr(y, pieces[-1], x)

def reset_var(modulename, var_name):
    if is_modified(modulename, var_name):
        set_var(modulename, var_name, _gld['original_varss'][modulename][var_name])

def eval_here(modulename, code_txt, delete_new_vars=False):
    # Runs code_txt in modulename. Returns any vars that are created (added to the __dict__)
    # (which means that it returns an empty dict for purely side-effect-free code).
    # Option to delete new vars to "clean up"
    #https://stackoverflow.com/questions/2220699/whats-the-difference-between-eval-exec-and-compile
    m = modulename if type(modulename) is type(sys) else sys.modules[modulename]

    vars0 = set(m.__dict__.keys())
    exec(code_txt, vars(m)) # This also makes
    new_vars = list(set(m.__dict__.keys())-vars0); new_vars.sort()

    out = {}
    for new_var in new_vars:
        out[new_var] = getattr(m, new_var)
        if delete_new_vars:
            delattr(m, new_var)
    return out

############################### Multible updates ###############################

def _get_vars_core(out, x, subpath, nest, usedids):
    d = x.__dict__ # Found in both modules and classes.
    for k in d.keys():
        if str(type(d[k])) == "<class 'module'>":
            continue # Exclude imports, etc.
        if id(d[k]) in usedids:
            continue # Avoids infinite loops with circular class references.
        if k.startswith('__') and k.endswith('__'): # Oddball python stuff we do not need.
            continue
        out[subpath+k] = d[k]
        usedids.add(id(d[k]))
        if nest and type(d[k]) is type: # Classes.
            _get_vars_core(out, d[k], subpath+k+'.', nest, usedids)

def get_vars(modulename, nest_inside_classes=True):
    # Map from symbol to name.
    out = {}
    usedids = set()
    y = sys.modules[modulename]
    _get_vars_core(out, y, '', nest_inside_classes, usedids)
    return out

def get_all_vars(nest_inside_classes=True): # For each module.
    return dict(zip(sys.modules.keys(), [get_vars(m, nest_inside_classes) for m in sys.modules.values()]))
