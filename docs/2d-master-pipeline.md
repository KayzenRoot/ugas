# 2D master pipeline v0.7.0

The active release is the v0.7.0 deterministic R4 cutout-rig provider. The v0.6.2 SDXL/OpenPose calibration remains historical and immutable; only static Q0/Q1/Q2 cutout-rig qualification is in scope.

This release does not run diffusion. It binds R4 RGBA pixels to an eleven-part rig through an isolated SAM2.1 Hiera Small pass and deterministic Pillow transforms. The current lane stopped at its explicit visual/estimator gap.

O pipeline mantém o R4 aprovado como anchor imutável e separa identidade, pose, transparência, execução e revisão humana.

1. `identity-manifest.json` fixa o anchor, revisão e hash.
2. `pose-guides/` contém guias determinísticos; o challenge v0.3 é usado no lane recheck.
3. `pose-metric-calibration.json` mantém o detected-joint metric de v0.5.3; silhueta/keypoint é apenas diagnóstica.
4. MediaPipe Pose Landmarker é QA-only, com license/hash evidence e uma política global `transparent_neutral_gray`.
5. Thresholds são congelados antes de qualquer job; cada job grava seed, workflow/model hash, referências, prompt ID, history e output.
6. A/C/R, IP-Adapter and SDXL remain historical. The active lane runs one SAM2 pass per rig revision, then static Q0/Q1/Q2 renders with zero ComfyUI generation jobs and does not authorize walk.

A revisão visual humana e a aprovação de produção permanecem separadas dos gates técnicos.
