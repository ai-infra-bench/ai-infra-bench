"""Hidden real-video fixtures and behavior assertions for the verifier."""

from __future__ import annotations

import io
import math
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


def _pyav_source_metadata(data: bytes) -> tuple[int, float, float]:
    with av.open(io.BytesIO(data)) as container:
        stream = container.streams.video[0]
        total_frames = stream.frames or 0
        source_fps = float(stream.average_rate) if stream.average_rate else 0.0
        duration = (
            float(stream.duration * stream.time_base) if stream.duration else 0.0
        )
    if total_frames == 0 and duration > 0 and source_fps > 0:
        total_frames = int(duration * source_fps)
    return total_frames, source_fps, duration


def expected_uniform_indices(
    data: bytes, *, num_frames: int = -1, fps: int = -1
) -> list[int]:
    """Compute the existing uniform-sampling contract independently."""
    total_frames, _, duration = _pyav_source_metadata(data)
    sample_count = total_frames
    if num_frames > 0:
        sample_count = min(num_frames, total_frames)
    if fps > 0:
        sample_count = min(sample_count, math.floor(duration * fps))
    sample_count = max(1, sample_count)
    if sample_count == total_frames:
        return list(range(sample_count))
    return np.linspace(0, total_frames - 1, sample_count, dtype=int).tolist()


def expected_dynamic_indices(
    data: bytes, *, fps: int, max_duration: int
) -> list[int]:
    """Compute the existing duration-aware sampling contract independently."""
    total_frames, source_fps, duration = _pyav_source_metadata(data)
    max_frame_idx = total_frames - 1
    if not duration and source_fps > 0:
        duration = round(max_frame_idx / source_fps) + 1

    if duration <= max_duration:
        sample_count = math.floor(duration * fps)
        return sorted(
            {
                min(max_frame_idx, math.ceil(i * source_fps / fps))
                for i in range(sample_count)
            }
        )

    sample_count = max_duration * fps
    if sample_count >= total_frames:
        return list(range(total_frames))
    target_seconds = np.linspace(0, duration, sample_count, endpoint=True)
    return sorted(
        {
            min(max_frame_idx, math.ceil(second * source_fps))
            for second in target_seconds
        }
    )


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
    _assert_metadata(
        data,
        opencv_metadata,
        expected_backend=f"opencv{_suffix(loader_name)}",
        loader_name=loader_name,
    )
    _assert_metadata(
        data,
        pyav_metadata,
        expected_backend=f"pyav{_suffix(loader_name)}",
        loader_name=loader_name,
    )
    if len(pyav_frames):
        per_frame_mae = np.abs(
            pyav_frames.astype(np.int16) - opencv_frames.astype(np.int16)
        ).mean(axis=(1, 2, 3))
        assert np.all(per_frame_mae <= max_mae), per_frame_mae.tolist()
    return pyav_frames, list(pyav_metadata["frames_indices"])


def _assert_metadata(data: bytes, metadata: dict, *, expected_backend, loader_name):
    required = {
        "total_num_frames",
        "fps",
        "duration",
        "video_backend",
        "frames_indices",
        "do_sample_frames",
    }
    assert required <= metadata.keys()

    expected_total, expected_fps, pyav_duration = _pyav_source_metadata(data)

    expected_duration = pyav_duration
    if expected_backend.startswith("opencv") and expected_fps > 0:
        expected_duration = expected_total / expected_fps

    assert metadata["total_num_frames"] == expected_total
    assert math.isclose(metadata["fps"], expected_fps, rel_tol=0, abs_tol=1e-9)
    assert math.isclose(
        metadata["duration"], expected_duration, rel_tol=0, abs_tol=1e-9
    )
    assert metadata["video_backend"] == expected_backend
    assert metadata["do_sample_frames"] == (
        len(metadata["frames_indices"]) == expected_total
    )
    if loader_name == "nemotron_vl":
        assert metadata["original_video_bytes"] == data


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
