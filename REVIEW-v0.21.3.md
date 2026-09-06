# UGAS v0.21.3 - Maps / Minimap Historical Byte Integrity

## Governed handoff

- Work order: `UGAS-WO-0213-MM-HBI`
- Repository: `KayzenRoot/ugas`
- Existing PR: `#11` - keep `OPEN`; do not merge
- Branch: `codex/v0.21.0-maps-minimap-runtime-foundation`
- Base: `0bf04cb92e8619ea10cf82af8dbf2d9abe599e05`
- Reviewed corrective history: v0.21.2 at `b80f30074374c539e008ce160846848f1c171d9a`, `CORRECTION_REQUIRED`
- Production: `production_routing=BLOCKED`, `production_approved=false`, `new_generation=0`
- Real map/minimap coverage: `NONE`; fixtures: `TEST_ONLY`

## Corrections delivered

F-09 is corrected by validating the raw bytes of the current HEAD Git object against the approved main Git object. No CRLF/LF normalization participates in the decision. The line-ending-only and append mutation controls both invoke the same reusable validator and record the observed rejection class.

F-10 is corrected by recording separate `authority_commit_sha`, `authority_blob_sha`, `candidate_commit_sha`/`candidate_head_sha`, `candidate_blob_sha`, `authority_sha256` and `candidate_sha256`. The authority blob is `6a44fb35ab99ffc87fc852fab9d65bfb1b5dc608`; the candidate blob is compared explicitly.

The v0.21.2 evidence root remains immutable and is referenced as rejected history. F-06/F-07/F-08 remain preserved. Production routing, real assets and generation remain blocked.

## Validation evidence

- Focused unit tests: 22 tests passed locally.
- Isolated maps/minimap execution: `MAPS_MINIMAP_RASTER_GOVERNANCE_INTEGRITY_TECHNICALLY_QUALIFIED`.
- Hard gates: 22/22 PASS.
- Negative controls: 30/30 PASS, including CRLF-only and append mutation.
- Independent full-slice runs: deterministic, no differences.
- Historical evidence: `docs/evidence/maps-minimap-runtime-v0213/historical-immutability-v0213.json`.
- v0.21.2 rejection record: `docs/evidence/maps-minimap-runtime-v0213/v0.21.2-rejection-correction-record-v0213.json`.

## Required external gate

The executor must push this correction to the same branch and update PR #11 only. Completion requires the exact new HEAD to have successful `UGAS CI / unit-and-validation`, `UGAS CI / docker-smoke` and `UGAS Review / evidence` contexts, plus a bounded exact-head artifact with `PASS`. External Sol approval remains required. No merge, UI, VFX, orchestration, real maps, real minimap art, production routing or generation is authorized.

## Checkpoint Delta

Advance the active checkpoint from v0.21.2 historical byte-integrity correction-required history to v0.21.3 Maps/Minimap historical byte-integrity correction, preserving v0.21.2 unchanged and allowing only `external_review_maps_minimap_v0213` after exact-head evidence is green.
