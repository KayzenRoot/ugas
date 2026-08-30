# UGAS Review - Prompt 05 v0.6.0

## STATUS

`SDXL_OPENPOSE_CONTROL_GAP` — smoke factorial encerrado no stop condition de pose; nenhuma aprovação externa ou de produção é inferida.

## VERSION

`0.6.0`; o review tooling histórico do v0.5.5 permanece preservado.

## PHASE

`SDXL_CONTROL_POSE_PROVIDER_QUALIFICATION`

## OBJECTIVE

Responder, com evidência reproduzível, se SDXL + OpenPose ControlNet + IP-Adapter consegue combinar pose e identidade do personagem R4 em geração 2D a 512x512. Não executar walk, anchors, spritesheet, GIF, animação ou 3D.

## V0.5.5 BASELINE

Baseline público: commit `233bb911c5100d9fe837833ec7598790d36354d5`. O snapshot anterior é `REVIEW_ARCHIVE_VERIFIED`; a decisão histórica de pose é `LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED`, comprovada em `docs/evidence/v054-provider-qualification.json`. Os thresholds `docs/evidence/pose-thresholds-v054.json` não podem ser alterados.

## POSE GAP STRATEGY

O ControlNet recebe diretamente o guia PNG COCO-18 determinístico de UGAS, sem preprocessor. O IP-Adapter recebe somente a identidade R4. A lane FLUX não é substituída; SDXL é uma lane candidata separada.

## STATE CONSISTENCY

O estado atual é `SDXL_OPENPOSE_CONTROL_GAP`, após `STATE_CONSISTENCY_PASSED` e auditoria do custom node. `generation_provider_change_authorized=false`, `walk_authorized=false`, `new_generation_started=true` e `new_generation_jobs=3`. O v0.5.5 permanece histórico como `REVIEW_ARCHIVE_VERIFIED`; walk permanece não autorizado. O manifest histórico `review-visuals-v0.5.5.json` continua preservado.

## CUSTOM NODE AUDIT

`CUSTOM_NODE_AUDIT_PASSED` em `docs/evidence/custom-node-audit-ipadapter-plus.json`. Checkout externo em `a0f451a5113cf9becb0847b92884cb10cbdec0ef`; não há rede, subprocesso ou download dinâmico detectado. O loader opcional de embeddings com `torch.load` é risco residual e não entra no workflow qualificado.

## CUSTOM NODE PIN / LICENSE

O candidato é GPL-3.0 e fica local-only, sem source vendorizado no Git/ZIP. A manutenção upstream deve ser registrada; remoção/reinstalação usa o mesmo commit pinado e não remove modelos compartilhados.

## SDXL BASE MODEL

Candidate source: `stabilityai/stable-diffusion-xl-base-1.0`; licença declarada CreativeML Open RAIL++-M. Qualificação exige URL, revision, filename, bytes, SHA-256 e inventário local.

## OPENPOSE CONTROLNET MODEL

Candidate source: `xinsir/controlnet-openpose-sdxl-1.0`; licença declarada Apache-2.0. O arquivo exato e seu SHA-256 devem ser registrados antes de qualquer smoke.

## IP-ADAPTER MODEL

Candidate source: `h94/IP-Adapter`; variante preferida `ip-adapter-plus_sdxl_vit-h`, declarada Apache-2.0. Variante ambígua, licença desconhecida ou hash divergente bloqueiam a lane.

## CLIP VISION MODEL

O encoder ViT-H é uma dependência separada do IP-Adapter e deve ter registro próprio de source, revision, arquivo, bytes, SHA-256 e licença. Para `ip-adapter-plus_sdxl_vit-h`, o pareamento obrigatório é `OpenCLIP-ViT-H-14` em `models/image_encoder`; o encoder `sdxl_models/image_encoder` é ViT-bigG e não é aceito. A incompatibilidade observada no primeiro ensaio está preservada em `docs/evidence/sdxl-provider-variant-mismatch.json`.

## RUNTIME / RTX 5050

O doctor precisa registrar GPU, driver, VRAM total/livre, versão/commit do ComfyUI, PyTorch/CUDA, nós nativos ControlNet e nós IP-Adapter pinados observados em `/object_info`. Tentativas de 512 FP16, low-VRAM/offload e unload sequencial são obrigatórias antes de declarar `SDXL_CONTROL_PROVIDER_HARDWARE_GAP`.

## WORKFLOW TOPOLOGY

Workflow API separado: SDXL text conditioning → ControlNet pose opcional → IP-Adapter identity opcional → KSampler → VAE decode → BiRefNet/normalização → MediaPipe detected-joint QA e identity/weapon QA. P/I/PI compartilham prompt, anchor, guide, resolution, scheduler e seed por comparação.

## P / I / PI FACTORIAL SMOKE

P usa apenas SDXL + OpenPose ControlNet; I usa apenas SDXL + IP-Adapter; PI usa ambos. A execução autorizada começa com exatamente um seed novo de smoke; se houver technical pass, seguem três seeds novos pareados. O seed é evidência de reprodução, nunca critério de ranking.

## STRENGTH BENCHMARK

Somente após smoke técnico verde: ControlNet `[0.80, 1.00]`, IP-Adapter `[0.70, 0.90]`, quatro configurações PI, um seed fixo, start/end e `weight_type` explícitos. Se nenhum smoke técnico passar, este artefato não deve ser fabricado.

## POSE QA

Reutiliza sem alteração os thresholds v0.5.4: pelo menos 10 joints mensuráveis, PCK@.10 ≥ 0.80, NME ≤ 0.10, limb-angle MAE ≤ 18°, lower-body PCK ≥ 0.75, orientação correta, sanity e MediaPipe detected-joint. Silhueta legada não qualifica a lane.

## IDENTITY / WEAPON QA

Cada output precisa preservar face/head, armor palette/material, black cloth, proporções e espada. O IP-Adapter não pode copiar a pose R4; o ControlNet não pode substituir a identidade. Identidade e espada são hard gates.

## FINAL PROVIDER QUALIFICATION

Só `PI` confirmado em 3/3, com gates absolutos de pose, identidade, espada e causalidade, pode resultar em `SDXL_CONTROL_POSE_PROVIDER_QUALIFIED`. Caso contrário, registrar o gap exato e manter a capacidade não qualificada.

## CAPABILITY ROUTING

Somente uma lane SDXL explicitamente qualificada pode entrar em routing para `pose-controlled-character-generation` e `animation-frame-pose-generation`. A lane FLUX e a decisão histórica v0.5.4 permanecem separadas. Sem evidência qualificada, o router retorna capability gap.

## EXECUTION EVIDENCE

Registrar `custom-node-audit-ipadapter-plus.json`, qualificações dos quatro artefatos, `runtime-doctor-v0.6.0.json`, workflow, smoke/benchmark/confirmation quando autorizados, overlays, identity drift, qualification final e `execution-evidence-v0.6.0.json`. Não criar artefatos de fases não executadas.

## REGRESSION PROTECTION

Os 134 testes históricos v0.5.5 permanecem executáveis no snapshot limpo; os testes v0.6.0 cobrem pin, pareamento ViT-H, separação P/I/PI, seed inteiro, gates fail-closed, ausência de pesos/source e bloqueio de fases posteriores.

## TESTS

Preservar os 134 testes históricos v0.5.5 e adicionar testes de pin, auditoria, modelos/licenças/hashes, topology P/I/PI, guide direto, causalidade, routing e ZIP sem pesos/source.

## VALIDATION

Compileall, unittest, validação da repository, schema/state consistency e validação do review ZIP devem passar com saídas registradas.

## REVIEW ARCHIVE SELF-TEST

O ZIP final deve ser autoextraível para validação externa, preservar os artefatos históricos e excluir pesos, `.task`, segredos, ZIPs anteriores e source do custom node.

## TRACKED SNAPSHOT / GITHUB

A publicação exige branch `main` limpa e `origin/main==HEAD`; o status local é distinto de GitHub Actions, aprovação visual e deployment.

## SECURITY / DISTRIBUTION

Não incluir pesos no Git/ZIP. GPL-3.0 do custom node fica no boundary local-only. Qualquer licença desconhecida, hash mismatch, commit flutuante, download dinâmico ou conteúdo não auditado encerra a lane.

## VISUAL REVIEW STATUS

Pendente até existir contacto/overlay hash-bound dos jobs autorizados. Revisão visual humana continua necessária e não é inferida pelo script.

## BLOCKERS / GAPS

No checkpoint atual: auditoria, quatro hashes/licenças e doctor/runtime passaram. O smoke de um seed novo por lane executou P/I/PI, mas P falhou no pós-processamento técnico e I/PI falharam nos gates de pose detectada (PCK, NME, lower-body e orientação); o estado exato é `SDXL_OPENPOSE_CONTROL_GAP`. Benchmark, seeds pareados e confirmação não foram executados, e a lane não pode ser promovida sem uma nova decisão de escopo.

## DECISIONS

Nenhuma promoção para walk, anchors, animação ou produção. A decisão de pose v0.5.4 e o snapshot v0.5.5 são históricos e imutáveis.

## NEXT STEP

Revisar o gap de OpenPose e preservar a lane anterior v0.5.4. Não executar benchmark, confirmação, walk ou routing SDXL não qualificado; a ação `run_sdxl_controlled_walk_pilot` não está autorizada neste estado.

## DEFINITION OF DONE

Estado consistente, auditoria/licenças/hashes, runtime, topology P/I/PI, QA e causalidade, routing, testes, documentação, GitHub e review ZIP auto-validado. Um gap documentado também é conclusão válida do slice quando um stop condition é atingido.

## REVIEW ZIP

`review/UGAS-REVIEW-v0.6.0-<timestamp>.zip`, gerado por último e validado sem modificar o filesystem depois da geração.
