"""Invoke the task-named operator through its registered public Torch schema.

The statement specifies an operator name and behavior, not an out-parameter ABI.
Both a functional operator returning (q, scales) and an operator filling supplied
outputs are valid. Resolve this once, outside measured calls; never inspect a
candidate's private Python helper or infer its algorithm.
"""
import torch


def make_quantizer(op):
    schema = op.default._schema
    types = [str(arg.type) for arg in schema.arguments]
    returns = [str(arg.type) for arg in schema.returns]
    functional = (len(types) == 5 and types[0] == "Tensor"
                  and returns == ["Tensor", "Tensor"])
    output_parameters = (len(types) == 7 and types[:3] == ["Tensor"] * 3
                         and not returns)
    if not (functional or output_parameters):
        raise RuntimeError(f"Unsupported native operator call convention: {schema}")
    scalars = types[1:] if functional else types[3:]
    if scalars[:2] != ["int", "float"] or any(t not in ("int", "float") for t in scalars[2:]):
        raise RuntimeError(f"Unsupported native scalar types: {schema}")
    lower_type = int if scalars[2] == "int" else float
    upper_type = int if scalars[3] == "int" else float
    empty_like, empty = torch.empty_like, torch.empty

    if functional:
        def quantize(x, group, eps=1e-10, lower=-128, upper=127):
            return op(x, group, eps, lower_type(lower), upper_type(upper))
    else:
        def quantize(x, group, eps=1e-10, lower=-128, upper=127):
            q = empty_like(x, dtype=torch.int8)
            scales = empty(x.shape[:-1] + (x.shape[-1] // group,),
                           device=x.device, dtype=torch.float32)
            op(x, q, scales, group, eps, lower_type(lower), upper_type(upper))
            return q, scales
    return quantize
