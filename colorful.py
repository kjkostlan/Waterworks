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
    paren0 = len(line0.replace('(', ''))-len(line0)
    for p in palette:
        line0 = line0.replace(p+'(', '')
    paren1 = len(line0.replace('(', ''))-len(line0)
    return paren0-paren1

def wrapprint(*txt):
    # Adds one more nested paren level to each line.
    txt = ' '.join([str(t) for t in txt])
    try: # If this fails keep going.
        lev = _color_paren_nest_level(txt)
    except:
        lev = 0
    txt = txt.replace('\r\n','\n')
    lines = txt.split('\n')
    p = palette[lev%len(palette)]
    out = []
    lines1 = [p+'('+'\x1b[0m'+line+p+')'+'\x1b[0m' for line in lines]
    for line1 in lines1:
        print(line1)
    return '\n'.join(lines1)
