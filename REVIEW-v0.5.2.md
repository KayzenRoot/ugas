# UGAS review - v0.5.2

## STATUS

`LOCAL_POSE_CONTROL_PROVIDER_GAP`. O estado ativo é deliberadamente não qualificado e encerra a escalada desta execução.

## VERSION

`0.5.2` — PDF fonte: `PROMPT-04D-UGAS-POSE-CONTROL-ESCALATION-v0.5.2.pdf`.

## PHASE

`PROMPT-04D / POSE_CONTROL_ESCALATION`.

## OBJECTIVE

Obter controle robusto de pose em 2D no RTX 5050 com a menor intervenção local verificável, mantendo identidade, material, arma, transparência, hashes, ordem de referências e evidência de execução.

## V0.5.1 AUDIT RESULT

O resultado histórico auditado foi `MULTI_REFERENCE_POSE_CONTROL_GAP`: A teve média de pose `0.757982`, B `0.898232`, ganho causal `0.140250`, abaixo do limiar fixo `0.15`. As flags históricas de âncoras e walk são tratadas como `false` pelo estado atual; `REVIEW-v0.5.1.md` permanece separado e imutável.

## STATE CONSISTENCY FIX

`docs/evidence/current-state.json` é machine-authoritative. O checkpoint anterior que promovia âncoras e walk foi corrigido. O validador em `src/ugas/state_consistency.py` verifica versão, fase, R4, gap histórico, gate atual e linguagem de promoção contraditória antes de qualquer novo job.

## CURRENT STATE

`current_gate=LOCAL_POSE_CONTROL_PROVIDER_GAP`, `stop_reason=LOCAL_POSE_CONTROL_PROVIDER_GAP`, `state_consistency=STATE_CONSISTENCY_PASSED`. A Fase Zero terminou antes dos jobs; o ciclo nativo teve 9 submissões frescas, mas somente 5 registros técnicos completos por falhas de QA de transparência/RGB em B e C.

## OPENPOSE GUIDE V3

Concluído tecnicamente: renderer determinístico Pillow, fundo preto, skeleton COCO-18 colorido, juntas indisponíveis explícitas como `visible=false`, hashes JSON/PNG e separação entre controle e overlay de revisão. A revisão visual humana permanece requerida.

## NATIVE REFERENCE ORDER BENCHMARK

Executado com seeds 52701–52703 por lane. A foi identity-only; B identidade primeiro + pose segundo; C pose primeiro + identidade segundo. Houve 9 submissões; 5 registros técnicos completos vincularam workflow template/bound hash, prompt, referências, histórico e SHA-256. B e C não cumpriram 3/3 de QA técnico: cada uma teve 1/3 pontuação completa; A teve 3/3.

## NATIVE POSE QUALIFICATION

Não qualificada. A média de pose foi `0.894403`; B teve o único candidato pontuado em `0.979682` e C em `0.990737`, mas ambas falharam o requisito 3/3 e a evidência de arma/frescura da lane. Critérios imutáveis: 3/3 tecnicamente válidos, média de pose >= A + `0.15`, média >= `0.85`, piso >= `0.75`, identidade mínima vigente, arma 3/3 e três execuções frescas.

## REFCONTROL MODEL / LICENSE / HASH

Obrigatório após o gap nativo. O candidato exclusivo é `xocialize/refcontrol-FLUX.2-klein-4B-pose-lora`, arquivo `refcontrol-pose-klein-4b.safetensors`, SHA esperado `f9880f9070576ff1603c0988ed2afc9957deb0d7dd7c52cf15decbd4087f1339`, com licença Apache-2.0 revalidada no runtime. Pesos não entram no Git nem no review ZIP.

## REFCONTROL NATIVE LOADER QUALIFICATION

Concluído com loader nativo compatível por `/object_info`: `LoraLoaderModelOnly`, módulo `nodes`, sem custom nodes. O peso não foi incluído no Git nem no review ZIP.

## REFCONTROL STRENGTH BENCHMARK

Executado em `0.8`, `0.9`, `1.0`, com duas seeds de triagem por strength e uma terceira seed para a vencedora (`0.8`). Resultados: 0.8 média `0.992258`, ganho `+0.097855`, piso `0.991656`; 0.9 média `0.990159`, ganho `+0.095757`; 1.0 média `0.992154`, ganho `+0.097751`. Nenhum atingiu o ganho causal `+0.15`, portanto nenhum lane foi qualificado.

## POSE CONTROL FINAL GATE

Não alcançado. O RefControl confirmou hash esperado `f9880f...7f1339`, 92.426.792 bytes, Apache-2.0 e loader nativo, mas não cumpriu o ganho causal. O estado final é `LOCAL_POSE_CONTROL_PROVIDER_GAP`; nenhum resultado foi promovido por aproximação visual ou por bounding box.

## IDENTITY FIDELITY

O anchor canônico é R4 `revision-3a425d184b1a49be9f6d6c8d52d04b96`, SHA `7c2d0ea531de5996bd747971c9daedef60a5ca9f2e5b57b2a52f80c05f8f5798`. A métrica regional de identidade e o hard gate da arma serão preservados no ciclo novo.

## DIRECTIONAL ANCHORS V3

Bloqueadas até `POSE CONTROL FINAL GATE`. Nenhum arquivo de âncora v3 é fabricado nesta revisão enquanto a lane não for qualificada.

## WALK FRONT 8 V3

Bloqueado até pose qualificada e âncoras v3 aprovadas tecnicamente. O walk v2 histórico não é reclassificado pelo v0.5.2.

## FRAME QA

Não aplicável antes da lane e das âncoras. Quando autorizado, cada frame deverá passar transparência, clipping, escala, pivô, ground, pose, identidade e arma.

## TEMPORAL QA

Não aplicável. O contrato v3 preservará mirror da meia-ciclo, robustez estatística, closure, drift, identidade, arma, ausência de chaining e 8/8.

## PACKING

Bloqueado. Nenhum spritesheet, GIF ou pacote de walk v3 é aceito antes da QA final.

## EXECUTION EVIDENCE

Concluída em [`docs/evidence/execution-evidence-v0.5.2.json`](docs/evidence/execution-evidence-v0.5.2.json), com ciclos nativo e RefControl separados, hashes, seeds, workflow IDs, ordem das referências, histórico e `previous_frame_chaining=false`. A completude de prompt/history do ciclo RefControl é `false` porque o conjunto não chegou a 9 registros completos; isso sustenta o stop, não uma aprovação.

## TESTS

A suíte histórica v0.5.1 permanece preservada. A versão 0.5.2 adiciona testes para consistência de estado, COCO-18 determinístico, diferença B/C, limiar sem promoção, loader/hash RefControl, strength, identidade/arma e bloqueio de escalada.

## VALIDATION

Pendente até a execução final: testes completos, validador, schemas, snapshot sem Git, publicação e auditoria read-only do ZIP.

## TRACKED SNAPSHOT / GITHUB

Repositório: `https://github.com/csn1985-ship-it/ugas`. O SHA público e o estado final serão registrados somente após commit, validação e push verificáveis.

## SECURITY

Sem cloud, serviço pago, executável, nó customizado ou loader LoRA customizado. Segredos, pesos e caches permanecem fora do Git. URLs e licenças serão registradas somente com evidência verificável.

## VISUAL REVIEW STATUS

Revisão visual humana ainda não concedida para a lane v0.5.2.

## BLOCKERS / GAPS

O gap histórico exigiu A/B/C e RefControl. Ambos falharam os critérios de promoção: A/B/C por QA técnico incompleto em B/C e RefControl por ganho máximo +0.097855, abaixo de +0.15. O estado final é um stop explícito, não uma aprovação.

## DECISIONS

Manter o limiar de ganho `0.15`; usar COCO-18 v3 determinístico; manter R4 exato; separar controle de overlay; selecionar pose, depois identidade, margens/escala e seed apenas como desempate; não gerar âncoras ou walk sem qualificação.

## NEXT STEP

Consolidar o stop, executar os validadores/testes finais, publicar o commit e gerar o review ZIP como última escrita.

## DEFINITION OF DONE

Estado sem contradição, guias v3 auditáveis, ambos os caminhos de pose avaliados, identidade/arma preservadas nos resultados elegíveis, âncoras e walk mantidos bloqueados, QA/evidências completas, testes verdes, GitHub sincronizado e review ZIP auditado. A qualificação positiva de pose não foi alcançada.

## REVIEW ZIP

Será criado ao final como última escrita: `review/UGAS-REVIEW-v0.5.2-*.zip`. Até lá, este documento é um registro de trabalho não qualificado.
