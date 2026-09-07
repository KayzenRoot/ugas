# UGAS repository review response protocol

The active UI correction is v0.22.1 with `current_gate=UI_ASSET_FAMILY_SEMANTIC_INTEGRITY_TECHNICALLY_QUALIFIED`, `allowed_next_actions=[external_review_ui_asset_family_v0221]`, and `baseline_main_sha=1fb298885c56ccbf3df7dfdcb1be37fe2dc23af3` as historical branch context. Resolve current main and PR #13 from GitHub LIVE; do not infer live main from tracked state. Production remains `production_routing=BLOCKED`, `production_approved=false`, and `new_generation=0`.

This is the canonical response contract for every repository review, including reviews resumed in a new chat. The executor must recalculate the values from the live repository state and GitHub result before responding; a previous response, stale estimate or hidden chat memory is not an authority.

## Required response block

Every review response must contain the following block, preserving these labels:

```text
PROGRESSO E ETA
Capability atual: X-Y%
UGAS V1: X-Y%
Capabilities concluidas: N / TOTAL
Gates principais restantes: N
Ciclos estimados restantes: N-M
ETA otimista: ...
ETA realista: ...
ETA conservadora: ...
Confianca: ...
Critical path: ...
Status delta desde a review anterior: ...
```

## Calculation rules

- `Capabilities concluidas` is counted from the live `docs/ugas-v1-capability-matrix.json`; only capabilities explicitly marked closed, approved or otherwise completed by the active governance record count as complete.
- `Capability atual` describes the active capability state as a percentage range and must account for unresolved review or closure gates.
- `UGAS V1` is a percentage range toward the full capability matrix, never a claim of production readiness.
- `Gates principais restantes` names and counts every unresolved review, merge, implementation, production or completion gate relevant to the current path.
- `Ciclos estimados restantes` is a range of executor/reviewer cycles based on the current gate graph.
- Each ETA is a dated or duration-based range with assumptions. Optimistic, realistic and conservative estimates must remain visibly distinct.
- `Confianca` must identify the confidence level and the evidence basis.
- `Critical path` names the ordered blockers that control the next safe increment.
- `Status delta desde a review anterior` must state what closed, what opened and what remains blocked.

## Anti-staleness contract

The response must reconcile GitHub LIVE, the current main SHA, the active PR and exact-head checks when relevant, then read `CHECKPOINT.md`, `docs/evidence/current-state.json`, and the capability matrix. A stale progress snapshot cannot override those sources. The machine response source fields are `source_live_main_sha` (the current GitHub LIVE main SHA), `source_baseline_main_sha` (the tracked historical closure baseline), `source_current_gate`, and `source_mode=LIVE_REPOSITORY_AND_GITHUB`. The baseline is not a substitute for live main. If live state is unavailable, mark the affected values as unverified instead of manufacturing precision.

For v0.21.3, Maps/Minimap is `APPROVED_FOUNDATION` and `MERGED_CLOSED`; UI Asset Family is the sole next candidate, while `resolve_post_merge_closure_gate_pr_12` is the sole tracked action until the governance closure review is approved and merged in GitHub LIVE. UI activation is resolved dynamically and must not be authorized from a stale tracked state. Production remains `BLOCKED`, with `new_generation=0`.
