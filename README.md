# UGAS 0.6.1

Universal Game Asset Studio: pipeline local-first para assets 2D com ComfyUI nativo, evidência reproduzível, transparência e governança de revisão.

O prompt v0.6.1 corrige a integridade da evidência do smoke SDXL + OpenPose ControlNet + IP-Adapter e torna os gates de identidade e sujeito único realmente fail-closed. A decisão histórica de pose `LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED` do v0.5.4, o review v0.6.0 e o snapshot `REVIEW_ARCHIVE_VERIFIED` do v0.5.5 permanecem preservados.

## Quick start

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -q
python scripts/validation/validate_state_consistency.py
python scripts/validation/run_validation.py
python scripts/validation/verify_review_archive.py <FINAL_REVIEW_ZIP>
```

Para executar a correção local, leia `docs/evidence/current-state.json` e siga os gates documentados em [REVIEW-v0.6.1.md](REVIEW-v0.6.1.md). O smoke usa somente a seed 61701 e registra cada lane, workflow, modelo, hash, prompt/history binding, PNG bruto, QA MediaPipe pré-BiRefNet, pós-processamento e gates de identidade. Não use o bundle MediaPipe local para distribuição.

## Boundaries

O workflow SDXL usa o PNG COCO-18 diretamente como controle de pose e o anchor R4 somente como identidade. P/I/PI são lanes separadas. Os thresholds de pose em [pose-thresholds-v054.json](docs/evidence/pose-thresholds-v054.json) são reutilizados sem alteração; a QA de silhueta legada é apenas diagnóstica.

Não são autorizados neste slice walk, âncoras, spritesheet, GIF, animação, 3D, provider alternativo ou pesos dentro do Git/ZIP. `REVIEW_ARCHIVE_VERIFIED` é verificação local do artefato, não aprovação externa.

Consulte [INSTALL.md](INSTALL.md), [CHECKPOINT.md](CHECKPOINT.md), [REVIEW-v0.6.1.md](REVIEW-v0.6.1.md) e [docs/evidence/current-state.json](docs/evidence/current-state.json). O review [v0.6.0](REVIEW-v0.6.0.md) e as releases v0.5.4/v0.5.5 continuam disponíveis como histórico.
