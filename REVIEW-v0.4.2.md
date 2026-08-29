# UGAS Review v0.4.2

## STATUS

`READY_FOR_REVIEW / VISUAL_REVIEW_REQUIRED`. The correction is implemented and technically validated. Human visual approval is still pending and is not inferred from automated checks.

## VERSION

`0.4.2`

## FASE

Revision integrity, evidence correctness, safe margins and transparency/RGB QA.

## OBJETIVO

Make every asset revision independently addressable, immutable and hash-verifiable while preserving the v0.4.1 Base/Distilled lanes.

## ESCOPO

Immutable revision directories, derived-from integrity, revision auditor, safe-margin hard gate, near-opaque alpha metrics, RGB preservation QA, immutable reference structural QA, review manifest validation, restored regression coverage and a fresh real RTX 5050 pilot. Animation, multi-frame generation, pose control, 3D, Blender, audio, cloud and paid providers remain out of scope.

## AUDIT FINDINGS FIXED

The v0.4.1 review alias defect is fixed: the former global mutable `tmp/background-removal/master-transparent.png` is not used for new authoritative revisions. R2 and R4 are independently stored, hash-checked and represented by distinct review roles.

## REVISION STORAGE

The fresh asset is `asset-6802db1284dd4b4ba25c6987e5b26ddb`. R1-R4 each use `tmp/assets/<asset-id>/revisions/<revision-id>/output.png`; transparent revisions also own `mask.png`, `checkerboard.png` and `metadata.json`. A unique job directory is used for each standalone operation.

## REVISION INTEGRITY

`python -m ugas.cli asset verify-integrity asset-6802db1284dd4b4ba25c6987e5b26ddb --json` returned `REVISION_INTEGRITY_PASSED`, with four unique revisions, unique paths, matching SHA-256 values, valid ancestry, no forward/cyclic derivation and no failures. Production readiness was recomputed as false because visual approval is pending.

R1 `revision-670566d1a2324f08a6903415f95606ef` — `6a69069f25d5b9b2ad0d1f8a05a648d4047163e84b789e9a0328eba21385f8c7`

R2 `revision-142ce444c56a4fdba02c4b59c8532a0d` — `1045c76fd1fb97632e2eb69f99244326c0acba837372a7afb2a531cca9388488`

R3 `revision-bd7baa4990c34a6e89bfca4e6aedb97e` — `cf315b52ed4576ffac80616e515749ada45c03d02faba6d458002e8bfe8a8c48`

R4 `revision-2e7023c8e0c947ac9faa96c5f7e35650` — `84e834db6adc51b4884e4b56d64bd9c196a17e818d792b177ae0fa0a06ecf928`

## SAFE MARGINS

The 512x512 pilot consumed the declared 24 px margins. Three of six candidates were eligible and all three had `safe_margin_ok=true`; rejected candidates recorded explicit top/bottom violations. The selected candidate was candidate-6, seed 9506, bbox `[158,40,361,487]`, within the inclusive safe area `[24,24,488,488]`.

## TRANSPARENCY / RGB PRESERVATION

Native BiRefNet produced R2 and R4 alpha masks. R2 near-opaque foreground fraction was `0.865464`; R4 was `0.879325`; both exceeded `0.85`. RGB preservation was `MAE total=0.0` for both transparent outputs, with `42,541` and `42,540` compared high-alpha pixels respectively. Both had no border contact and no detected halo.

## REFERENCE EDIT REVISION CHAIN

`R1 RGB -> R2 transparent -> R3 edited RGB -> R4 transparent`. R3 used the quality Base image-edit workflow and the constrained instruction to change only blue armor to deep cobalt/navy while preserving identity, face, proportions, pose, camera, silhouette, weapon and composition. R4 was derived from R3 with original RGB plus native BiRefNet alpha.

## REFERENCE STRUCTURAL QA

Immutable R2 versus R4 structural QA passed: silhouette IoU `0.978328` (minimum `0.70`), centroid drift `0.000978` (maximum `0.08`), bbox scale delta `0.0` (maximum `0.15`), non-identical pixels, distinct paths/revisions/hashes and matching metadata hashes.

## REAL RTX 5050 PILOT

The fresh corrective pilot ran on local ComfyUI `0.34.0` with `NVIDIA GeForce RTX 5050`, using the QUALITY Base lane (`50` steps, guidance `4.0`) and six candidates at 512x512. Seed 9501 was used for the candidate set; candidate-6 was selected after three candidates passed the margin gates. Two earlier bounded corrective attempts (seeds 9201 and 9301) correctly failed their hard margin gates after their allowed retries and were not presented as successful evidence.

A fresh FAST/QUALITY benchmark with shared seeds `[4301,4302,4303]` also completed: all six outputs were technically valid, with three eligible by safe margins (two FAST, one QUALITY). No visual winner was assigned automatically.

## TESTS

The restored/adapted v0.4.0 coverage matrix maps all 26 historical test intents. The full suite contains 58 tests, including v0.4.1 contracts and v0.4.2 revision-integrity tests.

## VALIDATION

The canonical commands passed locally before publication: `python -m compileall -q src scripts tests`, `python -m unittest -q`, review-manifest validation, and the integrity CLI. The exact Git archive and no-Git snapshot checks are required and recorded after the final commit below.

## TRACKED SNAPSHOT / GITHUB

Weights, secrets, caches and generated `tmp/` outputs remain outside the tracked distributable snapshot. Final commit, push and remote `main` equality are recorded here after they are verified.

## VISUAL REVIEW STATUS

The benchmark contact sheet, selected master, checkerboards and R3/R4 comparison were inspected locally. Technical transparency and structural checks pass. The R3/R4 preview visibly changes the armor toward cobalt/navy but also changes facial lighting/appearance; this is an explicit human-review item, not an automatic approval.

## PENDENCIAS

Human reviewer must accept or reject the R3/R4 visual result and, if rejected, request a new constrained reference-edit revision. External audit/approval remains pending.

## BLOQUEIOS

No implementation, GPU, ComfyUI, integrity or validation blocker remains. Visual acceptance of the generated edit is the only release gate still open.

## DECISOES

Preserve Distilled at 4 steps/guidance 1.0 and Base at 50 steps/guidance 4.0. Use original RGB plus native BiRefNet alpha. Never overwrite earlier revisions. Keep human approval separate. Do not authorize animation or other excluded capabilities.

## PROXIMO PASSO

Review the visual evidence, then use the exact revision ID/hash for any human approval decision. The published repository and review ZIP contain the evidence and the pending-review state.

## DEFINITION OF DONE

All v0.4.0 relevant regression intents are mapped; no relevant test was silently deleted; new integrity tests are green; outputs are unique and immutable; R2/R4 structural QA, safe margins and RGB preservation pass; the fresh RTX 5050 pilot is evidenced; review roles are distinct and hash-verifiable; exact snapshot and GitHub checks pass; no automatic human approval is claimed; and the final ZIP is validated.

## REVIEW ZIP

Generated after final GitHub verification and all evidence checks, as the last filesystem action. Its SHA-256 and path are reported in the final handoff.
