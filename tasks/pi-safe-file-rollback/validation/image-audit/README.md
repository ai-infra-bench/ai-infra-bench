# Agent image audit

`audit_image.py` inspects the final filesystem, Git object graph, node-user access,
and every unique filesystem layer exported by Docker. Repeated empty layers are
scanned once. The audit reads historical layer contents, including files deleted
by later layers, instead of relying only on the final checkout.

The scan checks known private task filenames and answer/verifier markers.
Additional private strings can be supplied through repeated `--private-marker`
arguments; findings identify their input index without reproducing the string.
`summary.json` records the audited image identity, results and script digest.

The node user can edit production sources and run the built CLI offline.
Dependency files are root-owned, but the writable workspace parent permits their
replacement, so the verifier must still validate pinned dependency digests.
Pattern scans establish the recorded checks, not absence of every possible
encoded secret or every future solution reference.

Run `python3 audit_image.py IMAGE --output report.json` on a host with Docker.
The image is inspected through temporary containers; its layers are not changed.
