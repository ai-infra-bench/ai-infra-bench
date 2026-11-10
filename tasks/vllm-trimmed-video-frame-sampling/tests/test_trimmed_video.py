"""Trusted verifier for trimmed-clip video sampling. Never imports vLLM."""

from __future__ import annotations

import json
import math
import os
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

import cases as C
import videolab as V

TESTS_DIR = Path(__file__).resolve().parent
CANDIDATE_ROOT = Path(os.environ.get("CANDIDATE_VLLM_ROOT", "/workspace/vllm")).resolve()
# Only set when exercising a checkout that is not the installed one (curator probes).
CANDIDATE_PYTHONPATH = os.environ.get("CANDIDATE_PYTHONPATH") or None
BASE_ROOT = Path(os.environ["BASE_VLLM_ROOT"]).resolve()
WORKER_PREFIX = shlex.split(os.environ.get("WORKER_PREFIX", ""))
WORK = Path(os.environ.get("VERIFIER_WORK", tempfile.mkdtemp(prefix="trimmed-video-verifier-")))
STATUS = Path(os.environ.get("VERIFIER_STATUS", str(WORK / "status.json")))
# Wall-clock limit per worker; a whole correct run takes well under a minute.
WORKER_TIMEOUT = int(os.environ.get("VERIFIER_WORKER_TIMEOUT", "1800"))


def _status(**fields) -> None:
    current = json.loads(STATUS.read_text()) if STATUS.exists() else {}
    current.update(fields)
    STATUS.write_text(json.dumps(current, indent=1))


# ----------------------------------------------------------------------------
# Fixture construction (trusted, ffmpeg CLI)
# ----------------------------------------------------------------------------

class Lab:
    def __init__(self) -> None:
        self.media = WORK / "media"
        self.scratch = WORK / "scratch"
        for d in (self.media, self.scratch):
            d.mkdir(parents=True, exist_ok=True)
        self.files: dict[str, Path] = {}
        self.copies: dict[str, Path] = {}
        self.visible: dict[str, list[int]] = {}
        self.header: dict[str, int] = {}
        self.fps: dict[str, float] = {}
        self.duration: dict[str, float] = {}

    def build(self) -> None:
        sources = {}
        for name, spec in C.SOURCES.items():
            sources[name] = self.scratch / f"{name}.mp4"
            V.encode_source(sources[name], spec)
        for name, (src, start, length) in C.TRIMS.items():
            self.files[name] = self.media / f"trim_{name}.mp4"
            V.copy_trim(sources[src], self.files[name], start, length)
        parent, start, length = C.DERIVED["trim_of_trim"]
        self.files["trim_of_trim"] = self.media / "derived_trim_of_trim.mp4"
        V.copy_trim(self.files[parent], self.files["trim_of_trim"], start, length)
        src, start_frame = C.DERIVED["rebased_remux"]
        self.files["rebased_remux"] = self.media / "derived_rebased_remux.mp4"
        V.rebased_remux(sources[src], self.files["rebased_remux"], start_frame, C.SOURCES[src].fps)
        for name in C.NORMAL:
            path = self.media / f"normal_{name}{C.NORMAL_EXT.get(name, '.mp4')}"
            V.make_normal(name, path, self.scratch)
            self.files[name] = path
        for name in set(C.FPS_LOADER_TRIMS) | set(C.RECOVERY_TRIMS):
            self.copies[name] = self.media / f"copy_{name}.mp4"
            V.reencode_copy(self.files[name], self.copies[name])
        for name, path in self.files.items():
            self.header[name] = V.header_frames(path)
            self.fps[name] = V.nominal_fps(path)
            self.visible[name] = V.visible_labels(path)
            self.duration[name] = V.container_duration(path)
            plays = len(self.visible[name])
            if len(set(self.visible[name])) != plays:
                raise RuntimeError(f"fixture {name}: frame labels are not readable after encoding")
            if name in C.TRIMS or name in C.DERIVED:
                # Every scored trim really hides decode lead-in behind its edit list.
                if not self.header[name] > plays > 0:
                    raise RuntimeError(f"fixture {name} is not a hidden-lead-in trim in this environment "
                                       f"(header {self.header[name]}, plays {plays})")
            elif self.header[name] not in (0, plays):
                # The preserved set must already be well-formed with this ffmpeg build:
                # its header counts exactly the frames that play (or has no count).
                raise RuntimeError(f"fixture {name} is not an already-correct file in this environment "
                                   f"(header {self.header[name]}, plays {plays})")
        # opencv_dynamic samples floor(duration * 2) frames. The metadata check accepts
        # either duration convention, so both must give the same sample count on
        # every trim it is compared on.
        for name in C.FPS_LOADER_TRIMS:
            if (name, "opencv_dynamic", "opencv") in C.FPS_LOADER_SKIP:
                continue
            by_frames = math.floor(len(self.visible[name]) / self.fps[name] * 2)
            by_container = math.floor(self.duration[name] * 2)
            if by_frames != by_container:
                raise RuntimeError(f"fixture {name}: duration conventions disagree on the opencv_dynamic "
                                   f"sample count ({by_frames} vs {by_container})")
        for name, path in self.copies.items():
            copy_labels = V.visible_labels(path)
            if copy_labels != self.visible[name]:
                raise RuntimeError(f"re-encoded copy of {name} does not hold the same frames")
        for d in (WORK, self.media):
            d.chmod(0o755)
        for path in self.media.iterdir():
            path.chmod(0o644)


# ----------------------------------------------------------------------------
# Requests and worker execution
# ----------------------------------------------------------------------------

def _num(count: str, visible: int) -> int:
    return {"all": -1, "over": visible + 37}.get(count, None) or int(count)


def _kwargs(loader: str, codec: str, **extra) -> dict:
    return {"video_backend": loader, "backend": codec, **extra}


def build_requests(lab: Lab):
    cand, ref = [], []

    def add(bucket, rid, file, kwargs):
        bucket.append({"id": rid, "file": str(file), "video_kwargs": kwargs})

    for t, b, c in C.generic_trim_params():
        add(cand, f"gen-{t}-{b}-{c}", lab.files[t], _kwargs("opencv", b, num_frames=_num(c, len(lab.visible[t]))))
    for t, b in C.generic_fps_params():
        add(cand, f"genfps-{t}-{b}", lab.files[t], _kwargs("opencv", b, num_frames=-1, fps=2))
    for t, loader, codec in C.fps_loader_params():
        add(cand, f"fpsl-{t}-{loader}-{codec}", lab.files[t], _kwargs(loader, codec, num_frames=8))
        add(ref, f"fpsl-{t}-{loader}-{codec}", lab.copies[t], _kwargs(loader, codec, num_frames=8))
    for t, c in C.recovery_params():
        kw = _kwargs("opencv", "opencv", num_frames=_num(c, len(lab.visible[t])), frame_recovery=True)
        add(cand, f"rec-{t}-{c}", lab.files[t], kw)
        add(ref, f"rec-{t}-{c}", lab.copies[t], kw)
    for n, loader, codec, c in C.preserved_params():
        kw = _kwargs(loader, codec, num_frames=-1 if c == "all" else int(c))
        add(cand, f"keep-{n}-{loader}-{codec}-{c}", lab.files[n], kw)
        add(ref, f"keep-{n}-{loader}-{codec}-{c}", lab.files[n], kw)
    for n in C.OPENCV_UNDECODABLE:
        for c in ("8", "all"):
            add(ref, f"cvcheck-{n}-{c}", lab.files[n], _kwargs("opencv", "opencv", num_frames=-1 if c == "all" else int(c)))
    for t, loader, c in C.no_pyav_params():
        add(cand, f"noav-{t}-{loader}-{c}", lab.files[t], _kwargs(loader, "opencv", num_frames=_num(c, len(lab.visible[t]))))
    for d, b, c in C.derived_params():
        add(cand, f"der-{d}-{b}-{c}", lab.files[d], _kwargs("opencv", b, num_frames=_num(c, len(lab.visible[d]))))
    return cand, ref


def _kill_group(pgid: int) -> None:
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def _kill_worker_user() -> None:
    """Kill every process of the worker user, including ones that left the group (setsid)."""
    if not WORKER_PREFIX or not Path("/proc").is_dir():
        return
    import pwd

    uid = pwd.getpwnam("nobody").pw_uid
    for _ in range(3):
        found = False
        for entry in Path("/proc").iterdir():
            if not entry.name.isdigit():
                continue
            try:
                status = (entry / "status").read_text()
            except OSError:
                continue
            uids = next((line.split()[1:] for line in status.splitlines() if line.startswith("Uid:")), [])
            if str(uid) in uids:
                found = True
                try:
                    os.kill(int(entry.name), signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
        if not found:
            return


def _seal(directory: Path) -> None:
    """Make a finished worker's output read-only to the worker user."""
    if os.geteuid() != 0:
        return
    for path in [directory, *directory.rglob("*")]:
        os.chown(path, 0, 0, follow_symlinks=False)
        if not path.is_symlink():
            path.chmod(0o755 if path.is_dir() else 0o644)


def describe_exit(code: int | None) -> str:
    if code is None:
        return f"timed out after {WORKER_TIMEOUT}s"
    if code < 0:
        try:
            return f"crashed with {signal.Signals(-code).name} (exit {code})"
        except ValueError:
            return f"killed by signal {-code}"
    return f"exit status {code}"


def run_worker(tag: str, requests: list, *, pythonpath: Path | None,
               block_av: bool = False) -> tuple[Path, int | None]:
    out = WORK / f"out-{tag}"
    home = WORK / f"home-{tag}"
    for d in (out, home):
        d.mkdir(parents=True, exist_ok=True)
        d.chmod(0o777)
    spec = WORK / f"requests-{tag}.json"
    spec.write_text(json.dumps({"media_root": str(WORK / "media"), "requests": requests}))
    spec.chmod(0o644)
    worker = WORK / "worker.py"
    if (TESTS_DIR / "worker.py").resolve() != worker.resolve():
        shutil.copy2(TESTS_DIR / "worker.py", worker)
    worker.chmod(0o644)
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(home),
        "XDG_CACHE_HOME": str(home / "cache"),
        "VLLM_CACHE_ROOT": str(home / "vllm-cache"),
        "VLLM_CONFIG_ROOT": str(home / "vllm-config"),
        "VLLM_NO_USAGE_STATS": "1",
        "VLLM_LOGGING_LEVEL": "ERROR",
        "OMP_NUM_THREADS": "2",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    if pythonpath is not None:
        env["PYTHONPATH"] = str(pythonpath)
    cmd = [*WORKER_PREFIX, sys.executable, "-P", str(worker), str(spec), str(out)]
    if block_av:
        cmd.append("--block-av")
    # Own session/process group, so a hang or leftover children never outlive the run.
    proc = subprocess.Popen(cmd, cwd=str(home), env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        stdout, stderr = proc.communicate(timeout=WORKER_TIMEOUT)
        code: int | None = proc.returncode
    except subprocess.TimeoutExpired:
        _kill_group(proc.pid)
        stdout, stderr = proc.communicate()
        code = None
    _kill_group(proc.pid)
    _kill_worker_user()
    _seal(out)
    (WORK / f"worker-{tag}.log").write_text(
        f"exit={code} ({describe_exit(code)})\n--- stdout\n{stdout[-20000:]}\n"
        f"--- stderr\n{stderr[-20000:]}\n"
    )
    return out, code


class Results:
    def __init__(self, run: tuple[Path, int | None], expected_root: Path, count: int) -> None:
        out, code = run
        self.out = out
        identity = out / "identity.json"
        self.identity_ok = False
        self.problem = ""
        exit_note = describe_exit(code)
        if not identity.exists():
            self.problem = f"worker {out.name} did not start loading ({exit_note}; see worker log)"
            return
        vllm_file = Path(json.loads(identity.read_text())["vllm_file"])
        if not vllm_file.is_relative_to(expected_root):
            self.problem = f"worker {out.name} imported vllm from {vllm_file}, expected {expected_root}"
            return
        done = out / "done.json"
        if not done.exists() or json.loads(done.read_text()).get("count") != count:
            self.problem = f"worker {out.name} stopped before finishing every request ({exit_note})"
        elif code != 0:
            # Loading must not crash the process, even after the last request.
            self.problem = f"worker {out.name} finished its requests but then {exit_note}"
        self.identity_ok = True

    def get(self, rid: str):
        assert self.identity_ok and not self.problem, self.problem
        meta_path = self.out / f"{rid}.json"
        assert meta_path.exists(), f"no result for {rid}"
        record = json.loads(meta_path.read_text())
        assert record["ok"], f"{rid} raised {record['error']}"
        frames = np.load(self.out / f"{rid}.npy", allow_pickle=False)
        return frames, record["metadata"]


class ResultSet:
    """Results of one side (candidate or Base), split across per-codec workers."""

    def __init__(self, parts: list[tuple[Results, set[str]]]) -> None:
        self.parts = parts
        self.problem = "; ".join(r.problem for r, _ in parts if r.problem)

    def get(self, rid: str):
        for results, ids in self.parts:
            if rid in ids:
                return results.get(rid)
        raise AssertionError(f"no request {rid}")


def run_side(tag: str, requests: list, pythonpath: Path | None, root: Path) -> ResultSet:
    # The OpenCV backend must work, and keep decoding itself, without PyAV, so
    # every backend="opencv" request runs in a worker where PyAV cannot be imported.
    parts = []
    for codec in ("opencv", "pyav"):
        subset = [r for r in requests if r["video_kwargs"]["backend"] == codec]
        if subset:
            out = run_worker(f"{tag}-{codec}", subset, pythonpath=pythonpath, block_av=codec == "opencv")
            parts.append((Results(out, root, len(subset)), {r["id"] for r in subset}))
    return ResultSet(parts)


def load_problems(frames, meta, visible: list[int], requested: int | None) -> list[str]:
    """Why a load is not a correct load of the clip (empty when it is)."""
    labels = labels_of(frames)
    problems = []
    if any(lab not in set(visible) for lab in labels):
        problems.append("returns frames that do not play")
    elif any(a >= b for a, b in zip(labels, labels[1:])):
        problems.append(f"repeats frames ({len(labels)} returned, {len(set(labels))} distinct)")
    elif [int(i) for i in meta["frames_indices"]] != [visible.index(lab) for lab in labels]:
        problems.append("frames_indices do not name the returned frames")
    if requested is not None:
        want = len(visible) if requested < 0 else min(requested, len(visible))
        if len(labels) != want:
            problems.append(f"returns {len(labels)} frames, expected {want}")
    if meta["total_num_frames"] != len(visible):
        problems.append(f"total_num_frames {meta['total_num_frames']}, plays {len(visible)}")
    return problems


def base_preserved_problems(lab: "Lab", ref: ResultSet) -> list[str]:
    """Preserved pairs are scored only where Base itself loads the file correctly."""
    bad = []
    for name, loader, codec, count in C.preserved_params():
        frames, meta = ref.get(f"keep-{name}-{loader}-{codec}-{count}")
        requested = (-1 if count == "all" else int(count)) if loader == "opencv" else None
        problems = load_problems(frames, meta, lab.visible[name], requested)
        if problems:
            bad.append(f"{name}-{loader}-{codec}-{count}: {'; '.join(problems)}")
    return bad


def opencv_decodes_undecodable(ref: ResultSet) -> list[str]:
    """Files in C.OPENCV_UNDECODABLE that Base's OpenCV backend can load here.

    Their preserved PyAV pairs show the selected backend still decodes only
    while OpenCV cannot decode them; Base must raise or return no frames.
    """
    loaded = []
    for name in C.OPENCV_UNDECODABLE:
        for count in ("8", "all"):
            try:
                frames, _ = ref.get(f"cvcheck-{name}-{count}")
            except AssertionError as exc:
                if "raised" not in str(exc):
                    raise
                continue
            if len(frames):
                loaded.append(f"{name}-{count}: {len(frames)} frames")
    return loaded


_ENVIRONMENT: dict = {}


def environment():
    """Build fixtures and run workers once; a setup failure is re-raised, not retried."""
    if "error" in _ENVIRONMENT:
        raise RuntimeError(f"verifier setup failed: {_ENVIRONMENT['error']}")
    if "value" not in _ENVIRONMENT:
        try:
            _ENVIRONMENT["value"] = _build_environment()
        except Exception as exc:
            _ENVIRONMENT["error"] = f"{type(exc).__name__}: {exc}"
            _status(infrastructure_error=f"verifier setup failed: {_ENVIRONMENT['error']}")
            raise
    return _ENVIRONMENT["value"]


def _build_environment():
    _status(phase="fixtures")
    lab = Lab()
    try:
        lab.build()
    except Exception as exc:
        _status(infrastructure_error=f"fixture construction failed: {type(exc).__name__}: {exc}")
        raise
    cand_req, ref_req = build_requests(lab)
    _status(phase="workers")
    # Base runs first, and each worker's output is sealed (root-owned, read-only)
    # once it exits, so candidate code never runs while Base's results are writable.
    ref = run_side("base", ref_req, BASE_ROOT, BASE_ROOT)
    cand = run_side("candidate", cand_req, CANDIDATE_PYTHONPATH, CANDIDATE_ROOT)
    if ref.problem:
        raise RuntimeError(f"Base reference worker failed: {ref.problem}")
    bad = base_preserved_problems(lab, ref)
    if bad:
        raise RuntimeError(f"preserved pairs Base does not load correctly here: {bad}")
    loaded = opencv_decodes_undecodable(ref)
    if loaded:
        raise RuntimeError(f"Base OpenCV decodes files expected to be OpenCV-undecodable here: {loaded}")
    _status(phase="assertions", candidate_problem=cand.problem)
    return lab, cand, ref


# ----------------------------------------------------------------------------
# Behavioral assertions
# ----------------------------------------------------------------------------

def labels_of(frames: np.ndarray) -> list[int]:
    return [V.read_label(f) for f in frames]


def assert_plays_without_repeats(labels: list[int], visible: list[int]):
    hidden = [lab for lab in labels if lab not in set(visible)]
    assert not hidden, f"returned frames that do not play in the clip: {hidden}"
    assert all(a < b for a, b in zip(labels, labels[1:])), f"repeated or out-of-order frames: {labels}"


def assert_covers_clip(labels: list[int], visible: list[int], samples: int):
    positions = [visible.index(lab) for lab in labels]
    last = len(visible) - 1
    assert positions and positions[0] == 0, f"samples do not start at the clip start: {positions}"
    if samples > 1 and last > 0:
        step = last / (samples - 1)
        assert positions[-1] >= last - math.ceil(step), f"samples stop before the clip end: {positions} of {last}"
        gaps = [b - a for a, b in zip(positions, positions[1:])]
        assert max(gaps) <= 2 * step + 1, f"samples leave part of the clip uncovered: {positions}"


def assert_metadata_describes_clip(meta: dict, frames: np.ndarray, visible: list[int], fps: float,
                                   clip_duration: float):
    indices = meta["frames_indices"]
    total = meta["total_num_frames"]
    assert len(indices) == len(frames), f"{len(indices)} indices for {len(frames)} frames"
    assert all(a < b for a, b in zip(indices, indices[1:])), f"frames_indices not increasing: {indices}"
    assert all(0 <= i < total for i in indices), f"frames_indices outside [0, {total}): {indices}"
    assert total == len(visible), f"total_num_frames={total}, clip plays {len(visible)} frames"
    positions = [visible.index(lab) for lab in labels_of(frames)]
    assert [int(i) for i in indices] == positions, (
        f"frames_indices {indices} do not name the returned frames (clip positions {positions})")
    # Either convention describes the clip: played frames / fps, or the
    # container's presentation duration (which counts the last frame's display time).
    low = (len(visible) - 1) / fps
    high = max(len(visible) / fps, clip_duration) + 1 / fps
    assert low <= meta["duration"] <= high, (
        f"duration={meta['duration']}, clip plays {len(visible)} frames "
        f"({len(visible) / fps:.3f}s; container {clip_duration:.3f}s)")


def check_uniform(frames, meta, visible, requested: int, fps: float, clip_duration: float, backend: str):
    labels = labels_of(frames)
    assert meta["video_backend"] == backend
    assert_plays_without_repeats(labels, visible)
    if 0 < requested <= len(visible):
        assert len(labels) == requested, f"asked for {requested} of {len(visible)} frames, got {len(labels)}"
        assert_covers_clip(labels, visible, requested)
    else:
        assert labels == visible, f"expected every frame once ({len(visible)}), got {len(labels)}: {labels}"
    assert_metadata_describes_clip(meta, frames, visible, fps, clip_duration)


# ----------------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------------

def _pid(*parts) -> str:
    return "-".join(str(p) for p in parts)


def test_fixtures_are_real_trims_and_untrimmed_files():
    # Fixture integrity is checked while building (an infrastructure error if it
    # does not hold); this only confirms the environment came up.
    lab, *_ = environment()
    assert set(lab.files) == {*C.TRIMS, *C.DERIVED, *C.NORMAL}


@pytest.mark.parametrize("trim,backend,count", C.generic_trim_params(), ids=lambda p: str(p))
def test_generic_loader_on_trim(trim, backend, count):
    lab, cand, *_ = environment()
    frames, meta = cand.get(f"gen-{trim}-{backend}-{count}")
    visible = lab.visible[trim]
    check_uniform(frames, meta, visible, _num(count, len(visible)), lab.fps[trim], lab.duration[trim], backend)


@pytest.mark.parametrize("trim,backend", C.generic_fps_params(), ids=lambda p: str(p))
def test_generic_loader_fps_sampling_on_trim(trim, backend):
    lab, cand, *_ = environment()
    frames, meta = cand.get(f"genfps-{trim}-{backend}")
    visible, fps = lab.visible[trim], lab.fps[trim]
    labels = labels_of(frames)
    assert meta["video_backend"] == backend
    assert_plays_without_repeats(labels, visible)
    allowed = math.floor((len(visible) + 2) / fps * 2)
    assert math.floor((len(visible) - 2) / fps * 2) <= len(labels) <= allowed, (
        f"{len(labels)} samples at 2 fps for a {len(visible) / fps:.2f}s clip")
    assert_covers_clip(labels, visible, len(labels))
    assert_metadata_describes_clip(meta, frames, visible, fps, lab.duration[trim])


@pytest.mark.parametrize("trim,loader,codec", C.fps_loader_params(), ids=lambda p: str(p))
def test_fps_loaders_match_reencoded_clip(trim, loader, codec):
    lab, cand, ref = environment()
    rid = f"fpsl-{trim}-{loader}-{codec}"
    ref_frames, ref_meta = ref.get(rid)
    frames, meta = cand.get(rid)
    labels, expected = labels_of(frames), labels_of(ref_frames)
    assert_plays_without_repeats(labels, lab.visible[trim])
    assert labels == expected, (
        f"trimmed clip sampled {labels}; the same frames in a re-encoded file sample {expected} at Base")
    assert meta["video_backend"] == ref_meta["video_backend"]
    assert_metadata_describes_clip(meta, frames, lab.visible[trim], lab.fps[trim], lab.duration[trim])


@pytest.mark.parametrize("trim,count", C.recovery_params(), ids=lambda p: str(p))
def test_frame_recovery_matches_reencoded_clip(trim, count):
    lab, cand, ref = environment()
    rid = f"rec-{trim}-{count}"
    ref_frames, _ = ref.get(rid)
    frames, meta = cand.get(rid)
    labels = labels_of(frames)
    assert_plays_without_repeats(labels, lab.visible[trim])
    assert labels == labels_of(ref_frames)
    assert_metadata_describes_clip(meta, frames, lab.visible[trim], lab.fps[trim], lab.duration[trim])


@pytest.mark.parametrize("name,loader,codec,count", C.preserved_params(), ids=lambda p: str(p))
def test_untrimmed_and_correct_videos_unchanged(name, loader, codec, count):
    _, cand, ref = environment()
    rid = f"keep-{name}-{loader}-{codec}-{count}"
    ref_frames, ref_meta = ref.get(rid)
    frames, meta = cand.get(rid)
    meta = {k: v for k, v in meta.items() if k != "av_imported"}
    ref_meta = {k: v for k, v in ref_meta.items() if k != "av_imported"}
    assert meta == ref_meta, f"metadata changed: {meta} vs Base {ref_meta}"
    assert frames.shape == ref_frames.shape and np.array_equal(frames, ref_frames), "frames changed"


@pytest.mark.parametrize("trim,loader,count", C.no_pyav_params(), ids=lambda p: str(p))
def test_opencv_without_pyav(trim, loader, count):
    lab, cand, _ = environment()
    frames, meta = cand.get(f"noav-{trim}-{loader}-{count}")
    assert meta["av_imported"] is False
    visible = lab.visible[trim]
    if loader == "opencv":
        check_uniform(frames, meta, visible, _num(count, len(visible)), lab.fps[trim], lab.duration[trim], "opencv")
    else:
        labels = labels_of(frames)
        assert_plays_without_repeats(labels, visible)
        assert_covers_clip(labels, visible, len(labels))
        assert_metadata_describes_clip(meta, frames, visible, lab.fps[trim], lab.duration[trim])


@pytest.mark.parametrize("derived,backend,count", C.derived_params(), ids=lambda p: str(p))
def test_independently_derived_trims(derived, backend, count):
    lab, cand, *_ = environment()
    frames, meta = cand.get(f"der-{derived}-{backend}-{count}")
    visible = lab.visible[derived]
    check_uniform(frames, meta, visible, _num(count, len(visible)), lab.fps[derived], lab.duration[derived], backend)
