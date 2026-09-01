# UGAS 0.11.2

Universal Game Asset Studio: pipeline local-first para assets 2D com ComfyUI nativo, evidência reproduzível, transparência e governança de revisão. O release ativo corrige somente a integridade QA e recupera o escopo do piloto determinístico `attack-front-v2`.

O v0.11.2 restaura `motion_tracks` e `key_pose_bindings` exatamente ao baseline v0.11.0 e corrige somente QA integrity: thresholds declarados, comparação attack-v1 fail-closed e continuidade relacional da arma. O v0.11.1 permanece como rejected history; não há ComfyUI, SAM2, diffusion, edição manual de pixels ou melhoria visual.

## Quick start

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -q
python scripts/validation/validate_state_consistency.py
python scripts/validation/run_validation.py
python scripts/validation/run_animation_runtime_v0112.py
python scripts/validation/build_review_index_v0112.py --tests-count <N> --validation-checks <N> --json
python scripts/validation/validate_review_index_v0112.py docs/evidence/review-index-v0.11.2.json
python scripts/validation/run_cutout_rig_v073.py --json
python -m ugas.cli --version
```

Leia `docs/evidence/current-state.json` e siga os gates documentados em [REVIEW-v0.11.2.md](REVIEW-v0.11.2.md). O runtime SAM2, o bundle MediaPipe e os checkpoints históricos são externos; nenhum peso é distribuído com o repositório.

## Boundaries

O provider `deterministic-cutout-rig-2d` aceita somente humanoide frontal com RGBA R4 imutável. Usa `translation_rotation_bounded_uniform_scale`, escala uniforme entre `0.92..1.08`, proveniência de pixels de origem e zero pixels gerados. Os thresholds MediaPipe em [pose-thresholds-v054.json](docs/evidence/pose-thresholds-v054.json) são reutilizados sem alteração.

Somente o replay walk/front/8, o idle/front/12 histórico, o `attack-front-v1` histórico e o novo `attack-front-v2` front/12 deste slice são autorizados; não há outras animações/direções nem routing de produção. `REVIEW_INDEX_VERIFIED` é verificação local do índice, não aprovação externa.

Consulte [INSTALL.md](INSTALL.md), [CHECKPOINT.md](CHECKPOINT.md), [REVIEW-v0.11.2.md](REVIEW-v0.11.2.md) e [docs/evidence/current-state.json](docs/evidence/current-state.json). O REVIEW-v0.11.1 e suas evidências continuam disponíveis como rejected history.

## v0.11.2 QA integrity and scope recovery

O v0.11.2 mantém a camada genérica `motion_tracks[]`, restaura os valores visuais do v0.11.0 e liga hard gates aos thresholds semânticos declarados no perfil. A arma usa trajetória angular unwrapped, aceleração relacional coerente e continuidade direcional imediata pós-hit; não há thresholds numéricos novos calibrados de output. A saída source-only é 12 frames RGBA tecnicamente qualificada, mas a revisão visual externa continua `REQUIRED` e `production_routing=BLOCKED`.

## v0.11.0 motion quality layer (historical)

`motion_tracks[]` é opcional e usa IDs opacos, valores `scalar`/`vec2`, interpolação linear, smoothstep ou cubic Hermite determinística. O core valida, amostra e hashia as curvas; o adapter `attack_front_v2` interpreta seus canais. O pacote v2 é 6x2, 512x512, RGBA, 12 fps, non-loop, com hit no frame 6 e janela ativa 4–7. O resultado técnico é `CUTOUT_ANIMATION_RUNTIME_V2_ATTACK_FRONT_TECHNICALLY_QUALIFIED`; a revisão visual externa permanece `REQUIRED`.
## v0.10.0 reusable action runtime (historical)

The v0.10.0 historical release added optional hash-bound `event_markers[]` and generic loop/non-loop lifecycle semantics for `attack-front-v1`, a deterministic source-only 10-frame front sword action over the approved R4 cutout rig. Its evidence remains under `docs/evidence/animation-runtime-v0100/`; the active release is v0.11.2.
