# Stores global variables. Is there an easy-to-use Python module that does this?
def global_get(name, initial_value):
    # Sets dataset[name] to initial_value if none exists.
    if name not in dataset:
        dataset[name] = initial_value
    return dataset[name]

try:
    x
except:
    x = 'The below code should only run once!'
    dump_folder = False # Must be set, preferably to an absolute path, if it is to be used (used by the disk log feature).
    dataset = {} # Technically, these are per-session variables.
