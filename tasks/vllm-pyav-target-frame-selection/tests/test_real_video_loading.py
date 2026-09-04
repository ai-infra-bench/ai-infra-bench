#!/usr/bin/env python3
"""Exercise the public registry with real video bytes and concurrent decodes."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from video_verifier_support import (
    assert_numbered_targets,
    assert_public_parity,
    expected_dynamic_indices,
    expected_uniform_indices,
    load_video,
    numbered_h264,
)


def main() -> int:
    try:
        public = Path("/opt/video/sintel-trailer.mp4").read_bytes()
        sintel_frames, sintel_targets = assert_public_parity(
            public, num_frames=8, max_mae=2.0
        )
        assert sintel_targets == expected_uniform_indices(public, num_frames=8)

        generated = numbered_h264(109, 25, 41, 112, 80, 2)

        def decode(sampled):
            frames, metadata = load_video(
                generated, backend="pyav", num_frames=sampled
            )
            targets = list(metadata["frames_indices"])
            assert targets == expected_uniform_indices(generated, num_frames=sampled)
            assert_numbered_targets(frames, targets)
            return sampled, targets

        counts = [5, 8, 11, 14]
        with ThreadPoolExecutor(max_workers=4) as pool:
            concurrent = list(pool.map(decode, counts))

        dynamic_frames, dynamic_targets = assert_public_parity(
            generated,
            loader_name="opencv_dynamic",
            fps=3,
            max_duration=2,
        )
        assert dynamic_targets == expected_dynamic_indices(
            generated, fps=3, max_duration=2
        )
        assert_numbered_targets(dynamic_frames, dynamic_targets)

        nemotron_frames, nemotron_targets = assert_public_parity(
            generated,
            loader_name="nemotron_vl",
            num_frames=9,
        )
        assert nemotron_targets == expected_uniform_indices(generated, num_frames=9)
        assert_numbered_targets(nemotron_frames, nemotron_targets)
        print(
            {
                "entrypoint": "VIDEO_LOADER_REGISTRY.load(...).load_bytes",
                "public_video_frames": len(sintel_frames),
                "public_video_targets": sintel_targets,
                "concurrent_decodes": len(concurrent),
                "generated_sample_counts": counts,
                "dynamic_frames": len(dynamic_frames),
                "nemotron_frames": len(nemotron_frames),
            },
            flush=True,
        )
        return 0
    except Exception as exc:
        print(
            {
                "error": type(exc).__name__,
                "message": str(exc).splitlines()[0] if str(exc) else "no message",
            },
            flush=True,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
