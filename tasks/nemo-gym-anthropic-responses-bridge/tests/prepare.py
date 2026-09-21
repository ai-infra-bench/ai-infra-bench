"""Check Harbor's complete-checkout transfer without importing candidate code."""

from pathlib import Path

# The separate environment receives /workspace/Gym at its original source path.
# Collection logs accompany it through Harbor's conventional artifact directory.
# Do not apply solution.patch again: tracked and untracked files are already
# present in the transferred checkout, including files omitted by Git ignores.
status = Path("/logs/artifacts/collection-status.txt")
if not status.is_file() or status.read_text().strip() != "complete":
    raise SystemExit("Missing completed candidate collection")
if not Path("/workspace/Gym").is_dir():
    raise SystemExit("Missing transferred candidate checkout")
