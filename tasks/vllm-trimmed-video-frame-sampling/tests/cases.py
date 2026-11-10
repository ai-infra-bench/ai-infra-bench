"""Declarative case inventory shared by the verifier and the JUnit checker."""

from __future__ import annotations

from videolab import Source

SOURCES = {
    "s60": Source(300, 30, 60),
    "s250": Source(360, 30, 250),
    "s48_25fps": Source(200, 25, 48),
    "s120": Source(240, 30, 120),
    "s90_bf0": Source(240, 30, 90, bframes=0),
    "s150_single_gop": Source(150, 30, 150),
}

# name -> (source, start seconds, length seconds); every one is a real -c copy cut.
TRIMS = {
    "mild": ("s60", 2.5, 3.0),
    "one_frame_lead_in": ("s60", 61 / 30, 3.0),
    "severe": ("s250", 7.0, 2.0),
    "fps25": ("s48_25fps", 3.3, 2.5),
    "very_short": ("s120", 3.0, 0.4),
    "no_bframes": ("s90_bf0", 4.1, 2.0),
}
# Independently derived trims (rubric step 11): a cut of an already-cut clip,
# and a stream-copy remux with rebased timestamps (another tool's output shape).
DERIVED = {
    "trim_of_trim": ("mild", 1.2, 1.5),
    "rebased_remux": ("s150_single_gop", 100),
}

NORMAL = [
    "mp4_bf2", "mp4_bf0", "mp4_29_97", "mp4_with_audio", "mov_h264",
    "mp4_fragmented", "mp4_faststart", "mp4_hevc", "mp4_mpeg4", "avi_mpeg4",
    "mp4_mpdecimate", "mp4_vfr_30_then_10", "mp4_vfr_gap", "mp4_reencoded_cut",
    "mp4_copy_cut_on_keyframe", "mp4_remuxed_from_mkv",
]
NORMAL_EXT = {"mov_h264": ".mov", "avi_mpeg4": ".avi"}

BACKENDS = ["opencv", "pyav"]
COUNTS = ["4", "8", "16", "all", "over"]  # "over" = visible + 37

# Loader x codec pairs checked differentially against Base on a re-encoded copy.
FPS_LOADERS = [
    ("opencv_dynamic", "opencv"),
    ("qwen2_vl", "opencv"),
    ("qwen3_vl", "opencv"),
    ("qwen2_vl", "pyav"),
    ("qwen3_vl", "pyav"),
]
FPS_LOADER_TRIMS = ["severe", "mild", "one_frame_lead_in", "very_short"]
# Base's opencv_dynamic raises on any clip shorter than one 2 fps sample
# interval (also on correctly re-encoded copies), so that pair is not scored.
FPS_LOADER_SKIP = {("very_short", "opencv_dynamic", "opencv")}
RECOVERY_TRIMS = ["severe", "one_frame_lead_in"]
RECOVERY_COUNTS = ["8", "all"]
PRESERVED_LOADERS = [("opencv_dynamic", "opencv"), ("qwen3_vl", "pyav")]
PRESERVED_LOADER_FILES = ["mp4_bf2", "mp4_29_97", "mp4_fragmented", "mp4_copy_cut_on_keyframe"]


def generic_trim_params():
    return [(t, b, c) for t in TRIMS for b in BACKENDS for c in COUNTS]


def generic_fps_params():
    return [(t, b) for t in ("mild", "severe") for b in BACKENDS]


def fps_loader_params():
    return [
        (t, loader, codec)
        for t in FPS_LOADER_TRIMS
        for loader, codec in FPS_LOADERS
        if (t, loader, codec) not in FPS_LOADER_SKIP
    ]


def recovery_params():
    return [(t, c) for t in RECOVERY_TRIMS for c in RECOVERY_COUNTS]


# Preserved pairs where Base itself does not load the file correctly, verified
# with labelled frames in the task image. The symptoms differ by file (returned
# frames that frames_indices does not name; frames repeated or skipped at -1)
# and are not attributed to a single cause. A correct fix may change these
# loads, so they are not held to Base's output. The verifier also re-checks at
# run time that Base is correct on every scored pair.
BASE_INCORRECT_PRESERVED = {
    ("mp4_fragmented", "opencv", "pyav", "8"),
    ("mp4_fragmented", "opencv", "pyav", "all"),
    ("mp4_fragmented", "qwen3_vl", "pyav", "8"),
    ("avi_mpeg4", "opencv", "pyav", "all"),
    ("mp4_mpdecimate", "opencv", "pyav", "8"),
    ("mp4_mpdecimate", "opencv", "pyav", "all"),
    ("mp4_vfr_30_then_10", "opencv", "pyav", "8"),
    ("mp4_vfr_30_then_10", "opencv", "pyav", "all"),
    ("mp4_vfr_gap", "opencv", "pyav", "8"),
    ("mp4_vfr_gap", "opencv", "pyav", "all"),
    ("mp4_remuxed_from_mkv", "opencv", "pyav", "8"),
    ("mp4_remuxed_from_mkv", "opencv", "pyav", "all"),
}


def preserved_params():
    out = [(n, "opencv", b, c) for n in NORMAL for b in BACKENDS for c in ("8", "all")]
    out += [(n, loader, codec, "8") for n in PRESERVED_LOADER_FILES for loader, codec in PRESERVED_LOADERS]
    return [p for p in out if p not in BASE_INCORRECT_PRESERVED]


def no_pyav_params():
    return [("severe", "opencv", "8"), ("one_frame_lead_in", "opencv", "all"), ("severe", "opencv_dynamic", "8")]


def derived_params():
    return [(d, b, c) for d in DERIVED for b in BACKENDS for c in ("8", "all")]


def _id(*parts) -> str:
    return "-".join(str(p) for p in parts)


def expected_test_names() -> set[str]:
    names = {"test_fixtures_are_real_trims_and_untrimmed_files"}
    names |= {f"test_generic_loader_on_trim[{_id(*p)}]" for p in generic_trim_params()}
    names |= {f"test_generic_loader_fps_sampling_on_trim[{_id(*p)}]" for p in generic_fps_params()}
    names |= {f"test_fps_loaders_match_reencoded_clip[{_id(*p)}]" for p in fps_loader_params()}
    names |= {f"test_frame_recovery_matches_reencoded_clip[{_id(*p)}]" for p in recovery_params()}
    names |= {f"test_untrimmed_and_correct_videos_unchanged[{_id(*p)}]" for p in preserved_params()}
    names |= {f"test_opencv_without_pyav[{_id(*p)}]" for p in no_pyav_params()}
    names |= {f"test_independently_derived_trims[{_id(*p)}]" for p in derived_params()}
    return names
