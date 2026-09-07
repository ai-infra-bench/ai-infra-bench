"""Independent non-zero timeline case outside the grading inventory."""

from video_verifier_support import (
    assert_numbered_targets,
    assert_public_parity,
    expected_uniform_indices,
    numbered_h264,
)


def main() -> None:
    data = numbered_h264(
        97,
        25,
        37,
        128,
        96,
        2,
        start_pts=437,
    )
    frames, targets = assert_public_parity(
        data,
        num_frames=17,
        fps=4,
    )
    assert targets == expected_uniform_indices(data, num_frames=17, fps=4)
    assert_numbered_targets(frames, targets)
    print({
        "nonzero_start_pts": 437,
        "selected_frames": len(frames),
        "targets": targets,
        "passed": True,
    })


if __name__ == "__main__":
    main()
