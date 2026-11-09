"""Trusted fixture construction and ground truth for the verifier.

This module never imports vLLM. Fixtures are real files produced with the
ffmpeg CLI from frame-labeled sources; ground truth comes from a sequential
ffmpeg CLI decode, which follows the clip's presentation timeline.
"""

from __future__ import annotations

import fractions
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

W, H = 160, 120


def label_frame(index: int) -> np.ndarray:
    rows, cols = np.indices((H, W))
    img = np.empty((H, W, 3), dtype=np.uint8)
    img[..., 0] = (cols * 2 + index * 3) % 256
    img[..., 1] = (rows * 3 + index * 5) % 256
    img[..., 2] = ((rows + cols) + index * 7) % 256
    img[:20, :60] = 128
    for k, digit in enumerate((index // 256 % 16, index // 16 % 16, index % 16)):
        img[2:18, 2 + 20 * k : 18 + 20 * k] = 40 + 11 * digit
    return img


def read_label(frame: np.ndarray) -> int:
    value = 0
    for k in range(3):
        level = float(np.median(frame[5:15, 5 + 20 * k : 15 + 20 * k]))
        value = value * 16 + min(15, max(0, round((level - 40) / 11)))
    return value


def _ffmpeg(args: list[str], stdin: bytes | None = None, stdout=None) -> None:
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-y", *args],
        input=stdin,
        stdout=stdout,
        check=True,
        timeout=300,
    )


def ffprobe_stream(path: Path) -> dict:
    out = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=nb_frames,avg_frame_rate,duration",
            "-of", "json", str(path),
        ],
        capture_output=True, text=True, check=True, timeout=120,
    ).stdout
    streams = json.loads(out).get("streams") or [{}]
    return streams[0]


def nominal_fps(path: Path) -> float:
    rate = ffprobe_stream(path).get("avg_frame_rate", "0/1")
    return float(fractions.Fraction(rate)) if rate not in ("0/0", "") else 0.0


def container_duration(path: Path) -> float:
    """The container's presentation duration in seconds, as ffprobe reports it."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True, timeout=120,
    ).stdout
    return float(json.loads(out)["format"]["duration"])


def header_frames(path: Path) -> int:
    value = ffprobe_stream(path).get("nb_frames")
    return int(value) if value not in (None, "N/A") else 0


def decode_frames(path: Path) -> np.ndarray:
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-i", str(path),
         "-map", "0:v:0", "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True, check=True, timeout=300,
    )
    frame_size = W * H * 3
    data = proc.stdout
    if len(data) % frame_size:
        raise RuntimeError(f"unexpected decode size for {path.name}")
    return np.frombuffer(data, dtype=np.uint8).reshape(-1, H, W, 3)


def visible_labels(path: Path) -> list[int]:
    return [read_label(f) for f in decode_frames(path)]


X264 = ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-threads", "1"]


@dataclass(frozen=True)
class Source:
    frames: int
    fps: int
    gop: int
    bframes: int = 2


def encode_source(path: Path, src: Source) -> None:
    raw = b"".join(label_frame(i).tobytes() for i in range(src.frames))
    _ffmpeg(
        ["-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(src.fps),
         "-i", "pipe:0", *X264, "-bf", str(src.bframes), "-g", str(src.gop),
         "-keyint_min", str(src.gop), "-sc_threshold", "0", "-pix_fmt", "yuv420p",
         str(path)],
        stdin=raw,
    )


def copy_trim(src: Path, out: Path, start: float, length: float) -> None:
    """The lossless cut from the task statement."""
    _ffmpeg(["-ss", repr(start), "-i", str(src), "-t", repr(length), "-c", "copy", str(out)])


def reencode_copy(src: Path, out: Path) -> None:
    """Re-encode exactly the frames that play, giving a file with a correct header."""
    _ffmpeg(["-i", str(src), "-fps_mode", "passthrough", *X264, "-crf", "12", "-bf", "2",
             "-pix_fmt", "yuv420p", str(out)])


def rebased_remux(src: Path, out: Path, start_frame: int, fps: int) -> None:
    """Stream-copy remux that rebases timestamps past the first keyframe.

    Independently re-implemented from the description of the reproduction in
    vLLM PR #48608: lead-in packets keep negative timestamps, so the muxer
    records an edit list. Uses PyAV muxing only; no vLLM code.
    """
    import av

    with av.open(str(src)) as source, av.open(str(out), mode="w", format="mp4") as sink:
        in_stream = source.streams.video[0]
        out_stream = sink.add_stream_from_template(in_stream)
        shift = round(start_frame / fps / in_stream.time_base)
        for packet in source.demux(in_stream):
            if packet.pts is None or packet.dts is None:
                continue
            packet.pts -= shift
            packet.dts -= shift
            packet.stream = out_stream
            sink.mux(packet)


def make_normal(name: str, path: Path, workdir: Path) -> None:
    """Real untrimmed (or already-correct) files from common tools."""
    def raw(n):
        return b"".join(label_frame(i).tobytes() for i in range(n))

    def src(fps):
        return ["-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "pipe:0"]

    x = [*X264, "-pix_fmt", "yuv420p"]
    recipes = {
        "mp4_bf2": lambda: _ffmpeg([*src(30), *x, "-bf", "2", str(path)], raw(300)),
        "mp4_bf0": lambda: _ffmpeg([*src(30), *x, "-bf", "0", str(path)], raw(300)),
        "mp4_29_97": lambda: _ffmpeg([*src("30000/1001"), *x, str(path)], raw(300)),
        "mp4_with_audio": lambda: _ffmpeg([*src(30), "-f", "lavfi", "-i", "sine=d=10.3", *x,
                                           "-c:a", "aac", "-shortest", str(path)], raw(300)),
        "mov_h264": lambda: _ffmpeg([*src(30), *x, str(path)], raw(300)),
        "mp4_fragmented": lambda: _ffmpeg([*src(30), *x, "-movflags", "frag_keyframe+empty_moov", str(path)], raw(300)),
        "mp4_faststart": lambda: _ffmpeg([*src(30), *x, "-movflags", "+faststart", str(path)], raw(300)),
        "mp4_hevc": lambda: _ffmpeg([*src(30), "-c:v", "libx265", "-pix_fmt", "yuv420p",
                                     "-x265-params", "log-level=error:pools=1:frame-threads=1", str(path)], raw(300)),
        "mp4_mpeg4": lambda: _ffmpeg([*src(30), "-c:v", "mpeg4", "-q:v", "3", str(path)], raw(300)),
        "avi_mpeg4": lambda: _ffmpeg([*src(30), "-c:v", "mpeg4", "-q:v", "3", str(path)], raw(300)),
        "mp4_mpdecimate": lambda: _ffmpeg([*src(30), "-vf", "mpdecimate", "-fps_mode", "vfr", *x, str(path)], raw(300)),
        # 3 s at 30 fps, then every third frame (10 fps) for 3 s. A single input
        # keeps the last frame inside the edit list with every ffmpeg tested;
        # the two-input concat form hides it under ffmpeg 7.1.
        "mp4_vfr_30_then_10": lambda: _ffmpeg(
            ["-f", "lavfi", "-i", f"testsrc=s={W}x{H}:r=30:d=6",
             "-vf", "select='lt(n\\,90)+gte(n\\,90)*not(mod(n-90\\,3))'",
             "-fps_mode", "vfr", *x, str(path)]),
        "mp4_vfr_gap": lambda: _ffmpeg(
            ["-f", "lavfi", "-i", f"testsrc=s={W}x{H}:r=30:d=4", "-vf", "select='not(between(t,1,2))',setpts=PTS",
             "-fps_mode", "vfr", *x, str(path)]),
    }
    if name in recipes:
        recipes[name]()
        return
    base = workdir / f"{name}.src.mp4"
    if name == "mp4_reencoded_cut":
        encode_source(base, Source(300, 30, 60))
        _ffmpeg(["-ss", "2.5", "-i", str(base), "-t", "3", *x, str(path)])
    elif name == "mp4_copy_cut_on_keyframe":
        encode_source(base, Source(300, 30, 60))
        copy_trim(base, path, 2.0, 3)
    elif name == "mp4_remuxed_from_mkv":
        mkv = workdir / f"{name}.src.mkv"
        _ffmpeg([*src(30), *x, str(mkv)], raw(300))
        _ffmpeg(["-i", str(mkv), "-c", "copy", str(path)])
    else:
        raise KeyError(name)
