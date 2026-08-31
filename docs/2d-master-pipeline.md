# 2D master pipeline v0.7.2

The active release is the v0.7.2 deterministic R4 cutout-rig occlusion/gait qualification. The v0.7.1 correction, v0.7.0 result, v0.6.2 SDXL/OpenPose calibration and earlier records remain historical and immutable; only Q0 and four static key poses are in scope.

This release does not run diffusion or SAM2. It reuses the v0.7.1 eleven-part R4 rig and applies deterministic Pillow transforms, pairwise occlusion, topological seam, retention and gait-structure QA. The current lane requires external visual review before walk authorization.

O pipeline mantém o R4 aprovado como anchor imutável e separa identidade, pose, transparência, execução e revisão humana.

1. `identity-manifest.json` fixa o anchor, revisão e hash.
2. `pose-guides/` contém guias determinísticos; o challenge v0.3 é usado no lane recheck.
3. `pose-metric-calibration.json` mantém o detected-joint metric de v0.5.3; silhueta/keypoint é apenas diagnóstica.
4. MediaPipe Pose Landmarker é QA-only, com license/hash evidence e uma política global `transparent_neutral_gray`.
5. Thresholds são congelados antes de qualquer job; cada job grava seed, workflow/model hash, referências, prompt ID, history e output.
6. A/C/R, IP-Adapter and SDXL remain historical. The active lane runs zero new SAM2 passes, then static Q0/K1/K2/K3/K4 renders with zero ComfyUI generation jobs and does not authorize walk.

A revisão visual humana e a aprovação de produção permanecem separadas dos gates técnicos.
