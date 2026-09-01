# REVIEW-v0.11.2 — QA Integrity and Scope Recovery

## 1 RESUMO

O prompt `PROMPT-CORRETIVO-UGAS-QA-INTEGRITY-SCOPE-RECOVERY-v0.11.2.pdf` foi executado como uma correção de integridade QA e recuperação de escopo. O resultado local é `decision=QUALIFIED` para o mesmo `attack-front-v2`, sem nova geração, sem melhoria visual e sem alteração de animação. A revisão visual externa permanece obrigatória.

Status ativo: `CUTOUT_ANIMATION_RUNTIME_V2_ATTACK_FRONT_TECHNICALLY_QUALIFIED`; `attack_front_v2_external_visual=REQUIRED`; `production_approved=false`; `production_routing=BLOCKED`. O único próximo passo permitido é `external_review_attack_front_v2_v0112`.

## 2 BASELINE

Baseline público e visual restaurado: v0.11.0, commit `9401c31f994e968149292b2993d960d3aafc37c4`. Base da implementação v0.11.2 e histórico rejeitado: HEAD anterior `f386c490a6d7289befc1c8a34c84eff1d2b1cc96`. O v0.11.1 continua como rejected history; nenhum commit histórico foi reescrito, squashado ou apagado.

O SHA final de publicação deve ser resolvido pelo revisor externo; o executor não o autoafirma.

## 3 ARQUIVOS

As fontes ativas são `profiles/animation/attack-front-v2.json` e `src/ugas/animation_profiles/attack_front_v2.py`. Os gates e artefatos estão em `docs/evidence/animation-runtime-v0112/`. O estado ativo é `docs/evidence/current-state.json`, o índice é `docs/evidence/review-index-v0.11.2.json`, e os validadores são `scripts/validation/run_validation.py`, `scripts/validation/validate_state_consistency_v0112.py` e `scripts/validation/validate_review_index_v0112.py`.

## 4 COMO O DESVIO FOI CORRIGIDO

O desvio do v0.11.1 era de escopo: a correção anterior alterava os valores ativos de `motion_tracks` e `key_pose_bindings` e criava uma lane numérica de weapon continuity. O v0.11.2 restaura esses dois contratos ao v0.11.0 e limita a mudança à integridade QA. O v0.11.1 e sua evidência permanecem intactos como rejected history.

Não foram alterados rig, máscaras, skeleton source, z-order, markers, timing, pixels, provider, ComfyUI, SAM2 ou direção/animação adicional.

## 5 PROVA DE RESTAURAÇÃO

`motion_tracks` e `key_pose_bindings` do perfil ativo são semanticamente iguais ao snapshot `profiles/animation/attack-front-v2-v0.11.0.json`. O hash de tracks é `ba8ab5f4426052ff701471c1a692a2fa52c684e1ad9428626602c01564e2646a` no perfil, compiled manifest, QA e package. A verificação foi feita antes do primeiro PNG.

## 6 THRESHOLDS

Os literais existentes foram migrados para `qa_profile.thresholds` e são consumidos pelo adapter sem duplicação de decision literals:

| Campo semântico | Valor preservado |
|---|---:|
| `body_root_path_min_px` | 2.0 |
| `torso_rotation_range_min_deg` | 2.0 |
| `left_wrist_counter_path_min_px` | 1.0 |
| `head_counter_motion_max_deg` | 4.0 |
| `root_horizontal_excursion_min_px` | 2.0 |
| `root_horizontal_excursion_max_px` | 6.0 |
| `root_vertical_excursion_min_px` | 1.0 |
| `root_vertical_excursion_max_px` | 5.0 |

O gate NC-06 prova que threshold impossível falha fechado.

## 7 BASELINE attack-v1

A comparação usa somente o caminho conhecido `profiles/animation/attack-front-v1.json`, autoridade `c11196e5e854a0fbc6ec62e959de5ecc28d492ce` e SHA-256 imutável `8634852cba11a545668587251f775c248f712174a483b9a05cfd8d2117bf6f0d`. Caminho ausente, leitura inválida, hash divergente ou schema divergente tornam a referência indisponível e falham fechado; não há fallback `None`.

## 8 ACCELERATION

A arma usa uma referência angular unwrapped robusta em torno de `-180/180`, com todos os deltas calculados nessa mesma referência. A regra é relacional: o pico de velocidade angular absoluta na janela ativa deve superar o pico pré-ativo; as velocidades pré-hit devem manter o mesmo sinal do strike e apresentar crescimento coerente; jitter, desaceleração incoerente e reversão imediata falham. O caminho pós-hit deve ser maior que zero e manter o sinal do strike na transição imediata. NC-07 e NC-08 são `WEAPON_ARC_GAP`.

## 9 NC-01 a NC-10

| Controle | Resultado | Gate |
|---|---|---|
| NC-01 curvas malformadas | REJECTED | schema/curve integrity |
| NC-02 root/torso isolado | REJECTED | `BODY_MECHANICS_GAP` |
| NC-03 braço direito isolado | REJECTED | `BODY_MECHANICS_GAP` |
| NC-04 braço esquerdo/cabeça isolado | REJECTED | `BODY_MECHANICS_GAP` |
| NC-05 attack-v1 ausente/incorreto | REJECTED | fail closed |
| NC-06 threshold impossível | REJECTED | gate fail |
| NC-07 aceleração incoerente | REJECTED | `WEAPON_ARC_GAP` |
| NC-08 reversão/snap imediato | REJECTED | `WEAPON_ARC_GAP` |
| NC-09 foot slide | REJECTED | `FOOT_GROUND_GAP` |
| NC-10 QUALIFIED com hard gate falso | REJECTED | package fail |

O conjunto está em `negative-controls-v0112.json` com status `NC_01_TO_NC_10_PASSED`.

## 10 TESTES

Comando: `python -m unittest discover -s tests -q`. Resultado direcionado: 72 testes, 72 passed. O resultado da suíte completa será registrado no review após a execução final.

## 11 VALIDATION

Comando: `python scripts/validation/run_validation.py`. Ele valida schemas, estado, identidade semântica, artefatos ativos, controles negativos, replay histórico, limites de execução, docs, compileall e a suíte unitária. O número final de checks será registrado no índice após a execução final.

## 12 PIXEL IDENTITY

`PIXEL_IDENTITY_V0110_PASSED`: os 12 `frame-00.png`–`frame-11.png`, `attack-front-v2-spritesheet.png` e `attack-front-v2-preview.gif` v0.11.2 são byte-identical aos artefatos v0.11.0. O manifest visual também contém os 12 overlays target/detected, com hashes verificados. Nenhum pixel novo foi gerado.

## 13 HISTORICAL REPLAY

`HISTORICAL_REPLAY_V0112_PASSED`: `REVIEW-v0.11.1.md`, o historical replay, execution evidence e QA result v0.11.1 permanecem content-identical ao commit `f386c490a6d7289befc1c8a34c84eff1d2b1cc96` após normalização de line endings. A diferença física de line endings em arquivos textuais não é tratada como alteração de conteúdo; binários exigem igualdade bruta.

## 14 PENDENCIAS

A pendência é exclusivamente `external_review_attack_front_v2_v0112`. A revisão visual externa de attack-v2 é `REQUIRED`; produção continua bloqueada. `REVIEW_INDEX_VERIFIED` é evidência local, não aprovação externa.

## 15 EVIDENCE

Os artefatos principais são `identity-proof-v0112.json`, `threshold-binding-v0112.json`, `attack-v1-baseline-fail-closed-v0112.json`, `attack-v2-body-mechanics-qa-v0112.json`, `attack-v2-temporal-qa-v0112.json`, `attack-v2-weapon-arc-qa-v0112.json`, `attack-v2-foot-ground-qa-v0112.json`, `negative-controls-v0112.json`, `historical-replay-v0112.json`, `qa-integrity-scope-recovery-v0112.json`, `execution-evidence-v0.11.2.json` e `attack-v2-visual-manifest-v0112.json`. Todos estão relacionados no review index com SHA-256.

## 16 CURRENT-STATE

O estado machine-authoritative é v0.11.2 em `docs/evidence/current-state.json`: fase `REUSABLE_DETERMINISTIC_ANIMATION_RUNTIME`, gate `CUTOUT_ANIMATION_RUNTIME_V2_ATTACK_FRONT_TECHNICALLY_QUALIFIED`, `new_generation=0`, `sam2_runs=0`, `comfyui_generation_jobs=0`, `diffusion_runs=0`, `production_routing=BLOCKED` e próximo passo único `external_review_attack_front_v2_v0112`. As decisões históricas permanecem `SDXL_OPENPOSE_CONTROL_GAP_CONFIRMED_AT_MODEL_CARD_SETTINGS` e `LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED`; elas não são o status ativo.

## 17 LOCAL_TECHNICAL_QUALIFIED

Localmente, o pacote é tecnicamente qualificado: `decision=QUALIFIED`, todos os hard gates verdadeiros, QA integrity e scope recovery passaram, pixels preservados e negative controls passaram. Isso não equivale a aprovação visual externa nem autoriza produção. Walk permanece `pilot_only`; histórico v0.11.0 e rejected history v0.11.1 não são a base visual ativa.

## DEFINITION OF DONE

- [x] baseline v0.11.0 restaurado em tracks/bindings;
- [x] QA thresholds semânticos e fail-closed;
- [x] weapon rules relacionais e controles NC-01..NC-10;
- [x] pixel identity e historical replay comprovados;
- [x] estado, docs, schemas, evidências e review index preparados;
- [x] zero generation e produção bloqueada;
- [ ] revisão visual externa de `attack-front-v2` — pendente e explicitamente não reivindicada.
