# Stores global variables. Is there an easy-to-use Python module that does this?
import threading

def global_get(name, initial_value):
    # Sets dataset[name] to initial_value if none exists.
    if name not in dataset:
        dataset[name] = initial_value
    return dataset[name]

def tprint(*args, **kwargs): # Globally thread-safe print.
    with print_mutex:
        print(*args, **kwargs)

try:
    x
except:
    x = 'The below code should only run once!'
    dump_folder = False # Must be set, preferably to an absolute path, if it is to be used (used by the disk log feature).
    dataset = {} # Technically, these are per-session variables.
    print_mutex = threading.Lock()
