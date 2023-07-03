# People don't use color enough.
# Colors: https://misc.flogisoft.com/bash/tip_colors_and_formatting
def bprint(*txt):
    # Use a light blue color to differentiate from the data dump that is the ssh/bash stream.
    txt = ' '.join([str(t) for t in txt])
    print('\033[94m'+txt+'\033[0m', end='')

def oprint(*txt):
    # Orange.
    txt = ' '.join([str(t) for t in txt])
    print('\x1b[0;33;40m'+txt+'\x1b[0m')

def arrowprint(*txt):
    txt = ' '.join([str(t) for t in txt])
    print('\x1b[0;33;40m'+'→'+'\x1b[6;30;42m'+txt+'\x1b[0;33;40m'+'←'+'\x1b[0m')

def arrowprint1(*txt):
    # Slightly different.
    txt = ' '.join([str(t) for t in txt])
    print('\x1b[0;33;40m'+'→'+'\033[97;104m'+txt+'\x1b[0;33;40m'+'←'+'\x1b[0m')


palette = ["\x1b[38;5;196m", "\x1b[38;5;220m", "\x1b[38;5;185m", "\x1b[38;5;40m", "\x1b[38;5;27m", "\x1b[38;5;201m"] # For paren nesting.
def _color_paren_nest_level(txt):
    txt = txt.strip().replace('\r\n','\n')
    line0 = txt.split('\n')[0]
    _cx = 2543
    line0 = line0.replace(chr(_cx),'')
    for p in palette:
        line0 = line0.replace(p+'(', chr(_cx))
    return len(line0)-len(line0.replace(chr(_cx), ''))

def wrap(txt):
    try: # If this fails keep going.
        lev = _color_paren_nest_level(txt)
    except:
        lev = 0
    txt = txt.replace('\r\n','\n')
    lines = txt.split('\n')
    p = palette[lev%len(palette)]
    out = []
    txt1 = '\n'.join([p+'('+'\x1b[0m'+line+p+')'+'\x1b[0m' for line in lines])
    return txt1

def unwrap_all(txt):
    # Undoes wrapprint, if wrapped in the first place.
    for p in palette:
        txt = txt.replace(p+'('+'\x1b[0m','')
        txt = txt.replace(p+')'+'\x1b[0m','')
    return txt

def wrapprint(*txt):
    # Adds one more nested paren level to each line.
    txt = ' '.join([str(t) for t in txt])
    txt1 = wrap(txt)
    print(txt1, end='')
    return txt1
