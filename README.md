# UGAS 0.5.4

Universal Game Asset Studio: pipeline local-first para assets 2D com ComfyUI nativo, evidência reproduzível, transparência e governança de revisão.

O slice ativo do prompt 04F qualificou o MediaPipe Pose Landmarker somente como estimador QA independente, resolveu a licença para uso local de QA e executou as 9 saídas autorizadas A/C/R. O resultado é `LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED`: a identidade foi preservada, mas C e R não passaram a pose medida por juntas. Walk, âncoras v3, novos providers e aprovação de produção continuam bloqueados.

## Quick start

```powershell
$env:PYTHONPATH = "src"
python -m ugas.cli pose-guides validate --json
python -m ugas.cli openpose validate --json
python -m ugas.cli identity inspect asset-2fec6fed1d714d0cb58ad75b56d7ba71 --json
python scripts/validation/run_pose_metric_calibration.py
python scripts/validation/run_pose_qa_qualification.py
python scripts/validation/run_v054_lane_recheck.py
python -m unittest discover -s tests -q
python scripts/validation/run_validation.py
```

O estimador é QA-only e não altera o grafo de geração. O bundle `.task` e os pesos ficam fora do Git e do review ZIP. A aprovação visual humana e qualquer aprovação externa continuam separadas dos gates automatizados.

Consulte [INSTALL.md](INSTALL.md), [CHECKPOINT.md](CHECKPOINT.md), [REVIEW-v0.5.4.md](REVIEW-v0.5.4.md), [docs/evidence/current-state.json](docs/evidence/current-state.json) e [docs/test-coverage-matrix-v0.5.4.md](docs/test-coverage-matrix-v0.5.4.md). Reviews anteriores, inclusive [REVIEW-v0.5.3.md](REVIEW-v0.5.3.md), são históricos e permanecem imutáveis.
