import hashlib
import io
from functools import lru_cache
from pathlib import Path

import av
import cv2
import numpy as np
import pytest
from vllm.multimodal.video import VIDEO_LOADER_REGISTRY, VideoBackend


PUBLIC_VIDEO = Path("/opt/video/sintel-trailer.mp4")
PUBLIC_VIDEO_SHA256 = "b670602fa00934ca27c4351bb0efe7ea7a07fae57284e44226025eeed7c51254"


@lru_cache(maxsize=1)
def _public_video() -> bytes:
    return PUBLIC_VIDEO.read_bytes()


@lru_cache(maxsize=None)
def _numbered_video(
    num_frames: int,
    fps: int,
    gop_size: int,
    width: int,
    height: int,
    max_b_frames: int,
) -> bytes:
    """Encode a real H.264 clip with visible frame numbers and motion."""
    buffer = io.BytesIO()
    with av.open(buffer, mode="w", format="mp4") as container:
        stream = container.add_stream("h264", rate=fps)
        stream.width = width
        stream.height = height
        stream.pix_fmt = "yuv420p"
        stream.codec_context.gop_size = gop_size
        stream.codec_context.max_b_frames = max_b_frames
        stream.codec_context.options = {
            "x264-params": (
                f"scenecut=0:keyint={gop_size}:min-keyint={gop_size}"
            )
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


def _decode_public(data: bytes, num_frames: int, backend: str):
    loader = VIDEO_LOADER_REGISTRY.load("opencv")
    return loader.load_bytes(data, num_frames=num_frames, backend=backend)


def _assert_backend_parity(data: bytes, num_frames: int):
    opencv_frames, opencv_metadata = _decode_public(data, num_frames, "opencv")
    pyav_frames, pyav_metadata = _decode_public(data, num_frames, "pyav")

    assert pyav_metadata["video_backend"] == "pyav"
    assert opencv_metadata["video_backend"] == "opencv"
    assert list(pyav_metadata["frames_indices"]) == list(
        opencv_metadata["frames_indices"]
    )
    assert pyav_frames.shape == opencv_frames.shape
    assert pyav_frames.dtype == opencv_frames.dtype == np.uint8
    np.testing.assert_array_equal(pyav_frames, opencv_frames)
    return pyav_frames, list(pyav_metadata["frames_indices"])


def _decoded_markers(frames: np.ndarray) -> list[int]:
    return [int(np.median(frame[2:16, 2:16])) for frame in frames]


def _assert_numbered_targets(frames: np.ndarray, targets: list[int]):
    markers = _decoded_markers(frames)
    assert len(markers) == len(targets)
    assert len(set(markers)) == len(markers)
    for marker, target in zip(markers, targets):
        assert abs(marker - target) <= 8, (marker, target, markers, targets)


def test_public_video_fixture_is_untampered_and_attributed():
    data = _public_video()
    assert hashlib.sha256(data).hexdigest() == PUBLIC_VIDEO_SHA256
    attribution = PUBLIC_VIDEO.with_name("ATTRIBUTION.txt").read_text()
    assert "CC-BY-3.0" in attribution
    assert "Blender Foundation" in attribution


@pytest.mark.parametrize("num_frames", [5, 8, 13])
def test_sintel_matches_opencv_at_sampled_positions(num_frames):
    frames, targets = _assert_backend_parity(_public_video(), num_frames)
    assert len(frames) == len(targets) == num_frames
    assert targets == sorted(targets)


@pytest.mark.parametrize(
    "profile",
    [
        (73, 24, 73, 96, 72, 0, 6),
        (91, 25, 29, 112, 80, 0, 9),
        (117, 30, 47, 96, 72, 2, 7),
        (64, 20, 16, 128, 96, 2, 5),
    ],
)
def test_numbered_h264_uniform_sampling(profile):
    num_frames, fps, gop, width, height, max_b_frames, sampled = profile
    data = _numbered_video(num_frames, fps, gop, width, height, max_b_frames)
    frames, targets = _assert_backend_parity(data, sampled)
    _assert_numbered_targets(frames, targets)


@pytest.mark.parametrize(
    ("profile", "targets"),
    [
        ((73, 24, 73, 96, 72, 0), [0, 7, 22, 51, 70]),
        ((91, 25, 29, 112, 80, 0), [3, 28, 29, 57, 88]),
        ((117, 30, 47, 96, 72, 2), [1, 31, 62, 93, 114]),
    ],
)
def test_numbered_h264_nonuniform_forward_targets(profile, targets):
    data = _numbered_video(*profile)
    with av.open(io.BytesIO(data)) as container:
        source = VideoBackend.get_metadata(container)
        frames, valid_indices = VideoBackend.decode_frames(
            container,
            targets,
            source.original_fps,
            source.duration,
        )

    assert valid_indices == targets
    _assert_numbered_targets(frames, targets)


def test_pyav_backend_does_not_fall_back_to_opencv(monkeypatch):
    data = _numbered_video(79, 23, 79, 96, 72, 0)

    def forbidden_opencv(*args, **kwargs):
        raise AssertionError("PyAV backend delegated decoding to OpenCV")

    monkeypatch.setattr(cv2, "VideoCapture", forbidden_opencv)
    loader = VIDEO_LOADER_REGISTRY.load("opencv")
    frames, metadata = loader.load_bytes(data, num_frames=7, backend="pyav")

    assert metadata["video_backend"] == "pyav"
    _assert_numbered_targets(frames, list(metadata["frames_indices"]))
