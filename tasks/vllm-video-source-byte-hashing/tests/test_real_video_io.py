from __future__ import annotations

import json
import tempfile
from pathlib import Path

from verifier_support import (
    hash_loaded_base64,
    hash_loaded_bytes,
    hash_loaded_file,
    make_video,
)


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="video-hash-e2e-"))
    path = root / "sample.mp4"
    source = make_video(path)
    from_bytes, bytes_video = hash_loaded_bytes(source, num_frames=8)
    from_file, file_video = hash_loaded_file(path, num_frames=8)
    from_base64, base64_video = hash_loaded_base64(source, num_frames=8)
    two_frames, _ = hash_loaded_bytes(source, num_frames=2)
    eight_frames, _ = hash_loaded_bytes(source, num_frames=8)
    hashes_equal = from_bytes == from_file == from_base64
    shapes_equal = (
        bytes_video[0].shape == file_video[0].shape == base64_video[0].shape
    )
    sampling_changes_hash = two_frames != eight_frames
    print(
        json.dumps(
            {
                "entrypoint": "VideoMediaIO bytes/file/base64 to public parser and hasher",
                "source_bytes": len(source),
                "sampled_frames": 8,
                "hashes_equal_across_transports": hashes_equal,
                "shapes_equal_across_transports": shapes_equal,
                "sampling_changes_hash": sampling_changes_hash,
            },
            separators=(",", ":"),
        )
    )
    assert hashes_equal
    assert shapes_equal
    assert sampling_changes_hash
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
