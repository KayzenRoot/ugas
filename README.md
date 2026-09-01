# UGAS 0.10.0

Universal Game Asset Studio: pipeline local-first para assets 2D com ComfyUI nativo, evidência reproduzível, transparência e governança de revisão.

O prompt v0.8.1 corrige a integridade QA do piloto determinístico de walk frontal em 8 frames, reutilizando o core estrutural v0.7.3 e as partes R4 v0.7.1 imutáveis. O provider permanece fail-closed: `walk_authorized=pilot_only`, `production_walk_authorized=false`, sem ComfyUI, sem nova execução SAM2 e com revisão visual externa obrigatória.

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

Leia `docs/evidence/current-state.json` e siga os gates documentados em [REVIEW-v0.10.0.md](REVIEW-v0.10.0.md). O runtime SAM2 e o checkpoint histórico são externos; nenhum peso é distribuído com o repositório.

## Boundaries

O provider `deterministic-cutout-rig-2d` aceita somente humanoide frontal com RGBA R4 imutável. Usa `translation_rotation_bounded_uniform_scale`, escala uniforme entre `0.92..1.08`, proveniência de pixels de origem e zero pixels gerados. Os thresholds MediaPipe em [pose-thresholds-v054.json](docs/evidence/pose-thresholds-v054.json) são reutilizados sem alteração.

Somente o replay walk/front/8, o idle/front/12 histórico e o novo `attack-front-v1` front/10 deste slice são autorizados; não há outras animações/direções nem routing de produção. `REVIEW_ARCHIVE_VERIFIED` é verificação local do artefato, não aprovação externa.

Consulte [INSTALL.md](INSTALL.md), [CHECKPOINT.md](CHECKPOINT.md), [REVIEW-v0.10.0.md](REVIEW-v0.10.0.md) e [docs/evidence/current-state.json](docs/evidence/current-state.json). Os reviews anteriores continuam disponíveis como histórico.
## v0.10.0 reusable action runtime

The current release is `0.10.0`. Use `python -m ugas.animation validate-spec`, `compile`, `qa`, and `package` with the profiles in `profiles/animation/`. The generic contract now preserves optional hash-bound `event_markers[]` and enforces loop/non-loop lifecycle semantics. The qualified pilot is `attack-front-v1`, a deterministic source-only 10-frame front sword action over the approved R4 cutout rig. Production routing remains `BLOCKED`; external attack visual review is still `REQUIRED`. Evidence is under `docs/evidence/animation-runtime-v0100/`.
