# UGAS V1 Definition of Done

Version 0.25.0 - phase V1_FINAL_ACCEPTANCE.

This document separates the technical V1 final acceptance from the separate
production readiness workstream. Completing this definition of done means the
V1 capability surface is technically accepted; it is explicitly not production
approval.

## Technical acceptance criteria (v0.25.0)

- The V1 capability matrix audits all 16 capability ids against repository bytes:
  every evidence pointer and every test pointer must resolve.
- Hard gates are observed, never assumed: each of the 28 hard gates is recorded
  as a strict boolean together with its proof source.
- Negative controls prove that the acceptance guardrails reject injected defects.
- Two independent executions of the acceptance core produce one canonical digest.
- The frozen v0.24.7 orchestration snapshots still match their bound digests.
- The external visual review of the observability dashboard is bound to the
  approval artifact without self approval.

## Production boundary

- production_approved=false
- production_routing=BLOCKED
- real_asset_generation=NONE
- new_generation=0
- provider_submit_calls=0
- production readiness workstream: NOT_STARTED_REQUIRED_SEPARATELY

The v0.25.0 technical acceptance is not production approval and does not open the
production readiness workstream. Starting that workstream requires a separate
work order with its own evidence and gates.

## Acceptance evidence

- Evidence root: docs/evidence/v1-final-acceptance/
- Summary: docs/evidence/v1-final-acceptance/final-acceptance-summary.json
- Review: REVIEW-UGAS-V1-FINAL-ACCEPTANCE.md
