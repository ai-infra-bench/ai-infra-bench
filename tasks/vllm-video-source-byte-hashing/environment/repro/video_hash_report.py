from __future__ import annotations

import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np

from vllm.multimodal.hasher import MultiModalHasher
from vllm.multimodal.media import ImageMediaIO, VideoMediaIO
from vllm.multimodal.parse import MultiModalDataParser


def make_video(path: Path) -> bytes:
    subprocess.run(
        [
            "ffmpeg",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=1280x720:rate=32:duration=2",
            "-c:v",
            "libx264",
            "-g",
            "64",
            "-pix_fmt",
            "yuv420p",
            "-y",
            str(path),
        ],
        check=True,
        timeout=60,
    )
    return path.read_bytes()


def hash_video(video) -> str:
    parsed = MultiModalDataParser().parse_mm_data({"video": [video]})
    item = parsed["video"].get_all_items_for_hash()[0]
    return MultiModalHasher.hash_kwargs(video=item)


def main() -> int:
    path = Path(tempfile.mkdtemp(prefix="video-hash-report-")) / "sample.mp4"
    source = make_video(path)
    io = VideoMediaIO(ImageMediaIO(), num_frames=32)
    first = io.load_bytes(source + b"A")
    second = io.load_bytes(source + b"B")
    first_frames, _ = first
    second_frames, _ = second
    same_frames = np.array_equal(first_frames, second_frames)

    started = time.perf_counter()
    first_hash = hash_video(first)
    source_seconds = time.perf_counter() - started
    second_hash = hash_video(second)

    started = time.perf_counter()
    decoded_hash = MultiModalHasher.hash_kwargs(video=first_frames)
    decoded_seconds = time.perf_counter() - started

    print(f"encoded_bytes={len(source)}")
    print(f"decoded_bytes={first_frames.nbytes}")
    print(f"decoded_frames_equal={same_frames}")
    print(f"encoded_source_changes_hash={first_hash != second_hash}")
    print(f"loaded_hash_seconds={source_seconds:.6f}")
    print(f"decoded_hash_seconds={decoded_seconds:.6f}")
    print(f"loaded_hash={first_hash}")
    print(f"decoded_hash={decoded_hash}")
    correct = (
        same_frames
        and first_hash != second_hash
        and source_seconds < decoded_seconds * 0.5
    )
    print(f"video_source_hash_contract={correct}")
    return 0 if correct else 3


if __name__ == "__main__":
    raise SystemExit(main())
