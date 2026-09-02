# Remediation matrix

| ID | Severity | Finding and evidence | Planned change | Validation | Status |
|---|---|---|---|---|---|
| C1 | blocking | New task provenance must preserve the security motivation of predecessor #32746 while isolating PR #42535's performance regression. | Start from size-dependent request latency and keep every non-data URL behavior in scope. | Public benchmark reproduces the 10 MB dispatch gap; real image paths remain correct. | fixed |
| C2 | blocking | Environment and exact cutoff lock are missing. | Build and audit a hardened canonical image. | Lock/digest stability and all isolation gates pass. | fixed |
| C3 | blocking | Verifier and controls are missing. | Measure public sync/async dispatch and cover real decoding, scheme case, HTTP, file, malformed, and unsupported inputs. | Base/Oracle five rounds, a structurally different prefix-helper alternative passes, and partial dispatch fixes fail. | fixed |
| C4 | blocking | Evidence and Harbor records are missing. | Record actual benchmark distributions, hashes, limitations, image, and Harbor IDs. | Evidence audit and Harbor Oracle pass. | fixed |
| C5 | blocking | The first verifier claimed dispatch was payload-size independent, but the upstream fix only removes `urllib3`'s extra full-payload parse; extracting the payload still copies data. Oracle measured about 4.5 ms for 8 MiB versus Base about 30 ms and was incorrectly rejected by a small/large ratio. | Keep source-backed absolute latency gates and remove the false asymptotic-ratio requirement. | Oracle passes the 8 MiB and hidden 6 MiB thresholds; Base fails both generic-parser overhead cases. | fixed |
