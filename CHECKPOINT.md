# UGAS checkpoint - v0.5.4

**STATUS:** `LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED`. O MediaPipe Pose Landmarker foi qualificado como estimador QA independente; as lanes A/C/R executaram 9 saídas frescas com as seeds autorizadas. A identidade/arma passou, mas nenhuma saída C/R passou os gates absolutos de pose por juntas. O processo para fail-closed antes de walk, âncoras v3 ou troca de provider.
**VERSION:** `0.5.4`
**PHASE:** `PROMPT-04F / POSE_LANE_RECHECK`

## Current state

O estado machine-authoritative é [docs/evidence/current-state.json](docs/evidence/current-state.json). O R4 continua imutável: revision `revision-3a425d184b1a49be9f6d6c8d52d04b96`, SHA-256 `7c2d0ea531de5996bd747971c9daedef60a5ca9f2e5b57b2a52f80c05f8f5798`.

O `REVIEW-v0.5.3.md` é histórico. Seu bloqueio de licença foi resolvido somente para uso local de QA: `POSE_QA_LOCAL_USE_LICENSE_RESOLVED`. O bundle não é redistribuído. A rechecagem atual confirmou o bloqueio do provider, sem reclassificar o histórico.

## Estimator and license gate

Uma política global única foi selecionada: `transparent_neutral_gray`. R4, referência editada e os 8 frames históricos são mensuráveis; mediana de juntas mensuráveis: 13; cobertura central: 100%; inversão esquerda/direita: 0. Overlays e sanity checks foram materializados.

As fontes oficiais registradas são a documentação do [Pose Landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker) e o [model card BlazePose GHUM 3D](https://storage.googleapis.com/mediapipe-assets/Model%20Card%20BlazePose%20GHUM%203D.pdf). O model card resolve Apache-2.0 para o uso local de QA documentado; o bundle permanece fora do Git e do ZIP.

## Provider lane recheck

Thresholds foram congelados antes dos jobs em [pose-thresholds-v054.json](docs/evidence/pose-thresholds-v054.json). Foram executadas somente as lanes A, C e R, com `54701`, `54702`, `54703` em cada lane. A usou apenas identidade; C usou pose-first/identity-second nativo; R usou RefControl nativo a `0.8`.

As 9 execuções possuem prompt/history/output binding fresco. A lane A teve mediana de pose `0.241770` e identidade aprovada; C teve mediana de pose `0.000000`; R teve mediana `0.174489`. Nenhuma lane pose-first cumpriu os gates absolutos. O overlay confirma que o corpo gerado permanece em pose diferente do guia.

## Boundary

`generation_provider_change_authorized=false` e `walk_authorized=false`. Walk/front/8 não foi executado nesta fase; âncoras direcionais v3, spritesheet e GIF não foram promovidos. Não foi adicionado provider, custom node, estimator alternativo ou strength nova.

O review ativo é [REVIEW-v0.5.4.md](REVIEW-v0.5.4.md). A aprovação visual humana, GitHub Actions, deployment e aprovação de produção não são inferidos da validação local.

Animação genérica permanece fora deste slice e não autoriza promoção de walk.
