# 2D master pipeline v0.8.0

The active release is the v0.8.0 deterministic R4 cutout-rig front-walk eight-frame pilot. The v0.7.3 structural correction and earlier records remain historical and immutable; only one front-walk animation is in scope and production routing remains blocked.

This release does not run diffusion or SAM2. It reuses the v0.7.1 eleven-part R4 rig and v0.7.2 targets, then applies a source-derived torso/abdomen/belt/pelvis core, deterministic Pillow transforms, independent layer-integrity, geometric pairwise occlusion, topological seam and retention QA. The current lane requires external visual review before walk authorization.

O pipeline mantém o R4 aprovado como anchor imutável e separa identidade, pose, transparência, execução e revisão humana.

1. `identity-manifest.json` fixa o anchor, revisão e hash.
2. `pose-guides/` contém guias determinísticos; o challenge v0.3 é usado no lane recheck.
3. `pose-metric-calibration.json` mantém o detected-joint metric de v0.5.3; silhueta/keypoint é apenas diagnóstica.
4. MediaPipe Pose Landmarker é QA-only, com license/hash evidence e uma política global `transparent_neutral_gray`.
5. Thresholds são congelados antes de qualquer job; cada job grava seed, workflow/model hash, referências, prompt ID, history e output.
6. A/C/R, IP-Adapter and SDXL remain historical. The active lane runs zero new SAM2 passes, then static Q0/K1/K2/K3/K4 renders with zero ComfyUI generation jobs and does not authorize walk.
7. The structural core is source-mapped and excludes head/sword; expected coverage is independent from rendered output and every overlap requires a joint corridor or explicit phase geometry.

A revisão visual humana e a aprovação de produção permanecem separadas dos gates técnicos.
