# Simple nuts-and-bolts IP functions.
import ipaddress, difflib

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

def txt_edit(old_txt, new_txt):
    # If not change or old_txt is None will not make a difference.
    #https://stackoverflow.com/questions/18715688/find-common-substring-between-two-strings
    #https://docs.python.org/3/library/difflib.html
    if old_txt is None or old_txt == new_txt:
        return [0,0,'',''] # Null edit. Please don't add this.
    if type(old_txt) is not str:
        raise TypeError('Both inputs must be a str but old_txt isnt.')
    if type(new_txt) is not str:
        raise TypeError('Both inputs must be a str but new_txt isnt.')
    s = difflib.SequenceMatcher(None, old_txt, new_txt)
    blocks = s.get_matching_blocks() #[(a,b,size)]

    blocks = list(filter(lambda b: b.size>0, blocks))

    if len(blocks)==0:
        return [0, len(old_txt), old_txt, new_txt]

    # Use the first and last block:
    b0 = blocks[0]; b1 = blocks[-1]
    ax0 = 0 if b0.a>0 else b0.a+b0.size
    ax1 = len(new_txt) if b1.b+b1.size<len(new_txt) else b1.b
    bx0 = ax0+b0.b-b0.a; bx1 = bx0+(ax1-ax0)

    return [ax0, ax1, old_txt[ax0:ax1], new_txt[bx0:bx1]]
