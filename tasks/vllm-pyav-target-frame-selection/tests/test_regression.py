from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path

import numpy as np
import pytest

from video_verifier_support import (
    assert_numbered_targets,
    assert_public_parity,
    load_video,
    numbered_h264,
)


PUBLIC_VIDEO = Path("/opt/video/sintel-trailer.mp4")
PUBLIC_VIDEO_SHA256 = "b670602fa00934ca27c4351bb0efe7ea7a07fae57284e44226025eeed7c51254"


@lru_cache(maxsize=1)
def _public_video() -> bytes:
    return PUBLIC_VIDEO.read_bytes()


def test_public_video_fixture_is_untampered_and_attributed():
    data = _public_video()
    assert hashlib.sha256(data).hexdigest() == PUBLIC_VIDEO_SHA256
    attribution = PUBLIC_VIDEO.with_name("ATTRIBUTION.txt").read_text()
    assert "CC-BY-3.0" in attribution
    assert "Blender Foundation" in attribution


@pytest.mark.parametrize("num_frames", [5, 8, 13])
def test_sintel_public_loader_returns_matching_moments(num_frames):
    frames, targets = assert_public_parity(
        _public_video(), num_frames=num_frames, max_mae=2.0
    )
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
def test_numbered_h264_uniform_sampling_through_public_loader(profile):
    num_frames, fps, gop, width, height, max_b_frames, sampled = profile
    data = numbered_h264(num_frames, fps, gop, width, height, max_b_frames)
    frames, targets = assert_public_parity(data, num_frames=sampled)
    assert_numbered_targets(frames, targets)


@pytest.mark.parametrize(
    ("profile", "sample_fps", "max_duration"),
    [
        ((73, 24, 73, 96, 72, 0), 3, 100),
        ((117, 30, 47, 96, 72, 2), 4, 2),
        ((97, 24, 24, 112, 80, 2), 2, 3),
    ],
)
def test_dynamic_loader_fps_and_duration_paths(profile, sample_fps, max_duration):
    data = numbered_h264(*profile)
    frames, targets = assert_public_parity(
        data,
        loader_name="opencv_dynamic",
        fps=sample_fps,
        max_duration=max_duration,
    )
    assert targets == sorted(set(targets))
    assert_numbered_targets(frames, targets)


@pytest.mark.parametrize("requested", [-1, 20])
def test_short_video_all_frame_behavior(requested):
    data = numbered_h264(7, 12, 7, 96, 72, 0)
    frames, targets = assert_public_parity(data, num_frames=requested)
    assert targets == list(range(7))
    assert len(frames) == 7


@pytest.mark.parametrize(("num_frames", "sample_fps"), [(17, 4), (40, 5)])
def test_uniform_loader_combines_frame_and_fps_limits(num_frames, sample_fps):
    data = numbered_h264(89, 24, 31, 112, 80, 2)
    frames, targets = assert_public_parity(
        data, num_frames=num_frames, fps=sample_fps
    )
    assert 1 <= len(targets) <= num_frames
    assert_numbered_targets(frames, targets)


def test_concurrent_public_pyav_decodes_do_not_share_state():
    data = numbered_h264(103, 25, 37, 112, 80, 2)

    def decode(sampled):
        frames, metadata = load_video(data, backend="pyav", num_frames=sampled)
        targets = list(metadata["frames_indices"])
        assert metadata["video_backend"] == "pyav"
        assert_numbered_targets(frames, targets)
        return sampled, targets

    sample_counts = [5, 7, 9, 12, 5, 9]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(decode, sample_counts))
    assert [sampled for sampled, _ in results] == sample_counts


def test_pyav_public_path_works_without_opencv_importable():
    script = r'''import sys
sys.modules["cv2"] = None
sys.modules["cv2.videoio_registry"] = None
from pathlib import Path
from vllm.multimodal.video import VIDEO_LOADER_REGISTRY
data = Path("/opt/video/sintel-trailer.mp4").read_bytes()
frames, metadata = VIDEO_LOADER_REGISTRY.load("opencv").load_bytes(
    data, num_frames=8, backend="pyav"
)
assert len(frames) == 8
assert metadata["video_backend"] == "pyav"
'''
    environment = os.environ.copy()
    environment["PYTHONPATH"] = "/workspace/vllm"
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd="/workspace/vllm",
        env=environment,
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
