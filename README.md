# UGAS 0.7.0

Universal Game Asset Studio: pipeline local-first para assets 2D com ComfyUI nativo, evidência reproduzível, transparência e governança de revisão.

O prompt v0.7.0 adiciona um provider determinístico de cutout-rig 2D para a revisão R4: MediaPipe para skeleton de origem, SAM2.1 Hiera Small isolado para onze máscaras e Pillow para transformações de pixels. O provider está implementado e evidenciado, mas permanece não qualificado por falha nos gates de pose Q1/Q2.

## Quick start

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -q
python scripts/validation/validate_state_consistency.py
python scripts/validation/run_validation.py
python scripts/validation/verify_review_archive.py <FINAL_REVIEW_ZIP>
python -m ugas.cli cutout-rig qualify-sam2 --json
python -m ugas.cli cutout-rig build --asset-id asset-2fec6fed1d714d0cb58ad75b56d7ba71 --json
python -m ugas.cli cutout-rig pose-pilot --poses q0,q1,q2 --json
```

Leia `docs/evidence/current-state.json` e siga os gates documentados em [REVIEW-v0.7.0.md](REVIEW-v0.7.0.md). O runtime SAM2 e o checkpoint são externos; nenhum peso é distribuído com o repositório.

## Boundaries

O provider `deterministic-cutout-rig-2d` aceita somente humanoide frontal com RGBA R4 imutável. Usa `translation_rotation_bounded_uniform_scale`, escala uniforme entre `0.92..1.08`, proveniência de pixels de origem e zero pixels gerados. Os thresholds MediaPipe em [pose-thresholds-v054.json](docs/evidence/pose-thresholds-v054.json) são reutilizados sem alteração.

Não são autorizados neste slice walk de 8 frames, âncoras, spritesheet, GIF, animação genérica, provider alternativo, geração ComfyUI ou pesos dentro do Git/ZIP. `REVIEW_ARCHIVE_VERIFIED` é verificação local do artefato, não aprovação externa.

Consulte [INSTALL.md](INSTALL.md), [CHECKPOINT.md](CHECKPOINT.md), [REVIEW-v0.7.0.md](REVIEW-v0.7.0.md) e [docs/evidence/current-state.json](docs/evidence/current-state.json). O review v0.6.2 e as releases anteriores continuam disponíveis como histórico.
