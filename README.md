# UGAS 0.5.2

Universal Game Asset Studio: pipeline local-first para assets 2D com ComfyUI nativo, evidência reproduzível, transparência e governança de revisão.

O slice atual executa a escalada de controle de pose do prompt 04D. O release v0.5.1 é histórico e terminou em `MULTI_REFERENCE_POSE_CONTROL_GAP`; o ganho B-A de 0.140250 não atingiu o limiar fixo de 0.15. A versão 0.5.2 primeiro corrige o estado, gera guias determinísticos OpenPose COCO-18 v3 e mede as ordens nativas A/B/C. RefControl só pode ser investigado se o benchmark nativo permanecer sem qualificação.

## Quick start

```powershell
$env:PYTHONPATH = "src"
python -m ugas.cli pose-guides validate --json
python -m ugas.cli openpose validate --json
python -m ugas.cli identity inspect asset-2fec6fed1d714d0cb58ad75b56d7ba71 --json
python -m ugas.cli pose-control benchmark --json
python -m unittest discover -s tests -q
python scripts/validation/run_validation.py
```

O benchmark aborta com código não zero quando o estado, o runtime, a identidade, a pose, a arma ou a frescura da execução falham. Nenhuma âncora ou walk v3 é gerada sem uma lane qualificada. Pesos ficam fora do Git e a saída visual continua sujeita a revisão humana.

Consulte [INSTALL.md](INSTALL.md), [CHECKPOINT.md](CHECKPOINT.md), [REVIEW-v0.5.2.md](REVIEW-v0.5.2.md), [docs/evidence/current-state.json](docs/evidence/current-state.json) e [docs/test-coverage-matrix-v0.5.2.md](docs/test-coverage-matrix-v0.5.2.md). `REVIEW-v0.5.1.md` e os reviews anteriores são históricos e permanecem imutáveis.
