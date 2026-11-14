"""Untrusted worker: loads videos through vLLM's public media connector.

Runs as an unprivileged user in a subprocess. It only writes raw frames and the
returned metadata into its output directory; every judgement happens in the
trusted parent. Usage: worker.py REQUESTS_JSON OUTPUT_DIR [--block-av]
"""

import faulthandler
import json
import sys
from pathlib import Path


def main() -> None:
    faulthandler.enable()  # a native crash leaves a Python stack in the worker log
    requests_path, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
    if "--block-av" in sys.argv[3:]:
        sys.modules["av"] = None  # PyAV not installed

    import numpy as np

    import vllm
    from vllm.multimodal.media.connector import MediaConnector

    spec = json.loads(requests_path.read_text())
    (out_dir / "identity.json").write_text(
        json.dumps({"vllm_file": str(Path(vllm.__file__).resolve())})
    )
    for request in spec["requests"]:
        rid = request["id"]
        try:
            connector = MediaConnector(
                media_io_kwargs={"video": request["video_kwargs"]},
                allowed_local_media_path=spec["media_root"],
            )
            media = connector.fetch_video(Path(request["file"]).resolve().as_uri())
            frames, metadata = media.media
            np.save(out_dir / f"{rid}.npy", np.ascontiguousarray(frames, dtype=np.uint8))
            meta = {}
            for key in ("total_num_frames", "fps", "duration", "video_backend",
                        "frames_indices", "do_sample_frames"):
                value = metadata.get(key)
                if key == "frames_indices" and value is not None:
                    value = [int(v) for v in value]
                elif isinstance(value, (np.integer, np.floating, np.bool_)):
                    value = value.item()
                meta[key] = value
            meta["av_imported"] = sys.modules.get("av") is not None
            (out_dir / f"{rid}.json").write_text(json.dumps({"ok": True, "metadata": meta}))
        except Exception as exc:  # recorded and judged by the parent
            (out_dir / f"{rid}.json").write_text(
                json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"[:500]})
            )
    (out_dir / "done.json").write_text(json.dumps({"count": len(spec["requests"])}))


if __name__ == "__main__":
    main()
