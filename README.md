# UGAS 0.11.0

Universal Game Asset Studio: pipeline local-first para assets 2D com ComfyUI nativo, evidência reproduzível, transparência e governança de revisão. O release ativo adiciona uma camada genérica de qualidade de movimento e o piloto determinístico `attack-front-v2`.

O v0.11.0 preserva byte-a-byte os fixtures históricos walk/idle/attack-front-v1, sem ComfyUI, SAM2, diffusion ou edição manual de pixels. O provider permanece fail-closed: `walk_authorized=pilot_only`, `production_walk_authorized=false`, `production_routing=BLOCKED` e revisão visual externa obrigatória.

## Quick start

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -q
python scripts/validation/validate_state_consistency.py
python scripts/validation/run_validation.py
python scripts/validation/verify_review_archive.py <FINAL_REVIEW_ZIP>
python scripts/validation/run_cutout_rig_v073.py --json
python -m ugas.cli --version
```

Leia `docs/evidence/current-state.json` e siga os gates documentados em [REVIEW-v0.11.0.md](REVIEW-v0.11.0.md). O runtime SAM2, o bundle MediaPipe e os checkpoints históricos são externos; nenhum peso é distribuído com o repositório.

## Boundaries

O provider `deterministic-cutout-rig-2d` aceita somente humanoide frontal com RGBA R4 imutável. Usa `translation_rotation_bounded_uniform_scale`, escala uniforme entre `0.92..1.08`, proveniência de pixels de origem e zero pixels gerados. Os thresholds MediaPipe em [pose-thresholds-v054.json](docs/evidence/pose-thresholds-v054.json) são reutilizados sem alteração.

Somente o replay walk/front/8, o idle/front/12 histórico, o `attack-front-v1` histórico e o novo `attack-front-v2` front/12 deste slice são autorizados; não há outras animações/direções nem routing de produção. `REVIEW_INDEX_VERIFIED` é verificação local do índice, não aprovação externa.

Consulte [INSTALL.md](INSTALL.md), [CHECKPOINT.md](CHECKPOINT.md), [REVIEW-v0.11.0.md](REVIEW-v0.11.0.md) e [docs/evidence/current-state.json](docs/evidence/current-state.json). Os reviews anteriores continuam disponíveis como histórico.

## v0.11.0 motion quality layer

`motion_tracks[]` é opcional e usa IDs opacos, valores `scalar`/`vec2`, interpolação linear, smoothstep ou cubic Hermite determinística. O core valida, amostra e hashia as curvas; o adapter `attack_front_v2` interpreta seus canais. O pacote v2 é 6x2, 512x512, RGBA, 12 fps, non-loop, com hit no frame 6 e janela ativa 4–7. O resultado técnico é `CUTOUT_ANIMATION_RUNTIME_V2_ATTACK_FRONT_TECHNICALLY_QUALIFIED`; a revisão visual externa permanece `REQUIRED`.
## v0.10.0 reusable action runtime (historical)

The v0.10.0 historical release added optional hash-bound `event_markers[]` and generic loop/non-loop lifecycle semantics for `attack-front-v1`, a deterministic source-only 10-frame front sword action over the approved R4 cutout rig. Its evidence remains under `docs/evidence/animation-runtime-v0100/`; the active release is v0.11.0.
