# UGAS 0.6.0

Universal Game Asset Studio: pipeline local-first para assets 2D com ComfyUI nativo, evidência reproduzível, transparência e governança de revisão.

O prompt v0.6.0 qualifica, com gates fail-closed, a lane experimental SDXL + OpenPose ControlNet + IP-Adapter. A decisão histórica de pose `LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED` do v0.5.4 e o snapshot `REVIEW_ARCHIVE_VERIFIED` do v0.5.5 permanecem imutáveis.

## Quick start

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -q
python scripts/validation/validate_state_consistency.py
python scripts/validation/run_validation.py
python scripts/validation/verify_review_archive.py <FINAL_REVIEW_ZIP>
```

Para executar a qualificação local, leia `docs/evidence/current-state.json` e siga os gates documentados em [REVIEW-v0.6.0.md](REVIEW-v0.6.0.md). O script de qualificação registra cada seed, workflow, modelo, hash, prompt/history binding e resultado da QA MediaPipe detectada. Não use o bundle MediaPipe local para distribuição.

## Boundaries

O workflow SDXL usa o PNG COCO-18 diretamente como controle de pose e o anchor R4 somente como identidade. P/I/PI são lanes separadas. Os thresholds de pose em [pose-thresholds-v054.json](docs/evidence/pose-thresholds-v054.json) são reutilizados sem alteração; a QA de silhueta legada é apenas diagnóstica.

Não são autorizados neste slice walk, âncoras, spritesheet, GIF, animação, 3D, provider alternativo ou pesos dentro do Git/ZIP. `REVIEW_ARCHIVE_VERIFIED` é verificação local do artefato, não aprovação externa.

Consulte [INSTALL.md](INSTALL.md), [CHECKPOINT.md](CHECKPOINT.md), [REVIEW-v0.6.0.md](REVIEW-v0.6.0.md) e [docs/evidence/current-state.json](docs/evidence/current-state.json). As releases v0.5.4 e v0.5.5 continuam disponíveis como histórico.
