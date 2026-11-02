"""Bounded data-only transport; never deserialize candidate Python objects."""
import math


def encode(value, depth=0):
    if depth > 32:
        raise ValueError('Value nesting is too deep')
    if value is None or type(value) in (bool, int, str):
        return {'type': 'scalar', 'value': value}
    if type(value) is float:
        return {'type': 'float', 'value': value.hex()}
    if type(value) is bytes:
        return {'type': 'bytes', 'value': value.hex()}
    if isinstance(value, dict):
        return {'type': 'dict', 'value': [[encode(k,depth+1),encode(v,depth+1)] for k,v in value.items()]}
    for kind, cls in [('list',list),('tuple',tuple),('set',set),('frozenset',frozenset)]:
        if isinstance(value,cls):return {'type':kind,'value':[encode(x,depth+1) for x in value]}
    from collections.abc import Mapping
    if isinstance(value,Mapping):return encode(dict(value),depth)
    raise TypeError('Unsupported return value type')


def decode(item, depth=0):
    if depth > 32 or type(item) is not dict or set(item) != {'type','value'}:
        raise ValueError('Invalid transport value')
    kind,value=item['type'],item['value']
    if kind=='scalar':
        if value is not None and type(value) not in (bool,int,str):raise ValueError('Invalid scalar')
        return value
    if kind=='float' and type(value) is str:return float.fromhex(value)
    if kind=='bytes' and type(value) is str:return bytes.fromhex(value)
    if type(value) is not list:raise ValueError('Invalid container')
    if kind=='dict':return {decode(k,depth+1):decode(v,depth+1) for k,v in value}
    classes={'list':list,'tuple':tuple,'set':set,'frozenset':frozenset}
    if kind not in classes:raise ValueError('Unknown transport type')
    return classes[kind](decode(x,depth+1) for x in value)


def restore_mutation(target, value):
    """Propagate ordinary list/dict/set argument mutations back to trusted tests."""
    if type(target) is list and type(value) is list:target[:]=value
    elif type(target) is dict and type(value) is dict:target.clear();target.update(value)
    elif type(target) is set and type(value) is set:target.clear();target.update(value)
    elif type(target) is tuple and type(value) is tuple:
        for a,b in zip(target,value):restore_mutation(a,b)
