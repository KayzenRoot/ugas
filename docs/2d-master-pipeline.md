# 2D master pipeline v0.6.1

The active release is the v0.6.1 SDXL smoke-evidence correction. The v0.6.0 provider qualification remains historical and immutable; benchmark, confirmation, walk and anchors remain outside this slice.

This release qualifies the bounded SDXL ControlNet/IP-Adapter provider lane. The v0.5.4 pose/provider and v0.5.5 review-snapshot evidence remain historical; the current lane stopped at its explicit OpenPose gap.

O pipeline mantém o R4 aprovado como anchor imutável e separa identidade, pose, transparência, execução e revisão humana.

1. `identity-manifest.json` fixa o anchor, revisão e hash.
2. `pose-guides/` contém guias determinísticos; o challenge v0.3 é usado no lane recheck.
3. `pose-metric-calibration.json` mantém o detected-joint metric de v0.5.3; silhueta/keypoint é apenas diagnóstica.
4. MediaPipe Pose Landmarker é QA-only, com license/hash evidence e uma política global `transparent_neutral_gray`.
5. Thresholds são congelados antes de qualquer job; cada job grava seed, workflow/model hash, referências, prompt ID, history e output.
6. A/C/R executam exatamente três seeds cada. O resultado atual falha o gate de provider por pose, preserva os outputs para review e não autoriza walk.

A revisão visual humana e a aprovação de produção permanecem separadas dos gates técnicos.
