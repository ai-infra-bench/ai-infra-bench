"""Observe live backing storage derived from actual encoder output tensors.

Tracks storage ownership, aliases and in-place copies, not encoder_cache fields
or a chosen tensor layout. Payload growth includes buffers allocated before
encoding. Profiling compares resident initialization plus retained payload, so
ordinary decoder buffers are counted in both paths. Masks are not payload.
CPU storage bytes are measured, not CUDA allocator peaks.
"""
from torch.utils._python_dispatch import TorchDispatchMode
from torch.utils._pytree import tree_leaves


class PayloadStorage(TorchDispatchMode):
    def __init__(self):
        super().__init__()
        self.references = {}
        self.payloads = set()
        self.resources = set()
        self.metadata = set()
        self.excluded = set()

    def _key(self, tensor):
        storage = tensor.untyped_storage()
        key = storage._weak_ref()
        if key in self.references:
            torch.UntypedStorage._free_weak_ref(key)
        else:
            self.references[key] = True
        return key

    def _keys(self, tensor):
        # Sparse cache layouts own separate value and index storages. Inspect
        # those views without recording the observer's own accessor operations.
        with torch._C._DisableTorchDispatch():
            if tensor.layout == torch.strided:
                data = {self._key(tensor)}
                return data, data
            if tensor.layout == torch.sparse_coo:
                values, indices = tensor._values(), [tensor._indices()]
            elif tensor.layout in (torch.sparse_csr, torch.sparse_bsr):
                values, indices = tensor.values(), [tensor.crow_indices(), tensor.col_indices()]
            elif tensor.layout in (torch.sparse_csc, torch.sparse_bsc):
                values, indices = tensor.values(), [tensor.ccol_indices(), tensor.row_indices()]
            else:
                raise TypeError(f'unsupported physical tensor layout: {tensor.layout}')
            data = {self._key(values)}
            metadata = {self._key(value) for value in indices}
            self.metadata.update(metadata - data)
            self.metadata.difference_update(data)
            return data, data | metadata

    def __torch_dispatch__(self, func, types, args=(), kwargs=None):
        inputs = [value for value in tree_leaves((args, kwargs))
                  if isinstance(value, torch.Tensor)]
        input_keys = [self._keys(value) for value in inputs]
        inherited = any(data & self.payloads for data, _ in input_keys)
        carries_resource = any(all_keys & self.resources for _, all_keys in input_keys)
        result = func(*args, **(kwargs or {}))
        for value in tree_leaves(result):
            if torch.Tensor in type(value).__mro__:
                data, all_keys = self._keys(value)
                if inherited:
                    self.payloads.update(data - self.metadata)
                if inherited or carries_resource:
                    self.resources.update(all_keys)
        return result

    def exclude_existing(self):
        self.excluded.update(self.references)

    def baseline(self):
        # Include shared/preallocated storage that predates this observer too.
        # Weak storage handles do not keep tensors or allocations alive.
        gc.collect()
        for value in gc.get_objects():
            if torch.Tensor in type(value).__mro__:
                try:
                    if not value.is_meta:
                        self._keys(value)
                except (RuntimeError, NotImplementedError):
                    # Symbolic/FakeTensor objects have no physical storage.
                    pass
        return set(self.references)

    def mark(self, outputs):
        for value in tree_leaves(outputs):
            if isinstance(value, torch.Tensor):
                data, all_keys = self._keys(value)
                self.metadata.difference_update(data)
                self.payloads.update(data)
                self.resources.update(all_keys)

    def live_bytes(self, *, include=(), resources=False):
        total = 0
        selected = self.resources if resources else self.payloads
        for key in (selected - self.excluded) | set(include):
            storage = torch.UntypedStorage._new_with_weak_ptr(key)
            if storage is not None:
                total += storage.nbytes()
        return total

    def close(self):
        for key in self.references:
            torch.UntypedStorage._free_weak_ref(key)
        self.references.clear()


def observe_storage(runtime, length, rows):
    indices = [i * (length - 1) // (len(rows) - 1) for i in range(len(rows))]
    spec = {'offset': 0, 'length': length, 'indices': indices, 'rows': rows}
    tokens = [MEDIA_TOKEN if i in indices else 17 for i in range(length)]
    observer = PayloadStorage()
    pair = None
    try:
        with observer:
            pair = runtime.pair(spec, chunk=1)
            baseline = observer.baseline()
            pair.add({'id': 'storage', 'tokens': tokens, 'features': [spec]})
            pair.model.on_encode = observer.mark
            pair.step()
        gc.collect()
        payload = observer.live_bytes()
        live = observer.live_bytes(include=baseline, resources=True)
    finally:
        if pair:
            pair.close()
        observer.close()
    # Drop the first runner before profiling with independently initialized state.
    pair = None
    gc.collect()
    observer = PayloadStorage()
    profiled = []
    try:
        with observer:
            pair = runtime.pair(spec, chunk=1)
            baseline = observer.baseline()
            pair.model.on_encode = observer.mark
            pair.model.on_forward = lambda: profiled.append(observer.live_bytes(include=baseline, resources=True))
            try:
                pair.runner.profile_run()
            except ModelInputObserved:
                pass
        if not profiled:
            raise AssertionError('profiling never reached decoder execution')
        if max(profiled) < live:
            raise AssertionError(f'profiling underestimates retained payload: '
                                 f'live={live}, profiled={profiled}')
        return {'span': length, 'payload_bytes': payload,
                'runtime_bytes': live, 'profile_bytes': max(profiled)}
    finally:
        if pair:
            pair.close()
        observer.close()


def check_storage(runtime):
    rows = [[float(100 + i + j) for j in range(WIDTH)] for i in range(8)]
    observations = [observe_storage(runtime, span, rows) for span in (16, 128, 4096)]
    baseline = observations[0]['payload_bytes']
    # Allow bounded alignment/representation overhead. A larger prompt must not
    # cause an embedding-sized allocation at every non-embedding position.
    allowance = max(256, baseline // 2)
    for item in observations[1:]:
        if item['payload_bytes'] > baseline + allowance:
            raise AssertionError(f'cached payload grows with placeholder span: {observations}')
    return observations
