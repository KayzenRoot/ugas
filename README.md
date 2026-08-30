# UGAS 0.5.5

Universal Game Asset Studio: pipeline local-first para assets 2D com ComfyUI nativo, evidência reproduzível, transparência e governança de revisão.

O prompt 04G corrige a integridade do snapshot distribuído do review v0.5.4. A decisão de pose permanece historicamente `LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED`; os 9 outputs A/C/R, hashes e execution evidence foram preservados. Esta release não executa ComfyUI nem MediaPipe, não altera thresholds e não gera walk/âncoras.

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
python scripts/validation/verify_review_archive.py <FINAL_REVIEW_ZIP>
```

O verificador do review extrai o ZIP em um diretório temporário externo, executa `compileall`, os testes e a validação sem depender de `.git`, e exige `REVIEW_ARCHIVE_VERIFIED`. O bundle `.task` e os pesos ficam fora do Git e do review ZIP. A aprovação visual humana e qualquer aprovação externa continuam separadas dos gates automatizados.

Consulte [INSTALL.md](INSTALL.md), [CHECKPOINT.md](CHECKPOINT.md), [REVIEW-v0.5.5.md](REVIEW-v0.5.5.md), [docs/evidence/current-state.json](docs/evidence/current-state.json) e [docs/test-coverage-matrix-v0.5.5.md](docs/test-coverage-matrix-v0.5.5.md). O [REVIEW-v0.5.4.md](REVIEW-v0.5.4.md) e as evidências de pose são históricos e permanecem imutáveis.
