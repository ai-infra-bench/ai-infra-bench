from __future__ import annotations

import time

import numpy as np
import pytest
from PIL import Image

from vllm.multimodal.hasher import MultiModalHasher
from vllm.multimodal.media import MediaWithBytes
from vllm.multimodal.parse import MultiModalDataParser

from verifier_support import (
    hash_loaded_bytes,
    hash_video,
    item_for_hash,
    make_video,
    manual_video,
    video_io,
)


@pytest.fixture(scope="session")
def encoded_video(tmp_path_factory) -> bytes:
    return make_video(tmp_path_factory.mktemp("video") / "sample.mp4")


def test_short_encoded_source_changes_hash_when_frames_match(encoded_video) -> None:
    first_hash, first = hash_loaded_bytes(encoded_video + b"A", num_frames=8)
    second_hash, second = hash_loaded_bytes(encoded_video + b"B", num_frames=8)
    first_frames, _ = first
    second_frames, _ = second
    assert np.array_equal(first_frames, second_frames)
    assert first_hash != second_hash


def test_long_sources_fall_back_to_smaller_decoded_frames() -> None:
    frames = np.arange(4 * 64 * 64 * 3, dtype=np.uint8).reshape(4, 64, 64, 3)
    size = frames.nbytes + 4096
    first = manual_video(frames, b"A" * size)
    second = manual_video(frames, b"B" * size)
    assert hash_video(first) == hash_video(second)


def test_short_sources_are_part_of_cache_identity() -> None:
    frames = np.zeros((8, 128, 128, 3), dtype=np.uint8)
    first = manual_video(frames, b"source-one")
    second = manual_video(frames, b"source-two")
    assert hash_video(first) != hash_video(second)


def test_sampling_metadata_changes_source_based_hash(encoded_video) -> None:
    hash_two, _ = hash_loaded_bytes(encoded_video, num_frames=2)
    hash_six, _ = hash_loaded_bytes(encoded_video, num_frames=6)
    assert hash_two != hash_six


def test_same_source_and_sampling_are_stable(encoded_video) -> None:
    first, _ = hash_loaded_bytes(encoded_video, num_frames=5)
    second, _ = hash_loaded_bytes(encoded_video, num_frames=5)
    assert first == second


def test_bare_decoded_pixel_changes_remain_visible() -> None:
    first = np.zeros((3, 16, 16, 3), dtype=np.uint8)
    second = first.copy()
    second[1, 4, 5, 2] = 255
    assert hash_video(first) != hash_video(second)


def test_metadata_free_preprocessing_still_returns_frames(encoded_video) -> None:
    _, loaded = hash_loaded_bytes(encoded_video, num_frames=4)
    items = MultiModalDataParser(video_needs_metadata=False).parse_mm_data(
        {"video": [loaded]}
    )
    video = items["video"].get(0)
    assert isinstance(video, np.ndarray)
    assert video.shape[0] == 4


def test_loaded_video_preserves_tuple_indexing(encoded_video) -> None:
    _, loaded = hash_loaded_bytes(encoded_video, num_frames=3)
    frames, metadata = loaded
    assert np.array_equal(loaded[0], frames)
    assert loaded[1] == metadata
    assert metadata["frames_indices"]


def test_base64_jpeg_frame_lists_remain_compatible() -> None:
    frames = np.stack(
        [
            np.full((12, 16, 3), (10, 20, 30), dtype=np.uint8),
            np.full((12, 16, 3), (40, 50, 60), dtype=np.uint8),
        ]
    )
    io = video_io(num_frames=2)
    encoded = io.encode_base64(frames)
    first = io.load_base64("video/jpeg", encoded)
    second = io.load_base64("video/jpeg", encoded)
    loaded_frames, metadata = first
    assert loaded_frames.shape == frames.shape
    assert metadata["video_backend"] == "jpeg_sequence"
    assert metadata["frames_indices"] == [0, 1]
    assert hash_video(first) == hash_video(second)


def test_image_source_byte_hashing_is_unchanged() -> None:
    image = Image.new("RGB", (4, 4), color=(12, 34, 56))
    first = MediaWithBytes(image, b"encoded-image-one")
    second = MediaWithBytes(image, b"encoded-image-two")
    assert MultiModalHasher.hash_kwargs(image=first) != MultiModalHasher.hash_kwargs(
        image=second
    )


def test_short_source_hashing_is_materially_cheaper() -> None:
    frames = np.arange(16 * 512 * 512 * 3, dtype=np.uint8).reshape(
        16, 512, 512, 3
    )
    source = b"x" * (64 * 1024)
    wrapped = MediaWithBytes(frames, source)

    started = time.perf_counter()
    for _ in range(3):
        MultiModalHasher.hash_kwargs(video=wrapped)
    source_seconds = time.perf_counter() - started

    started = time.perf_counter()
    for _ in range(3):
        MultiModalHasher.hash_kwargs(video=frames)
    decoded_seconds = time.perf_counter() - started
    assert source_seconds < decoded_seconds * 0.5, (source_seconds, decoded_seconds)
