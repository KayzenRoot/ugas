# UGAS 0.7.2

Universal Game Asset Studio: pipeline local-first para assets 2D com ComfyUI nativo, evidência reproduzível, transparência e governança de revisão.

O prompt v0.7.2 qualifica a correção v0.7.1 com plano hash-bound de oclusão, QA topológico de juntas, retenção explicada por profundidade e quatro poses estruturais front-walk. O provider permanece fail-closed: `walk_authorized=false`, sem ComfyUI, sem nova execução SAM2 e com revisão visual externa obrigatória.

## Quick start

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -q
python scripts/validation/validate_state_consistency.py
python scripts/validation/run_validation.py
python scripts/validation/verify_review_archive.py <FINAL_REVIEW_ZIP>
python scripts/validation/run_cutout_rig_v072.py --json
python -m ugas.cli --version
```

Leia `docs/evidence/current-state.json` e siga os gates documentados em [REVIEW-v0.7.2.md](REVIEW-v0.7.2.md). O runtime SAM2 e o checkpoint histórico são externos; nenhum peso é distribuído com o repositório.

## Boundaries

O provider `deterministic-cutout-rig-2d` aceita somente humanoide frontal com RGBA R4 imutável. Usa `translation_rotation_bounded_uniform_scale`, escala uniforme entre `0.92..1.08`, proveniência de pixels de origem e zero pixels gerados. Os thresholds MediaPipe em [pose-thresholds-v054.json](docs/evidence/pose-thresholds-v054.json) são reutilizados sem alteração.

Não são autorizados neste slice walk de 8 frames, âncoras, spritesheet, GIF, animação genérica, provider alternativo, geração ComfyUI ou pesos dentro do Git/ZIP. `REVIEW_ARCHIVE_VERIFIED` é verificação local do artefato, não aprovação externa.

Consulte [INSTALL.md](INSTALL.md), [CHECKPOINT.md](CHECKPOINT.md), [REVIEW-v0.7.2.md](REVIEW-v0.7.2.md) e [docs/evidence/current-state.json](docs/evidence/current-state.json). O review v0.7.1, v0.7.0, v0.6.2 e as releases anteriores continuam disponíveis como histórico.
