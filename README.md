# UGAS 0.5.3

Universal Game Asset Studio: pipeline local-first para assets 2D com ComfyUI nativo, evidência reproduzível, transparência e governança de revisão.

O slice atual executa a calibração de métrica de pose do prompt 04E. O resultado v0.5.2 `LOCAL_POSE_CONTROL_PROVIDER_GAP` foi reclassificado como `POSE_METRIC_GATE_DESIGN_GAP` porque A=0.894403 + 0.15 exigia 1.044403, acima do máximo [0,1]. A calibração sintética passou, mas a qualificação QA parou em `POSE_QA_MODEL_LICENSE_GAP` por termos não determinados do bundle MediaPipe. Nenhum provider, âncora ou walk novo foi executado.

## Quick start

```powershell
$env:PYTHONPATH = "src"
python -m ugas.cli pose-guides validate --json
python -m ugas.cli openpose validate --json
python -m ugas.cli identity inspect asset-2fec6fed1d714d0cb58ad75b56d7ba71 --json
python scripts/validation/run_pose_metric_calibration.py
python scripts/validation/run_pose_qa_qualification.py
python -m unittest discover -s tests -q
python scripts/validation/run_validation.py
```

Os scripts abortam com código não zero quando estado, métrica ou QA independente falham. O estimador MediaPipe é somente QA e não altera o grafo de geração. Nenhuma lane de provider, âncora ou walk v3 é executada sem calibração e estimador qualificados. Pesos e bundles ficam fora do Git e a saída visual continua sujeita a revisão humana.

Consulte [INSTALL.md](INSTALL.md), [CHECKPOINT.md](CHECKPOINT.md), [REVIEW-v0.5.3.md](REVIEW-v0.5.3.md), [docs/evidence/current-state.json](docs/evidence/current-state.json) e [docs/test-coverage-matrix-v0.5.3.md](docs/test-coverage-matrix-v0.5.3.md). Reviews anteriores são históricos e permanecem imutáveis.
