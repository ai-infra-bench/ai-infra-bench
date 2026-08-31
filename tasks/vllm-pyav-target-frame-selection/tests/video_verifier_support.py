"""Hidden real-video fixtures and behavior assertions for the verifier."""

from __future__ import annotations

import io
from functools import lru_cache

import av
import cv2
import numpy as np

from vllm.multimodal.video import VIDEO_LOADER_REGISTRY


@lru_cache(maxsize=None)
def numbered_h264(
    num_frames: int,
    fps: int,
    gop_size: int,
    width: int,
    height: int,
    max_b_frames: int,
) -> bytes:
    """Encode a real H.264 clip with motion and a visible frame marker."""
    buffer = io.BytesIO()
    with av.open(buffer, mode="w", format="mp4") as container:
        stream = container.add_stream("h264", rate=fps)
        stream.width = width
        stream.height = height
        stream.pix_fmt = "yuv420p"
        stream.codec_context.gop_size = gop_size
        stream.codec_context.max_b_frames = max_b_frames
        stream.codec_context.options = {
            "x264-params": f"scenecut=0:keyint={gop_size}:min-keyint={gop_size}"
        }

        rows, cols = np.indices((height, width))
        for frame_index in range(num_frames):
            image = np.empty((height, width, 3), dtype=np.uint8)
            image[:, :, 0] = (cols * 2 + frame_index * 3) % 256
            image[:, :, 1] = (rows * 3 + frame_index * 5) % 256
            image[:, :, 2] = ((rows + cols) * 2 + frame_index * 7) % 256
            square_x = (frame_index * 5) % (width - 18)
            square_y = (frame_index * 3) % (height - 18)
            image[square_y : square_y + 18, square_x : square_x + 18] = (
                255,
                240,
                32,
            )
            image[:18, :18] = frame_index
            cv2.putText(
                image,
                f"{frame_index:03d}",
                (24, height - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )
            frame = av.VideoFrame.from_ndarray(image, format="rgb24")
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    return buffer.getvalue()


def load_video(data: bytes, *, loader_name="opencv", backend, **kwargs):
    loader = VIDEO_LOADER_REGISTRY.load(loader_name)
    return loader.load_bytes(data, backend=backend, **kwargs)


def assert_public_parity(data: bytes, *, loader_name="opencv", max_mae=2.0, **kwargs):
    opencv_frames, opencv_metadata = load_video(
        data, loader_name=loader_name, backend="opencv", **kwargs
    )
    pyav_frames, pyav_metadata = load_video(
        data, loader_name=loader_name, backend="pyav", **kwargs
    )
    assert opencv_metadata["video_backend"] == f"opencv{_suffix(loader_name)}"
    assert pyav_metadata["video_backend"] == f"pyav{_suffix(loader_name)}"
    assert list(pyav_metadata["frames_indices"]) == list(
        opencv_metadata["frames_indices"]
    )
    assert pyav_frames.shape == opencv_frames.shape
    assert pyav_frames.dtype == opencv_frames.dtype == np.uint8
    if len(pyav_frames):
        per_frame_mae = np.abs(
            pyav_frames.astype(np.int16) - opencv_frames.astype(np.int16)
        ).mean(axis=(1, 2, 3))
        assert np.all(per_frame_mae <= max_mae), per_frame_mae.tolist()
    return pyav_frames, list(pyav_metadata["frames_indices"])


def _suffix(loader_name: str) -> str:
    return "_dynamic" if loader_name == "opencv_dynamic" else ""


def decoded_markers(frames: np.ndarray) -> list[int]:
    return [int(np.median(frame[2:16, 2:16])) for frame in frames]


def assert_numbered_targets(frames: np.ndarray, targets: list[int]):
    markers = decoded_markers(frames)
    assert len(markers) == len(targets)
    assert len(set(markers)) == len(markers)
    for marker, target in zip(markers, targets):
        assert abs(marker - target) <= 8, (marker, target, markers, targets)
