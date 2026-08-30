# UGAS Review - Prompt 05-D v0.6.2

## STATUS

`SDXL_OPENPOSE_CONTROL_GAP_CONFIRMED_AT_MODEL_CARD_SETTINGS` — P0, P1 e P2 foram executados com geração fresca na seed 62701; nenhum passou o Stage A. O gap histórico `SDXL_OPENPOSE_CONTROL_GAP` do v0.6.1 é preservado e confirmado sob o operating point publicado.

## VERSION

`0.6.2`; runtime, package, pyproject, schema e documentação corrente devem permanecer alinhados.

## PHASE

`SDXL_OPENPOSE_MODEL_CARD_CALIBRATION`.

## OBJECTIVE

Medir se o xinsir/controlnet-openpose-sdxl-1.0 obedece à pose quando o operating point publicado é respeitado, sem IP-Adapter, sem novo modelo/provider e sem mudar os thresholds congelados.

## V0.6.1 AUDIT RESULT

O baseline público é o commit `95e590360dc90b509be5e70495f5904af2eb489f`, branch `main`. A auditoria externa registrou 152 testes PASS e 500/500 checks no snapshot sem `.git`. O review v0.6.1 registra historicamente 151 testes e não será reescrito; este review registra o valor auditado de 152. P raw teve PCK@0.10=0.333333 e NME=0.550885; PI raw teve PCK@0.10=0.000000 e NME=0.827. O P BiRefNet failure permanece separado da pose. A evidência histórica v0.6.0 inclui `docs/evidence/v054-provider-qualification.json` e `docs/evidence/review-visuals-v0.6.0.json`.

## MODEL CARD CONFIGURATION FINDING

O operating point publicado informa `controlnet_conditioning_scale=1.0`, `num_inference_steps=30`, `EulerAncestralDiscreteScheduler` e orientação de resolução aproximadamente 1024x1024 ou mesmo bucket. O baseline UGAS 512/20/Euler/0.9 não é suficiente para abandonar o provider.

## STATE RECLASSIFICATION

O estado corrente usa `version=0.6.2`, `phase=SDXL_OPENPOSE_MODEL_CARD_CALIBRATION`, `historical_smoke_status=SDXL_OPENPOSE_CONTROL_GAP`, `current_gate=SDXL_OPENPOSE_CONTROL_GAP_CONFIRMED_AT_MODEL_CARD_SETTINGS`, `provider_smoke_status=SDXL_OPENPOSE_CONTROL_GAP_CONFIRMED_AT_MODEL_CARD_SETTINGS`, `walk_authorized=false` e `generation_provider_change_authorized=false`. A decisão histórica `LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED` e o snapshot `REVIEW_ARCHIVE_VERIFIED` permanecem preservados. `allowed_next_actions` contém somente a preservação/revisão da evidência produzida.

## P-ONLY SCOPE

Somente o workflow P derivado de `providers/workflows/sdxl-openpose-controlnet-p.api.json`, com SDXL Base 1.0 e xinsir OpenPose ControlNet. IP-Adapter, I, PI, identity R4, benchmark, anchors, walk e novo provider não são executados.

## MODEL CARD SOURCE

Fonte autoritativa: https://huggingface.co/xinsir/controlnet-openpose-sdxl-1.0. A página registra licença Apache-2.0, base SDXL e o exemplo com `EulerAncestralDiscreteScheduler`, scale 1.0, 30 steps e aproximadamente 1024 pixels. A revisão/URL e os valores observados ficam hash-bound em `docs/evidence/sdxl-openpose-config-matrix.json`.

## SAMPLER / SCHEDULER MAPPING

O runtime ComfyUI é consultado em `KSampler` via `object_info`; a equivalência registrada para `EulerAncestralDiscreteScheduler` é `sampler_name=euler_ancestral` e `scheduler=normal`, somente se ambos forem valores observados como válidos. P0 mantém `euler/normal` como baseline.

## RESOLUTION GUIDE RENDERING

Os guides P0/P1/P2 são renderizados diretamente do JSON COCO-18 em 512, 768 e 1024, com hashes do JSON, renderer e PNG registrados. A operação não redimensiona o PNG 512; escala coordenadas e primitives de desenho deterministicamente para cada bucket.

## RTX 5050 MEMORY STRATEGY

A ordem obrigatória é P0, P1, P2 normal. Se P2 emitir OOM, ocorre um único retry com a estratégia suportada do endpoint `/free` do ComfyUI para unload/free memory, mantendo 1024, 30 steps, Euler Ancestral e strength 1.0. Novo OOM produz substatus `SDXL_OPENPOSE_1024_HARDWARE_GAP`; nenhum PNG P2 é fabricado.

## P0 / P1 / P2 TRIAGE

P0, P1 e P2 foram executados sequencialmente na seed 62701. P0 e P1 produziram raw outputs sem pose MediaPipe mensurável; P2 produziu 7 joints mensuráveis, PCK@0.10=0.428571, NME=0.551963, limb-angle MAE=16.352462, lower-body PCK=1.0 e orientação correta, mas falhou nos gates de joints/PCK/NME e no gate técnico de forma humana. Não houve OOM nem retry P2.

## RAW POSE QA

Cada PNG bruto é processado pela política `raw_rgb_neutral_gray`, usando os thresholds imutáveis de `docs/evidence/pose-thresholds-v054.json`: pelo menos 10 joints, PCK@0.10 >= 0.80, NME <= 0.10, limb-angle MAE <= 18 graus, lower-body PCK >= 0.75 e orientação correta.

## HUMAN-FORM TECHNICAL QA

Sem aplicar identidade R4, o gate técnico exige uma detecção MediaPipe suficiente, uma pose primária, ausência de segunda pose detectável, ausência de corrupção de canvas/borda dominante e ausência de colapso puro em stencil/silhueta. Evidência insuficiente permanece `HUMAN_VISUAL_REVIEW_REQUIRED` e não é auto-aprovada.

## P-ONLY CONFIRMATION

Confirmation só pode executar se ao menos uma configuração passar a triagem Stage A. Nesse caso, a melhor configuração é escolhida por métricas de pose, não por runtime, e confirmada nas seeds 62711, 62712 e 62713. Se nenhuma passar, confirmation permanece `NOT_RUN`.

## FINAL P-LANE DECISION

Resultado: `SDXL_OPENPOSE_CONTROL_GAP_CONFIRMED_AT_MODEL_CARD_SETTINGS`. `stage_a_pass_count=0`; confirmation está `NOT_RUN`. Estados permitidos: `SDXL_OPENPOSE_P_LANE_QUALIFIED`, `SDXL_OPENPOSE_P_LANE_QUALIFIED_768`, `SDXL_OPENPOSE_CONTROL_GAP_CONFIRMED_AT_MODEL_CARD_SETTINGS` e `SDXL_OPENPOSE_1024_HARDWARE_GAP`.

## POSTPROCESS DIAGNOSTIC

BiRefNet não participa da qualificação P-only. Se executado como diagnóstico secundário, ocorre somente depois do raw pose QA e sua falha não altera a decisão de pose.

## EXECUTION EVIDENCE

`docs/evidence/execution-evidence-v0.6.2.json` deve ligar cada geração a prompt_id, history exato, raw PNG, SHA-256, target fresco, seed e graph P-only. P2 normal e retry são distinguíveis; outputs antigos não podem ser a única prova.

## TESTS

Os 152 testes auditados do v0.6.1 são preservados e os novos testes cobrem a matriz exata, mapeamento observado, graph sem IP-Adapter, rendering por JSON/resolução, seed 62701, retry P2 sem downgrade, confirmation condicional, BiRefNet independente, estado e snapshot sem Git.

## VALIDATION

Compileall, unittest, state-consistency, `run_validation.py`, comando P-only com `--json`, verificador do review ZIP e snapshot sem Git devem passar. Falhas interrompem a promoção.

## REVIEW ARCHIVE SELF-TEST

O ZIP deve conter o review v0.6.2, histórico v0.6.1/v0.6.0, matriz, runtime, guides, raw/overlays aplicáveis, execution evidence e executar compileall, testes e validação no snapshot extraído.

## TRACKED SNAPSHOT / GITHUB

`main` deve publicar o commit final, `origin/main == HEAD` e working tree limpo. Nenhum peso, bundle MediaPipe ou source GPL entra no Git ou no ZIP.

## SECURITY / LICENSES

Nenhum download ou instalação é feito nesta release. O pin `a0f451a5113cf9becb0847b92884cb10cbdec0ef` e sua fronteira GPL local-only permanecem preservados. A licença Apache-2.0 do model card é registrada como fonte do modelo, sem vendoring.

## VISUAL REVIEW STATUS

O review inclui a matriz P0/P1/P2, contato dos raw outputs, overlays P0/P1/P2, guides 512/768/1024 e, somente se executada, a evidência visual de confirmation. A revisão visual humana permanece separada da decisão técnica; production_approval=not-granted.

## BLOCKERS / GAPS

P0/P1/P2 completaram sem OOM ou erro de execução, mas todos falharam o raw pose gate; P0/P1 foram não mensuráveis e P2 ficou em 7 joints, PCK 0.428571 e NME 0.551963. O gate humano de P2 também falhou por detectabilidade insuficiente e colapso stencil/silhueta. I/PI/benchmark/anchors/walk e confirmation permanecem `NOT_RUN`.

## DECISIONS

Esta release testa primeiro o operating point do próprio model card e preserva thresholds, modelo, guide JSON e workflow P. Nenhum resultado será promovido por score agregado, runtime ou inferência visual não documentada.

## NEXT STEP

Preservar a evidência, revisar visualmente os raw outputs/overlays, executar a validação integral, publicar o commit em `main` e criar o ZIP por último.

## DEFINITION OF DONE

O model-card mismatch está documentado; P0/P1/P2 foram executados conforme hardware; raw pose ocorreu antes de qualquer pós-processamento; confirmation não rodou porque `stage_a_pass_count=0`; nenhum I/PI/benchmark/walk/anchor foi executado; os 152 testes históricos e os testes novos passam; checkout, git archive, snapshot sem Git e review ZIP passam; `main` está publicado e limpo; o ZIP será criado por último.

## REVIEW ZIP

`review/UGAS-REVIEW-v0.6.2-<timestamp>.zip`, criado por último e auto-validado sem alterações posteriores no filesystem.
