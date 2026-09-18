# Rollout hardening evidence

Raw A100 records are preserved. Seven passing control `verification.json`
files contain the JSON report followed by `ENCODER_CACHE_VERIFIER=PASS`;
parse the leading JSON object or read as a log. This is their actual captured
output, not a fabricated success record. Scores and completed stages were
checked separately. See ../../rollout-review.md for scope and conclusions.

Archive naming correction during 1.3.4 evidence review: seven successful
`full-control-matrix/*/verification.json` captures contain a JSON object followed
by `ENCODER_CACHE_VERIFIER=PASS`. They are stored as `verification.log` now;
raw bytes and SHA-256 values are unchanged, and the inventory paths are updated.
