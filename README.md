# UGAS 0.14.0

Universal Game Asset Studio: pipeline local-first para assets 2D com evidência reproduzível, transparência e governança de revisão. O release ativo executa somente HIT_REACTION_FRONT determinístico sobre o cutout R4 aprovado, mantém o dashboard Dockerizado always-on/read-only/local e não habilita produção.

O v0.13.1 permanece o piloto aprovado de RUN_FRONT_V1. O v0.13.0, v0.12.0, v0.12.1 e v0.12.2 permanecem preservados como rejected/history evidence. O v0.11.2 permanece preservado como release anterior: sua decisão visual externa é `APPROVED_PILOT` para pipeline/piloto, nunca aprovação de produção.

[![UGAS CI](https://github.com/csn1985-ship-it/ugas/actions/workflows/ugas-ci.yml/badge.svg?branch=main)](https://github.com/csn1985-ship-it/ugas/actions/workflows/ugas-ci.yml) [![UGAS review evidence](https://github.com/csn1985-ship-it/ugas/actions/workflows/ugas-review.yml/badge.svg?branch=main)](https://github.com/csn1985-ship-it/ugas/actions/workflows/ugas-review.yml)

## Quick start

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -q
python scripts/validation/validate_state_consistency.py
python scripts/validation/run_validation.py
python scripts/validation/run_animation_runtime_v0140.py
python scripts/validation/run_observability_v0122.py
python scripts/validation/build_review_index_v0122.py --json
python scripts/validation/validate_review_index_v0122.py docs/evidence/review-index-v0.12.2.json
docker compose -f compose.yaml -f compose.gpu.yaml up -d --build
pwsh -ExecutionPolicy Bypass -File scripts/docker/ugas-dashboard-status.ps1
python scripts/validation/run_animation_runtime_v0112.py
python scripts/validation/build_review_index_v0112.py --tests-count <N> --validation-checks <N> --json
python scripts/validation/validate_review_index_v0112.py docs/evidence/review-index-v0.11.2.json
python scripts/validation/run_cutout_rig_v073.py --json
python -m ugas.cli --version
python -m ugas.cli dashboard --host 127.0.0.1 --port 8765 --no-open
```

Leia `docs/evidence/current-state.json` e siga os gates documentados em [REVIEW-v0.14.0.md](REVIEW-v0.14.0.md). O runtime SAM2, o bundle MediaPipe e os checkpoints históricos são externos; nenhum peso é distribuído com o repositório.

## v0.13.1 RUN_FRONT_V1 flight/QA visual integrity

The active phase is `RUN_FRONT_V1` and the local gate is `CUTOUT_ANIMATION_RUNTIME_V1_RUN_FRONT_TECHNICALLY_QUALIFIED`. The eight-frame front run uses twelve declarative motion tracks, source-only R4 pixels, real airborne frames 3 and 7, immutable-base approved-asset identity, decoded GIF timing, and NC-01..NC-12. Use the GitHub-first PR -> Actions -> external visual review sequence in [docs/github-review-protocol.md](docs/github-review-protocol.md). `CAPABILITY_COUNT=16`, `production_approved=false`, `production_routing=BLOCKED`, `new_generation=0`, and `external_visual=REQUIRED`. PR #3 remains OPEN.

## Historical v0.13.0 RUN_FRONT_V1

The v0.13.0 technically qualified package remains frozen in [REVIEW-v0.13.0.md](REVIEW-v0.13.0.md) and `docs/evidence/animation-runtime-v0130/`. External visual review rejected that slice; it is not the active status.

## Historical v0.12.2 QA cache and Docker always-on local observability

O dashboard Dockerizado fica em `http://127.0.0.1:8765/`, usa `restart: unless-stopped`, monta o repositório somente para leitura e `.ugas/runtime` para persistência SQLite WAL. A aplicação só aceita `0.0.0.0` dentro do container confiável (`UGAS_CONTAINERIZED=1`); invocações nativas continuam loopback-only. Use `pwsh -ExecutionPolicy Bypass -File scripts/docker/ugas-dashboard-up.ps1` para build/start e `scripts/docker/ensure-dashboard-online.ps1` para autostart idempotente.

O banco local fica em `.ugas/runtime/telemetry.db` (SQLite WAL) e é ignorado pelo Git. GPU ausente é reportada como `GPU_CONTAINER_RUNTIME_GAP` ou `GPU_UNAVAILABLE` com motivo; timeouts preservam `stale_last_known` sem zero fabricado. O QA expõe HEAD/worktree/cache fingerprint e invalida PASS quando o repositório muda. A UI não usa `innerHTML` para dados não confiáveis e as respostas incluem CSP, nosniff e referrer policy.

## ALWAYS_ON_DASHBOARD_POLICY

Depois de aprovado tecnicamente, o dashboard deve permanecer online durante o desenvolvimento. Após qualquer alteração de observabilidade/runtime, execute o ensure/up idempotente e verifique `/api/status` e `/api/health`. A política é local, read-only e não inicia nem migra o ComfyUI.

## v0.12.1 local observability (rejected history)

O v0.12.1 permanece preservado em `REVIEW-v0.12.1.md`, `docs/evidence/observability-v0121/` e `docs/evidence/current-state-v0.12.1.json`. A correção v0.12.2 não reescreve essa evidência.

## v0.12.0 local observability (rejected history)

O MVP original permanece em `REVIEW-v0.12.0.md`, `docs/evidence/observability-v0120/` e `docs/evidence/current-state-v0.12.0.json`. A correção v0.12.1 não reescreve essa evidência.

## Boundaries

O provider `deterministic-cutout-rig-2d` aceita somente humanoide frontal com RGBA R4 imutável. Usa `translation_rotation_bounded_uniform_scale`, escala uniforme entre `0.92..1.08`, proveniência de pixels de origem e zero pixels gerados. Os thresholds MediaPipe em [pose-thresholds-v054.json](docs/evidence/pose-thresholds-v054.json) são reutilizados sem alteração.

Somente o replay walk/front/8, o idle/front/12 histórico, o `attack-front-v1` histórico e o novo `attack-front-v2` front/12 deste slice são autorizados; não há outras animações/direções nem routing de produção. `REVIEW_INDEX_VERIFIED` é verificação local do índice, não aprovação externa.

Consulte [INSTALL.md](INSTALL.md), [CHECKPOINT.md](CHECKPOINT.md), [REVIEW-v0.12.2.md](REVIEW-v0.12.2.md) e [docs/evidence/current-state.json](docs/evidence/current-state.json). Os reviews v0.12.0 e v0.12.1 permanecem disponíveis como rejected history.

## v0.11.2 QA integrity and scope recovery

O v0.11.2 mantém a camada genérica `motion_tracks[]`, restaura os valores visuais do v0.11.0 e liga hard gates aos thresholds semânticos declarados no perfil. A arma usa trajetória angular unwrapped, aceleração relacional coerente e continuidade direcional imediata pós-hit; não há thresholds numéricos novos calibrados de output. A saída source-only é 12 frames RGBA tecnicamente qualificada, mas a revisão visual externa continua `REQUIRED` e `production_routing=BLOCKED`.

## v0.11.0 motion quality layer (historical)

`motion_tracks[]` é opcional e usa IDs opacos, valores `scalar`/`vec2`, interpolação linear, smoothstep ou cubic Hermite determinística. O core valida, amostra e hashia as curvas; o adapter `attack_front_v2` interpreta seus canais. O pacote v2 é 6x2, 512x512, RGBA, 12 fps, non-loop, com hit no frame 6 e janela ativa 4–7. O resultado técnico é `CUTOUT_ANIMATION_RUNTIME_V2_ATTACK_FRONT_TECHNICALLY_QUALIFIED`; a revisão visual externa permanece `REQUIRED`.
## v0.10.0 reusable action runtime (historical)

The v0.10.0 historical release added optional hash-bound `event_markers[]` and generic loop/non-loop lifecycle semantics for `attack-front-v1`, a deterministic source-only 10-frame front sword action over the approved R4 cutout rig. Its evidence remains under `docs/evidence/animation-runtime-v0100/`; the active release is v0.12.1.
