# 2D master pipeline v0.11.0

The active release is the v0.11.0 generic motion-quality runtime over the immutable v0.10.0 action lane and v0.9.0 cutout-rig lane. The v0.8.0, v0.7.3, v0.9.0, v0.9.1 and v0.10.0 records remain historical and immutable; only front `attack-front-v2` is newly executed and production routing remains blocked.

This release does not run diffusion or SAM2. It reuses the v0.7.1 eleven-part R4 rig, masks, structural core, walk/idle/attack-v1 fixtures, and adds the generic optional motion-track contract plus a deterministic source-skeleton sword sweep for `attack-front-v2`. The 12 frames are non-looping, 12 fps, front-facing, RGBA, with fixed markers at windup peak, active start/end, hit, and recovery complete. The current lane requires external attack-v2 visual review before authorization.

O pipeline mantém o R4 aprovado como anchor imutável e separa identidade, pose, transparência, execução e revisão humana.

1. `identity-manifest.json` fixa o anchor, revisão e hash.
2. `pose-guides/` contém guias determinísticos; o challenge v0.3 é usado no lane recheck.
3. `pose-metric-calibration.json` mantém o detected-joint metric de v0.5.3; silhueta/keypoint é apenas diagnóstica.
4. MediaPipe Pose Landmarker é QA-only, com license/hash evidence e uma política global `transparent_neutral_gray`.
5. Thresholds são congelados antes de qualquer job; cada job grava seed, workflow/model hash, referências, prompt ID, history e output.
6. A/C/R, IP-Adapter and SDXL remain historical. The active lane runs zero new SAM2 passes, then static Q0/K1/K2/K3/K4 renders with zero ComfyUI generation jobs and does not authorize walk.
7. The structural core is source-mapped and excludes head/sword; expected coverage is independent from rendered output and every overlap requires a joint corridor or explicit phase geometry.

A revisão visual humana e a aprovação de produção permanecem separadas dos gates técnicos.
## v0.10.0 runtime boundary

The reusable deterministic animation runtime consumes the immutable R4 cutout rig through declarative animation specs. v0.10.0 covers `attack-front-v1` only; generic event markers are validated, ordered, hash-bound, and preserved through compiled manifest, QA, metadata, and package artifacts. Production routing is `BLOCKED`, with `decision=QUALIFIED` and every hard gate literally true required before package creation. Evidence is recorded in `docs/evidence/animation-runtime-v0100/`.
