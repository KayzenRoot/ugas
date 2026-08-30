# 2D master pipeline v0.6.2

The active release is the v0.6.2 SDXL OpenPose model-card calibration. The v0.6.1 smoke correction and v0.6.0 provider qualification remain historical and immutable; only the P-only P0/P1/P2 matrix is authorized.

This release calibrates only the bounded SDXL Base + OpenPose ControlNet P lane. The v0.5.4 pose/provider and v0.5.5 review-snapshot evidence remain historical; P0/P1/P2 completed and the current lane stopped at its explicit model-card OpenPose gap.

O pipeline mantém o R4 aprovado como anchor imutável e separa identidade, pose, transparência, execução e revisão humana.

1. `identity-manifest.json` fixa o anchor, revisão e hash.
2. `pose-guides/` contém guias determinísticos; o challenge v0.3 é usado no lane recheck.
3. `pose-metric-calibration.json` mantém o detected-joint metric de v0.5.3; silhueta/keypoint é apenas diagnóstica.
4. MediaPipe Pose Landmarker é QA-only, com license/hash evidence e uma política global `transparent_neutral_gray`.
5. Thresholds são congelados antes de qualquer job; cada job grava seed, workflow/model hash, referências, prompt ID, history e output.
6. A/C/R e as lanes IP-Adapter permanecem históricas. A calibração atual executa exatamente P0/P1/P2 na seed 62701, preserva raw outputs/overlays e não autoriza walk.

A revisão visual humana e a aprovação de produção permanecem separadas dos gates técnicos.
