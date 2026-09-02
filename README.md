# UGAS 0.12.1

Universal Game Asset Studio: pipeline local-first para assets 2D com ComfyUI nativo, evidência reproduzível, transparência e governança de revisão. O release ativo corrige a integridade, segurança e precisão do dashboard local read-only, near-real-time, sem telemetria remota.

O v0.12.0 permanece preservado como rejected history. O v0.11.2 permanece preservado como release anterior: sua decisão visual externa é `APPROVED_PILOT` para pipeline/piloto, nunca aprovação de produção.

## Quick start

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -q
python scripts/validation/validate_state_consistency.py
python scripts/validation/run_validation.py
python scripts/validation/run_observability_v0121.py
python scripts/validation/build_review_index_v0121.py --tests-count <N> --validation-checks <N> --json
python scripts/validation/validate_review_index_v0121.py docs/evidence/review-index-v0.12.1.json
python scripts/validation/run_animation_runtime_v0112.py
python scripts/validation/build_review_index_v0112.py --tests-count <N> --validation-checks <N> --json
python scripts/validation/validate_review_index_v0112.py docs/evidence/review-index-v0.11.2.json
python scripts/validation/run_cutout_rig_v073.py --json
python -m ugas.cli --version
python -m ugas.cli dashboard --host 127.0.0.1 --port 8765 --no-open
```

Leia `docs/evidence/current-state.json` e siga os gates documentados em [REVIEW-v0.12.1.md](REVIEW-v0.12.1.md). O runtime SAM2, o bundle MediaPipe e os checkpoints históricos são externos; nenhum peso é distribuído com o repositório.

## v0.12.1 observability integrity correction

`python -m ugas.cli dashboard` abre o dashboard local em `127.0.0.1:8765`. Use `--port 0` para um smoke test efêmero, `--no-open` para não abrir o navegador e `--host` somente com um endereço loopback. A UI é estática, sem CDN/build chain, e expõe apenas GET read-only: status, sistema/GPU/processos, ComfyUI, jobs com estágios reais, assets allowlisted, QA fail-closed, health, eventos e stream SSE.

O banco local fica em `.ugas/runtime/telemetry.db` (SQLite WAL) e é ignorado pelo Git. GPU ausente é reportada como `GPU_UNAVAILABLE` com motivo; timeouts preservam `stale_last_known` sem zero fabricado. A UI não usa `innerHTML` para dados não confiáveis e as respostas incluem CSP, nosniff e referrer policy.

## v0.12.0 local observability (rejected history)

O MVP original permanece em `REVIEW-v0.12.0.md`, `docs/evidence/observability-v0120/` e `docs/evidence/current-state-v0.12.0.json`. A correção v0.12.1 não reescreve essa evidência.

## Boundaries

O provider `deterministic-cutout-rig-2d` aceita somente humanoide frontal com RGBA R4 imutável. Usa `translation_rotation_bounded_uniform_scale`, escala uniforme entre `0.92..1.08`, proveniência de pixels de origem e zero pixels gerados. Os thresholds MediaPipe em [pose-thresholds-v054.json](docs/evidence/pose-thresholds-v054.json) são reutilizados sem alteração.

Somente o replay walk/front/8, o idle/front/12 histórico, o `attack-front-v1` histórico e o novo `attack-front-v2` front/12 deste slice são autorizados; não há outras animações/direções nem routing de produção. `REVIEW_INDEX_VERIFIED` é verificação local do índice, não aprovação externa.

Consulte [INSTALL.md](INSTALL.md), [CHECKPOINT.md](CHECKPOINT.md), [REVIEW-v0.12.1.md](REVIEW-v0.12.1.md) e [docs/evidence/current-state.json](docs/evidence/current-state.json). O REVIEW-v0.12.0 e o REVIEW-v0.11.1 permanecem disponíveis como rejected history.

## v0.11.2 QA integrity and scope recovery

O v0.11.2 mantém a camada genérica `motion_tracks[]`, restaura os valores visuais do v0.11.0 e liga hard gates aos thresholds semânticos declarados no perfil. A arma usa trajetória angular unwrapped, aceleração relacional coerente e continuidade direcional imediata pós-hit; não há thresholds numéricos novos calibrados de output. A saída source-only é 12 frames RGBA tecnicamente qualificada, mas a revisão visual externa continua `REQUIRED` e `production_routing=BLOCKED`.

## v0.11.0 motion quality layer (historical)

`motion_tracks[]` é opcional e usa IDs opacos, valores `scalar`/`vec2`, interpolação linear, smoothstep ou cubic Hermite determinística. O core valida, amostra e hashia as curvas; o adapter `attack_front_v2` interpreta seus canais. O pacote v2 é 6x2, 512x512, RGBA, 12 fps, non-loop, com hit no frame 6 e janela ativa 4–7. O resultado técnico é `CUTOUT_ANIMATION_RUNTIME_V2_ATTACK_FRONT_TECHNICALLY_QUALIFIED`; a revisão visual externa permanece `REQUIRED`.
## v0.10.0 reusable action runtime (historical)

The v0.10.0 historical release added optional hash-bound `event_markers[]` and generic loop/non-loop lifecycle semantics for `attack-front-v1`, a deterministic source-only 10-frame front sword action over the approved R4 cutout rig. Its evidence remains under `docs/evidence/animation-runtime-v0100/`; the active release is v0.12.1.
