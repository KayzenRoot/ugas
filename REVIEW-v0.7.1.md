# UGAS Review v0.7.1

## STATUS

`CUTOUT_RIG_SEAM_GAP` — execução local concluída e fail-closed. A revisão externa/artística ainda não foi reivindicada.

O estado mantém `provider_smoke_status` separado do gate atual. A história v0.6.2 permanece `SDXL_OPENPOSE_CONTROL_GAP_CONFIRMED_AT_MODEL_CARD_SETTINGS`, a decisão de pose histórica permanece `LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED`, o snapshot anterior permanece `REVIEW_ARCHIVE_VERIFIED`, e os manifests `sdxl-openpose-p-qualification.json` e `review-visuals-v0.6.1.json` continuam referências históricas, não gates ativos.

## VERSION

`0.7.1`; o release anterior `0.7.0` permanece preservado para comparação.

## PHASE

Correção de fidelidade e QA do provider determinístico `deterministic-cutout-rig-2d`, limitada a Q0, Q1 e Q2.

## OBJECTIVE

Corrigir anatomia target, fragmentação, fallback residual e métricas falsas do v0.7.0 mantendo R4, SAM2.1 Hiera Small, MediaPipe, thresholds históricos e zero geração ComfyUI.

## V0.7.0 EXTERNAL AUDIT FINDINGS

O audit identificou falsos verdes (false-positive paths) em hips colapsados, weapon target, ownership/masks, componentes torso/sword, joint patches, `seam_metrics`, internal QA, retention e overlays. O v0.7.1 não reescreve os artefatos históricos: adiciona evidências versionadas e torna os gates mensuráveis.

## TARGET HIP / SIDE MAPPING FIX

O adapter `target-skeleton-adapter-2.0-v0.7.1` preserva o centro pélvico, calcula `hip_left` e `hip_right` separadamente dentro da razão de largura `0.92..1.08`, e registra o mapeamento `anatomical_left=guide_right` / `anatomical_right=guide_left`.

## WEAPON ATTACHMENT FIX

A espada permanece presa a `wrist_right`, usa o ângulo local da fonte relativo ao antebraço e limita o swing a `+/-12°`. O target registra o corredor de torso protegido e falha se a lâmina o atravessar.

## RAW MASKS

SAM2 produz uma hipótese única por parte, sem união multimask. Os PNGs raw e o manifest `r4-cutout-raw-masks-v071-manifest.json` são hash-bound ao R4 e separados das máscaras refinadas.

## REFINED MASKS

O refinamento usa ownership semântico completo, cleanup por componentes e bandas de overlap derivadas da fonte. Nenhum pixel é inventado e nenhum residual da fonte é usado para completar Q0.

## COMPONENT QA

O gate semântico calcula `max(16 px, 0.25% da primary component)`, exige head primário, torso com no máximo 3 componentes significativos e sword com no máximo 2. Os contadores pós-blend são reportados separadamente das bandas intencionais para impedir falso verde.

## Q0 NO-RESIDUAL RECONSTRUCTION

Q0 é composto exclusivamente pelas onze partes RGBA transformadas pelo mesmo caminho do piloto. O gate exige alpha IoU `>=0.995`, RGB MAE `<=1.5`, bbox drift `<=1 px`, ownership semântico `>=0.995`, ownership estrito `>=0.99`, duplicate `<=0.01` e `source_residual_fallback_used=false`.

## JOINT BLENDING

O antigo patch 15x15 foi removido. O único overlap permitido para blending é uma banda circular de pixels já pertencentes ao R4 e é contabilizado na proveniência; `joint_patch_copy_count=0`.

## INTERNAL GEOMETRY QA REAL

Cada parte grava a matriz affine forward, pivôs/endpoints transformados, erro de ângulo, drift de osso e escala uniforme. Os gates são calculados desses valores; não há constantes de aprovação.

## SEAM / SAFE-MARGIN QA REAL

O QA calcula bbox alpha do output, margem mínima de 24 px, contato de borda, holes no corredor do torso, componentes, gaps de junta e overlap de occupancy antes/depois do blend. O resultado atual permanece `CUTOUT_RIG_SEAM_GAP`: Q1 tem `2222` pixels de overlap fora das juntas e Q2 `4477`; o gap não é relaxado.

## PIXEL RETENTION / PROVENANCE

A proveniência permanece source-only. Q0 e Q1 passam retention; Q2 permanece gap com retenção total `0.854145` e `right_thigh=0.710917`. Os valores são derivados dos pixels esperados versus pixels visíveis após z-order.

## Q1 CONTACT-LEFT

O output, target e skeleton detectado estão em `docs/evidence/`. A pose tem hips distintos, espada lateral e margem segura, mas falha seam por overlap/gap medido; permanece não qualificada.

## Q2 PASSING-LEFT

O output preserva fase lower-body distinta e espada fora do corredor protegido, mas falha seam por overlap medido e retention da coxa direita. Não autoriza walk.

## TARGET VS DETECTED OVERLAYS

`cutout-q1-q2-target-detected-overlays-v071.png` contém os skeletons target e MediaPipe detectados, vetores de erro e métricas sincronizadas com os outputs Q1/Q2.

## FINAL PROVIDER DECISION

`CUTOUT_RIG_SEAM_GAP`. A arquitetura foi corrigida e a evidência é reproduzível, mas a qualificação técnica final não é emitida enquanto os gates reais de seam/retention não passarem.

## NO COMFYUI / NO WALK

`comfyui_generation_jobs=0`, `sam3_used=false`, `walk=NOT_RUN`, spritesheet e GIF `NOT_RUN`. `walk_authorized=false` durante toda a execução.

## TESTS

Os 183 testes auditados do v0.7.0 foram preservados. O v0.7.1 adiciona regressões para hips/lados, arma, masks raw/refined, componentes, ownership, Q0 sem residual, affine forward, seam real, retention, overlays e limites de execução.

## VALIDATION

Os comandos finais são compileall, unittest, `run_validation.py`, qualificação SAM2, build canônico, pose-pilot e verificação do review ZIP. O resultado numérico final deve ser lido no `SUMMARY` e no manifest do ZIP.

## REVIEW ARCHIVE SELF-TEST

O ZIP v0.7.1 será produzido somente após a última modificação normal, conterá histórico v0.7.0 e será validado por `scripts/validation/verify_review_archive.py` em extração limpa.

## TRACKED SNAPSHOT / GITHUB

O destino é `https://github.com/csn1985-ship-it/ugas.git`, branch `main`. O requisito é `origin/main == HEAD` e working tree limpo após o push.

## SECURITY / LICENSES

O código e os manifests não contêm secrets. O SAM2 oficial e seu checkpoint permanecem externos ao Git e ao ZIP; o checkpoint é identificado por SHA-256. Licença e uso comercial devem seguir os termos upstream registrados na evidência.

## VISUAL REVIEW STATUS

Revisão visual humana externa: `PENDING`. A contact sheet local é evidência de comparação, não aprovação artística.

## BLOCKERS / GAPS

O blocker técnico atual é seam/retention: overlap fora das juntas em Q1/Q2, gap residual de junta medido e baixa retenção da coxa direita em Q2. Esses resultados são reportados, não convertidos em verde por mudança de threshold.

## DECISIONS

Preservar R4 e histórico; manter SAM2.1 Hiera Small e MediaPipe; remover residual e patches artificiais; manter routing, thresholds e walk bloqueados; publicar somente a evidência correta para auditoria externa.

## NEXT STEP

Auditoria externa do review ZIP v0.7.1 e, somente após decisão governada, uma nova correção de continuidade/retention. Walk/front/8 continua fora deste slice.

## DEFINITION OF DONE

Código, evidências, schemas, testes, documentação, validação e archive verifier estão preparados para revisão. A definição técnica completa de qualificação não é declarada porque Q1/Q2 ainda falham gates reais; `main` será publicado com esse estado honesto.

## REVIEW ZIP

`UGAS-REVIEW-v0.7.1-final-*.zip` será o último artefato materializado e deverá passar o verifier em extração limpa.
