# UGAS v0.14.1 — HIT_REACTION_FRONT package integrity correction

## External visual decision

Sol external review recorded hit_reaction_front=APPROVED_PILOT and APPROVED_TO_MERGE for PR #4 at exact head a3e37865f260c5a6cd56743e1d4b9131fcb12cda. Technical GitHub checks were green; package integrity omitted the non-loop NETSCAPE extension while preserving reviewed HIT pixels. Visual content is inherited from the v0.14.0 review. Production remains production_approved=false, production_routing=BLOCKED. The last approved release before this merge is 0.13.1 (run_front_v1=APPROVED_PILOT). v0.14.0 remains a rejected historical package attempt. The capability matrix now has CAPABILITY_COUNT=16 and next_candidate=DEATH_ANIMATION_FRONT. The only allowed next action after governed merge is death_animation_front.

GITHUB_OPERATIONS_AUTOMATION_POLICY=ENABLED, USER_MANUAL_GITHUB_OPERATIONS=FALLBACK_ONLY, GITHUB_REVIEW_MODE=PR_FIRST, NO_SELF_MERGE_UNTIL_EXTERNAL_VISUAL_APPROVAL=true, ALWAYS_ON_DASHBOARD_POLICY=ENABLED, and DOCKER_ALWAYS_ON_LOCAL are authoritative. The GitHub review manifest/artifact is the authority for the exact PR #4 head; committed self-referential evidence files are not final-head authority.

The active phase is HIT_REACTION_FRONT. The current gate is HIT_REACTION_FRONT_PACKAGE_INTEGRITY_TECHNICALLY_QUALIFIED. Frame content remains APPROVED_PILOT_CONTENT_PENDING_PACKAGE_INTEGRITY_REVIEW. This correction does not merge PR #4 and does not start DEATH_ANIMATION_FRONT.

The rejected reviewed head is c059e24a4fa215882fac4b36991f7860f185a920. run_front_v1=APPROVED_PILOT remains bound to f3d68faa5524392e66aee2fc2a450b9da8fa734b from approved 0.13.1. v0.14.0 evidence is frozen rejected technical history. CAPABILITY_COUNT=16, next_candidate=HIT_REACTION_FRONT, production_routing=BLOCKED, new_generation=0, production_approved=false.

The generic GIF encoder now omits the NETSCAPE repeat extension when spec.loop=false and encodes infinite loop=0 only when spec.loop=true. The decoder reports loop_extension_present and loop_count without collapsing absence into loop=1. Fail-closed gates are loop_contract_matches, loop_extension_presence_matches and loop_count_matches.

GITHUB_OPERATIONS_AUTOMATION_POLICY=ENABLED, USER_MANUAL_GITHUB_OPERATIONS=FALLBACK_ONLY, GITHUB_REVIEW_MODE=PR_FIRST, NO_SELF_MERGE_UNTIL_EXTERNAL_VISUAL_APPROVAL=true, ALWAYS_ON_DASHBOARD_POLICY=ENABLED, and DOCKER_ALWAYS_ON_LOCAL are authoritative. The only allowed next action is external_review_hit_reaction_front_v0141. Do not merge.

## Package integrity

Non-loop HIT GIFs must have loop_extension_present=false and loop_count=null. Looping RUN_FRONT GIFs must keep an explicit infinite extension. NC-LOOP-01..05 use real encoded GIF files. Existing HIT NC-01..NC-10 remain rejection controls. Visual frame RGBA hashes, target hashes, motion_tracks_sha256, spritesheet pixels and GIF frame pixels/durations must remain identical to the v0.14.0 reviewed content.

## Evidence and validation

The corrected evidence is under docs/evidence/animation-runtime-v0141/. Frozen v0.14.0 evidence under docs/evidence/animation-runtime-v0140/ is not rewritten. Provenance fields are implementation_base_commit, branch_base_commit, rejected_reviewed_head and evidence_head_sha. The GitHub review manifest is the authority for the exact PR #4 head.

## Handoff gate

Leave PR #4 OPEN. Do not merge. Do not start DEATH_ANIMATION_FRONT. production_approved=false, production_routing=BLOCKED, new_generation=0 remain authoritative until the narrow package re-review.
