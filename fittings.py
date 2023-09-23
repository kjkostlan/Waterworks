# Simple nuts-and-bolts IP functions.
import ipaddress, difflib

########################### Vanilla ############################################

def dplane(x, out=None):
    # Flattens a nested dictionary into 2D: [key][index].
    if type(x) is list or type(x) is tuple:
        x = dict(zip(range(len(x)), x))
    if type(x) is set:
        x = dict(zip(x,x))
    if out is None:
        out = {}
    _is_coll = lambda x: type(x) in [list, tuple, dict, set]
    for k in x.keys():
        if k not in out:
            out[k] = []
        if _is_coll(x[k]):
            dplane(x[k], out)
        else:
            out[k].append(x[k])
    return out

def flat_lookup(resc, k, v, assert_range=None):
    # Flat resource lokup. Not recommended for tags.
    if assert_range is None:
        assert_range = [0, 1e100]
    elif type(assert_range) is int:
        assert_range = [assert_range, assert_range]
    out = []
    for r in resc:
        r2 = dplane(r)
        if v in r2.get(k, []):
            out.append(r)
    if len(out)<assert_range[0]:
        raise Exception(f'Too few matches to {rtype} {k} {v}')
    elif len(out)>assert_range[1]:
        raise Exception(f'Too many matches to {rtype} {k} {v}')
    return out

def cwalk(f, x, leaf_only=True):
    # Simple collection walk. Used in the subprocess to wrap objects as strings.
    ty = type(x)
    if type(x) is dict:
        x = x if leaf_only else f(x)
        return dict(zip([cwalk(f, k, leaf_only) for k in x.keys()], [cwalk(f, v, leaf_only) for v in x.values()]))
    elif type(x) is list:
        x = x if leaf_only else f(x)
        return [cwalk(f, xi, leaf_only) for xi in x]
    elif type(x) is set:
        x = x if leaf_only else f(x)
        return set([cwalk(f, xi, leaf_only) for xi in x])
    elif type(x) is tuple:
        x = x if leaf_only else f(x)
        return tuple([cwalk(f, xi, leaf_only) for xi in x])
    else:
        return f(x)

################################# Strings ######################################

def txt_edits(old_txt, new_txt):
    # If not change or old_txt is None will not make a difference.
    # Edits are [ix0, ix1, txt_inserted].
    # Edits must be applied in order.
    #https://stackoverflow.com/questions/18715688/find-common-substring-between-two-strings
    #https://docs.python.org/3/library/difflib.html
    if old_txt is None or old_txt == new_txt:
        return [] # No edit.
    if type(old_txt) is not str:
        raise TypeError('Both inputs must be a str but old_txt isnt.')
    if type(new_txt) is not str:
        raise TypeError('Both inputs must be a str but new_txt isnt.')
    old_txt = old_txt.replace('\r\n','\n')
    new_txt = new_txt.replace('\r\n','\n')

    s = difflib.SequenceMatcher(None, old_txt, new_txt)
    blocks = s.get_matching_blocks() #[(a,b,size)]

    min_size = 12 # Below this size just combine the edits into one feature.
    blocks = list(filter(lambda b: b.size>=min_size, blocks))

    # The edited part is the pieces between the blocks:
    blocks1 = [[0,0,0]]+[[bl.a, bl.b, bl.size] for bl in blocks]+[[len(old_txt), len(new_txt), 0]]

    edits = []
    for i in range(0, len(blocks1)-1):
        b0 = blocks1[i]; b1 = blocks1[i+1] # The part between b0 and b1 is the actual edit.
        ix_starta = b0[0]+b0[2]; ix_enda = b1[0]
        ix_startb = b0[1]+b0[2]; ix_endb = b1[1]
        if ix_enda-ix_starta>0 or ix_endb-ix_startb>0:
            edits.append([ix_starta, ix_enda, new_txt[ix_startb:ix_endb]])
    edits.reverse() # Avoid shift-index errors.

    return edits

def utf8_one_char(read_bytes_fn):
    # One unicode char may be multible bytes, but if so the first n-1 bytes are not valid single byte chars.
    # See: https://en.wikipedia.org/wiki/UTF-8.
    # TODO: consider: class io.TextIOWrapper(buffer, encoding=None, errors=None, newline=None, line_buffering=False, write_through=False)
    #  See: https://stackoverflow.com/questions/18727282/read-subprocess-output-multi-byte-characters-one-by-one
    bytes = read_bytes_fn(1)
    while True:
        try:
            return bytes.decode('UTF-8')
        except UnicodeDecodeError as e:
            if 'unexpected end of data' not in str(e):
                raise e
            bytes = bytes+read_bytes_fn(1)

############################ IP addresses ######################################

def in_cidr(ip_address, cidr_block):
    if ip_address==cidr_block:
        return True
    return ipaddress.ip_network(ip_address).subnet_of(ipaddress.ip_network(cidr_block))

def enclosing_cidrs(ip_or_cidr):
    # All enclosing cidrs, including itself. Shouldn't the ipddress module have a similar feature?
    if ':' in ip_or_cidr:
        raise Exception('TODO: ipv6')
    pieces = ip_or_cidr.replace('/','.').split('.')
    if '/' not in ip_or_cidr:
        return enclosing_cidrs(ip_or_cidr+'/32')
    elif '/32' in ip_or_cidr:
        return [ip_or_cidr.replace('/32',''), ip_or_cidr]+enclosing_cidrs('.'.join(pieces[0:3])+'.0/24')
    elif '/24' in ip_or_cidr:
        return [ip_or_cidr]+enclosing_cidrs('.'.join(pieces[0:2]+['0'])+'.0/16')
    elif '/16' in ip_or_cidr:
        return [ip_or_cidr]+enclosing_cidrs('.'.join(pieces[0:1]+['0', '0'])+'.0/8')
    elif '/8' in ip_or_cidr:
        return [ip_or_cidr, '0.0.0.0/0']
    elif '/0' in ip_or_cidr:
        return [ip_or_cidr]
