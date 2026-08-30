# UGAS 0.6.2

Universal Game Asset Studio: pipeline local-first para assets 2D com ComfyUI nativo, evidência reproduzível, transparência e governança de revisão.

O prompt v0.6.2 calibra exclusivamente a lane P do SDXL + OpenPose ControlNet nas configurações publicadas pelo model card, preservando o smoke v0.6.1 e todos os gates históricos. IP-Adapter, I/PI, benchmark, anchors e walk permanecem fora do escopo.

## Quick start

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -q
python scripts/validation/validate_state_consistency.py
python scripts/validation/run_validation.py
python scripts/validation/verify_review_archive.py <FINAL_REVIEW_ZIP>
```

Para executar a calibração local, leia `docs/evidence/current-state.json` e siga os gates documentados em [REVIEW-v0.6.2.md](REVIEW-v0.6.2.md). A triagem usa somente P0/P1/P2 com seed 62701, renderiza guides diretamente do JSON em 512/768/1024 e registra workflow, model card, hashes, prompt/history binding, PNG bruto e QA MediaPipe. Não use o bundle MediaPipe local para distribuição.

## Boundaries

O workflow SDXL usa o PNG COCO-18 diretamente como controle de pose e o anchor R4 somente como identidade. P/I/PI são lanes separadas. Os thresholds de pose em [pose-thresholds-v054.json](docs/evidence/pose-thresholds-v054.json) são reutilizados sem alteração; a QA de silhueta legada é apenas diagnóstica.

Não são autorizados neste slice walk, âncoras, spritesheet, GIF, animação, 3D, provider alternativo ou pesos dentro do Git/ZIP. `REVIEW_ARCHIVE_VERIFIED` é verificação local do artefato, não aprovação externa.

Consulte [INSTALL.md](INSTALL.md), [CHECKPOINT.md](CHECKPOINT.md), [REVIEW-v0.6.2.md](REVIEW-v0.6.2.md) e [docs/evidence/current-state.json](docs/evidence/current-state.json). Os reviews v0.6.1/v0.6.0 e as releases v0.5.4/v0.5.5 continuam disponíveis como histórico.
