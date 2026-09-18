"""Curator-owned behavioral case inventory, never installed for the agent."""
CASES = [
    dict(name=f"merge_{device}_{dtype}_{form}", kind="merge", device=device,
         dtype=dtype, form=form)
    for device in ("cpu", "cuda")
    for dtype in ("float16", "bfloat16", "float32")
    for form in ("nested", "batched")
] + [
    dict(name=f"counts_{device}_{actual}_{expected}", kind="counts",
         device=device, actual=actual, expected=expected)
    for device in ("cpu", "cuda")
    for actual, expected in ((5, 3), (2, 4), (1, 3), (1, 0), (0, 3))
] + [
    dict(name=f"empty_{device}", kind="empty", device=device)
    for device in ("cpu", "cuda")
] + [
    dict(name=f"interface_{oov}", kind="interface", oov=oov,
         device="cuda" if oov else "cpu")
    for oov in (False, True)
]

# Empty outer containers take a different production branch from [empty_tensor].
CASES += [
    dict(name=f"counts_empty_{device}_{form}", kind="counts", device=device,
         actual=0, expected=3, form=form)
    for device in ("cpu", "cuda")
    for form in ("list", "tuple", "tensor")
]

# Equal token counts do not imply equal placeholder positions on later calls.
CASES += [
    dict(name=f"repeated_merge_{device}", kind="repeated_merge", device=device)
    for device in ("cpu", "cuda")
]
