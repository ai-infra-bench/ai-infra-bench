from __future__ import annotations

import base64
import subprocess
from pathlib import Path

import numpy as np

from vllm.multimodal.hasher import MultiModalHasher
from vllm.multimodal.media import ImageMediaIO, MediaWithBytes, VideoMediaIO
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
            "testsrc2=size=320x240:rate=12:duration=2",
            "-c:v",
            "libx264",
            "-g",
            "24",
            "-pix_fmt",
            "yuv420p",
            "-y",
            str(path),
        ],
        check=True,
        timeout=60,
    )
    return path.read_bytes()


def video_io(num_frames: int) -> VideoMediaIO:
    return VideoMediaIO(ImageMediaIO(), num_frames=num_frames)


def item_for_hash(video) -> object:
    items = MultiModalDataParser().parse_mm_data({"video": [video]})
    return items["video"].get_all_items_for_hash()[0]


def hash_video(video) -> str:
    return MultiModalHasher.hash_kwargs(video=item_for_hash(video))


def hash_loaded_bytes(data: bytes, *, num_frames: int) -> tuple[str, object]:
    loaded = video_io(num_frames).load_bytes(data)
    return hash_video(loaded), loaded


def hash_loaded_file(path: Path, *, num_frames: int) -> tuple[str, object]:
    loaded = video_io(num_frames).load_file(path)
    return hash_video(loaded), loaded


def hash_loaded_base64(data: bytes, *, num_frames: int) -> tuple[str, object]:
    encoded = base64.b64encode(data).decode()
    loaded = video_io(num_frames).load_base64("video/mp4", encoded)
    return hash_video(loaded), loaded


def manual_video(
    frames: np.ndarray,
    source: bytes,
    *,
    frame_indices: list[int] | None = None,
) -> MediaWithBytes[tuple[np.ndarray, dict]]:
    indices = frame_indices or list(range(len(frames)))
    metadata = {
        "total_num_frames": max(len(frames), len(indices)),
        "fps": 12.0,
        "duration": 2.0,
        "video_backend": "opencv",
        "frames_indices": indices,
        "do_sample_frames": True,
    }
    return MediaWithBytes((frames, metadata), source)
