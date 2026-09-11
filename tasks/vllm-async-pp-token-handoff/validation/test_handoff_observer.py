"""Real-CUDA regressions for the verifier observer, not Harbor results."""
from pathlib import Path
import sys
import json

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
import torch
from handoff_observer import HandoffObserver


def main():
    x = torch.arange(6, device="cuda", dtype=torch.int32)
    destination = torch.empty(6, dtype=x.dtype, pin_memory=True)
    event = torch.cuda.Event()
    event.record()
    generic_event = torch.Event()
    generic_event.record()
    generic_stream = torch.Stream(device="cuda")
    cases = [
        ("cpu", lambda: x.cpu(), True),
        ("to_cpu", lambda: x.to("cpu"), True),
        ("copy_to_cpu", lambda: destination.copy_(x), True),
        ("cuda_item", lambda: x[0].item(), True),
        ("cuda_tolist", lambda: x.tolist(), True),
        ("device_sync", lambda: torch.cuda.synchronize(), True),
        ("stream_sync", lambda: torch.cuda.current_stream().synchronize(), True),
        ("event_sync", lambda: event.synchronize(), True),
        ("generic_event_sync", lambda: generic_event.synchronize(), True),
        ("generic_stream_sync", lambda: generic_stream.synchronize(), True),
        ("cuda_bool", lambda: bool(x[0]), True),
        ("cpu_scalar", lambda: torch.tensor(6).item(), False),
        ("gpu_operation", lambda: x + 1, False),
        ("cpu_buffer_allocation", lambda: torch.empty_like(x, device="cpu", pin_memory=True), False),
        ("async_output_copy", lambda: destination.copy_(x, non_blocking=True), False),
        ("async_output_to", lambda: x.to("cpu", non_blocking=True), False),
    ]
    records = []
    for inference in (False, True):
        for name, operation, rejected in cases:
            observer = HandoffObserver()
            with observer.observe():
                with torch.inference_mode(inference):
                    result = operation()
            torch.cuda.synchronize()  # Test consumer, outside handoff.
            assert bool(observer.violations) == rejected, (inference, name, observer.violations)
            records.append({"case": name, "inference_mode": inference,
                            "expected_rejected": rejected,
                            "violations": observer.violations,
                            "transfers": observer.transfers})
    print(json.dumps(records, indent=2))
    print("HANDOFF_OBSERVER_REGRESSIONS=PASS")


if __name__ == "__main__":
    main()
