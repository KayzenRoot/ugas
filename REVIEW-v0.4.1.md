# UGAS Review v0.4.1

## STATUS

READY_FOR_REVIEW — the real local correction passed the technical and structural gates; visual approval remains an explicit human decision.

## VERSION

0.4.1

## FASE

2D master visual-quality stabilization.

## OBJETIVO

Correct the FLUX.2 Klein Base/Distilled mismatch and establish a visually revisable, evidence-backed master-sprite pipeline before animation.

## ESCOPO

Base and Distilled model metadata, compatible workflows, prompt compiler, quality policies, hard candidate gates, bounded retries, native BiRefNet, alpha QA, checkerboard preview, measurable reference edit, structural QA, tests, documentation, GitHub and review ZIP.

## BASELINE AUDIT FINDINGS

The v0.4.0 candidate contact sheet contained clipping, fused anatomy, graphic noise and unusable candidates. Candidate selection could promote a technically valid but visibly unacceptable result, and reference edit did not have structural silhouette thresholds.

## ROOT CAUSE

The Base checkpoint was used with Distilled parameters: 4 steps and guidance 1.0. The corrected contract uses Base at 50 steps/guidance 4.0 and Distilled at 4 steps/guidance 1.0.

## MODEL LANES

FAST is `flux2-klein-4b-distilled-nvfp4`; QUALITY is `flux2-klein-4b-base-nvfp4`. Each record declares family, variant, quantization, distillation flags, recommended parameters, license, exact hashes and hardware evidence.

## WORKFLOW COMPATIBILITY

The loader validates family, variant, steps and guidance before a ComfyUI job. A Base/Distilled mismatch is rejected; experimental overrides are not part of the normal pipeline.

## FAST vs QUALITY BENCHMARK

The same master spec, prompt, resolution and seeds 4301–4303 were run through both lanes. All six 512² outputs were technically valid and eligible: Distilled used 4/1.0 and Base used 50/4.0. Results, SHA-256, runtime, parameters, hard gates and eligibility are in `docs/evidence/quality-benchmark.json`. No automatic visual winner is recorded.

## MASTER PILOT RESULT

The corrective pilot uses a stylized fantasy human warrior: full body, neutral idle pose, three-quarter front view, readable anatomy, separated arms, one sword beside the body, no effects and a simple contrasting background. Three QUALITY candidates passed the hard gates; candidate-3 was human-inspected as preferred and selected. Eligibility and selection are recorded in `docs/evidence/candidates.json`.

## TRANSPARENCY RESULT

Native BiRefNet remains the only removal path. The selected master has alpha-zero 0.767872, alpha-opaque 0.003914, partial-alpha 0.228214, foreground coverage 0.232128, bbox `[93,16,372,499]`, no border contact and no halo. Metrics and the checkerboard are recorded in `docs/evidence/master-transparent.json`.

## REFERENCE EDIT RESULT

The edit instruction is stored separately from the generation prompt, normalized and hashed. It states the single measurable change and the identity/pose/silhouette properties that must be preserved.

## REFERENCE STRUCTURAL QA

The output is compared with the pre-edit mask. The result passed with silhouette IoU 0.988583, centroid drift 0.000279, bbox scale delta 0.014085 and non-identical pixels. The configured thresholds are 0.70, 0.08, 0.15 and pixel-identity rejection; failure is `REFERENCE_EDIT_QA_FAILED`.

## TESTS

The suite covers lane metadata, mismatch rejection, visual-only prompt compilation, separate edit instructions, clipping, duplicates, empty candidates, alpha metrics, checkerboard, structural QA, approval hash/transparency gates and out-of-scope grids: 17 tests pass.

## VALIDATION

`python -m unittest -q` passes 17/17. `python scripts/validation/run_validation.py` is the final gate; it also runs a `git archive HEAD` snapshot and a no-Git review-snapshot regression when the checkout is available.

## GITHUB

The target repository is `https://github.com/csn1985-ship-it/ugas`. Publication is complete only when the final commit is on `main` and the local checkout is clean; external GitHub Actions or approval is not inferred from a push.

## VISUAL REVIEW STATUS

REQUIRED. This file never substitutes human inspection of the baseline, benchmark contact sheet, selected master, transparency checkerboard or reference edit.

## PENDENCIAS

Obtain the user's external visual approval if desired. GitHub publication and the review ZIP are final delivery actions; neither is an approval of the artwork.

## BLOQUEIOS

Animation, multi-frame grids, production LoRAs, 3D, Blender, audio, cloud inference and paid providers remain blocked by scope. A local visual-quality gap must be reported rather than hidden.

## DECISOES

Keep Base and Distilled explicit; rank only eligible candidates; retry at most two rounds; preserve revision provenance; invalidate transparency/approval on edits; do not infer approval from local evidence.

## PROXIMO PASSO

Publish the validated commit and create the final review ZIP; keep the visual approval gate explicit.

## DEFINITION OF DONE

Correct semantics, real benchmark, hard-gate selection, at least one eligible pilot, native transparency and alpha evidence, measurable reference edit with structural QA, tests, docs, GitHub publication, clean checkout and final review ZIP. No animation work begins here.
