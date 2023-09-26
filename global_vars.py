# Stores global variables. Is there an easy-to-use Python module that does this?
import sys, threading

def global_get(name, initial_value):
    # Sets dataset[name] to initial_value if none exists.
    if name not in dataset:
        dataset[name] = initial_value
    return dataset[name]

def tprint(*args, **kwargs): # Globally thread-safe print.
    with print_mutex:
        print(*args, **kwargs)

def bprint(*args): # Binary print, encodes non-bytes items with utf-8.
    bytess = []
    for a in args:
        if type(a) is not bytes:
            a = str(a).encode('utf-8')
        bytess.append(a)
    out = b''.join(bytess)
    with print_mutex:
        #https://stackoverflow.com/questions/908331/how-to-write-binary-data-to-stdout-in-python-3
        sys.stdout.buffer.write(out)

try:
    x
except:
    x = 'The below code should only run once!'
    dump_folder = False # Must be set, preferably to an absolute path, if it is to be used (used by the disk log feature).
    dataset = {} # Technically, these are per-session variables.
    print_mutex = threading.Lock()
