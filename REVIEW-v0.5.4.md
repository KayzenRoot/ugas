# UGAS Review - Prompt 04F v0.5.4

## STATUS

`BLOCKED / LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED`. A qualificação do estimador QA passou, o runtime nativo executou exatamente 9 outputs frescos, e C/R falharam a pose medida por juntas. Identidade e arma passaram separadamente. Não é aprovação externa nem aprovação de produção.

## VERSION

`0.5.4`

## PHASE

`PROMPT-04F / POSE_LANE_RECHECK`

## OBJECTIVE

Resolver o bloqueio de licença do estimador, comprovar detectabilidade em R4/referência editada/8 frames históricos, congelar thresholds antes dos jobs e executar somente A/C/R com evidência de binding fresco. Preservar o R4 e parar se o provider não demonstrar controle causal de pose.

## V0.5.3 HISTORICAL BASELINE

`REVIEW-v0.5.3.md` e suas evidências permanecem imutáveis. O v0.5.3 terminou em `POSE_QA_MODEL_LICENSE_GAP`; sua correção do gate impossível permanece registrada como `POSE_METRIC_GATE_DESIGN_GAP`. O estado ativo não transforma esse resultado histórico em aprovação.

## LICENSE RESOLUTION

O MediaPipe Pose Landmarker Full foi resolvido como ferramenta QA-only local. A evidência registra a documentação oficial do [Pose Landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker), o [model card BlazePose GHUM 3D](https://storage.googleapis.com/mediapipe-assets/Model%20Card%20BlazePose%20GHUM%203D.pdf), a licença Apache-2.0 e o hash do bundle local de 9.398.198 bytes. `POSE_QA_LOCAL_USE_LICENSE_RESOLVED` não autoriza redistribuição do `.task`: ele está fora do Git e fora deste ZIP.

## POSE QA ESTIMATOR QUALIFICATION

MediaPipe `0.10.35` foi importado e executado fora do grafo ComfyUI. A detecção foi mensurável em R4, na referência editada e nos 8 frames históricos. A mediana foi 13 juntas mensuráveis, a cobertura dos joints centrais passou 100%, a inversão esquerda/direita foi 0 e todos os sanity checks passaram. O overlay [pose-qa-estimator-overlays-contact-sheet.png](docs/evidence/pose-qa-estimator-overlays-contact-sheet.png) foi materializado para revisão humana.

## PREPROCESSING MATRIX

Foram avaliadas as políticas `transparent_neutral_gray`, `transparent_white`, `full_body_crop_margin_25` e `full_body_crop_margin_25_upscale_2x`. Uma só política global foi escolhida antes do uso em outputs: `transparent_neutral_gray`. Não houve escolha por imagem.

## THRESHOLDS FROZEN BEFORE JOBS

Os valores estão em [pose-thresholds-v054.json](docs/evidence/pose-thresholds-v054.json), criado antes de qualquer nova submissão. O gate absoluto exige PCK@0.10 `>=0.80`, NME `<=0.10`, erro angular `<=18°`, lower-body PCK `>=0.75`, orientação correta e pelo menos 10 joints mensuráveis. O gate causal exige os gates absolutos em todos os outputs e redução de erro `>=35%` ou ganho normalizado `>=50%`, além de identidade/arma e binding fresco.

## NATIVE LANE RECHECK

A foi o baseline de identidade-only; C foi native pose-first + identity-second; ambas usaram FLUX.2 Klein Base e as três seeds `54701`, `54702`, `54703`. As 9 execuções têm prompt ID, history key, output hash e `fresh_binding=true`; não houve frame anterior encadeado.

A teve mediana de pose `0.241770`, identidade aprovada e PCK `0.000`. C teve mediana de pose `0.000000`; seus três outputs falharam o gate absoluto, embora a identidade/arma tenha passado. Os erros completos estão em [v054-pose-error-table.json](docs/evidence/v054-pose-error-table.json).

## REFCONTROL LANE RECHECK

R usou exclusivamente o loader nativo `LoraLoaderModelOnly`, o LoRA verificado `refcontrol-pose-klein-4b.safetensors` e strength `0.8`, com a mesma base, anchor, guia e seeds. Os três outputs têm binding fresco, identidade/arma aprovada, mas mediana de pose `0.174489` e PCK `0.000`; nenhum passou o gate absoluto.

## IDENTITY / WEAPON QA

Identidade e arma foram medidas separadamente da pose. As nove saídas foram preservadas em [docs/evidence/v054-lanes](docs/evidence/v054-lanes) e as 9/9 passaram o gate de identidade/arma. Isso não compensa o fracasso da pose: pixels de espada não são joints.

## CAUSAL PROVIDER DECISION

`LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED`. O MediaPipe mede corretamente o material histórico e os outputs, os grafos C/R são live-valid e a execução foi fresca, porém nenhuma lane pose-first passou os gates absolutos. Portanto o provider local não demonstrou controle causal de pose. A decisão machine-readable está em [v054-provider-qualification.json](docs/evidence/v054-provider-qualification.json). Nenhum provider alternativo foi introduzido.

## EXECUTION EVIDENCE

[execution-evidence-v0.5.4.json](docs/evidence/execution-evidence-v0.5.4.json) registra 9 outputs, as três lanes, as três seeds, `all_fresh_binding=true`, `no_previous_frame_chaining=true` e `no_walk_executed=true`. O walk não foi executado nesta fase. O runtime de health/GPU não foi usado como substituto da prova de prompt/history/output.

## STATE CONSISTENCY

[current-state.json](docs/evidence/current-state.json) é `v0.5.4 / POSE_LANE_RECHECK`, com gate e stop reason iguais a `LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED`. `generation_provider_change_authorized=false`, `walk_authorized=false` e `new_generation_jobs=9`. O R4 canônico não mudou.

## TESTS

A suíte cobre separação histórica, licença/hash/exclusão, preprocessamento global, mapping MediaPipe, sanity, thresholds limitados, seeds/lanes exatas, fresh binding, gate por juntas, identidade/arma separadas, decisão causal e bloqueio de walk/provider.

## VALIDATION

A validação final deve executar `compileall`, a suíte unitária, schemas, consistência de estado, evidências históricas e snapshot tracked/no-Git. O review não declara sucesso de GitHub Actions, deployment ou aprovação humana sem evidência correspondente.

## TRACKED SNAPSHOT / GITHUB

Repositório: [csn1985-ship-it/ugas](https://github.com/csn1985-ship-it/ugas). O branch operacional é `main`; a publicação local e o resultado dos testes são verificáveis no commit final reportado pelo agente. Review do GitHub, CI, deployment e aprovação externa não são inferidos.

## SECURITY

Nenhum `.safetensors`, `.task`, segredo ou credencial é incluído no Git ou no ZIP. Os documentos registram apenas hashes, paths de boundary e URLs públicas. O bundle Pose Landmarker e os pesos de geração permanecem locais, fora da área publicada.

## VISUAL REVIEW STATUS

Os contact sheets [v054-lanes-contact-sheet.png](docs/evidence/v054-lanes-contact-sheet.png) e [v054-pose-overlays-contact-sheet.png](docs/evidence/v054-pose-overlays-contact-sheet.png) mostram os 9 outputs e os joints detectados. São evidência técnica para revisão; não constituem aprovação visual automática.

## BLOCKERS / GAPS

O provider nativo ComfyUI/RefControl não atingiu pose controlada por joints em C ou R. Walk/front/8, âncoras direcionais v3, nova strength, novo provider, DWPose, ControlNet, custom nodes e estimator alternativo estão bloqueados neste slice.

## DECISIONS

1. Resolver a licença somente para QA local e manter o bundle fora do Git/ZIP.
2. Aceitar MediaPipe como estimador independente após detectabilidade e sanity.
3. Congelar thresholds antes dos jobs.
4. Executar somente A/C/R nas seeds exatas, sem encadeamento.
5. Emitir `LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED` após a falha absoluta de C/R.
6. Não executar walk nem promover âncoras.

## NEXT STEP

O próximo passo permitido é documentar e revisar uma estratégia de correção do controle de pose. Nenhuma execução adicional de provider é autorizada por este review.

## DEFINITION OF DONE

License/hash evidence resolvida para QA local; MediaPipe qualificado em 10 assets; thresholds congelados; 9 jobs A/C/R frescos executados; outputs, overlays, métricas e decisão causal materializados; estado fail-closed atualizado; walk e provider alternativo bloqueados; testes, validação e snapshots reproduzíveis; sem afirmar aprovação externa.

## REVIEW ZIP

O ZIP final será criado somente depois do commit, push, verificação pública de `main` e validação final. A criação do ZIP será a última escrita desta execução; depois dela somente leituras e auditoria do arquivo.
