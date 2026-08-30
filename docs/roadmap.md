# UGAS roadmap

## v0.7.0 - deterministic cutout-rig pose provider

Build the R4 front-facing deterministic cutout rig with SAM2.1 Hiera Small masks, hash-bound hierarchy, source-only pixel provenance and static Q0/Q1/Q2 QA. The implementation is complete locally, but the provider remains at `CUTOUT_RIG_VISUAL_OR_ESTIMATOR_GAP` because Q1/Q2 do not pass the unchanged pose thresholds.

## v0.6.2 - historical SDXL OpenPose model-card calibration

Preserve raw generation evidence before BiRefNet, render the model-card guides directly at 512/768/1024, and run raw pose QA for P0/P1/P2. The completed calibration stopped at `SDXL_OPENPOSE_CONTROL_GAP_CONFIRMED_AT_MODEL_CARD_SETTINGS`; confirmation, identity R4, benchmark, walk and anchors were not run.

## v0.6.0 - SDXL ControlNet/IP-Adapter provider qualification

O operating point xinsir foi testado somente na lane P: P0 512/20/Euler/0.9, P1 768/30/Euler Ancestral/1.0 e P2 1024/30/Euler Ancestral/1.0. O resultado atual é `SDXL_OPENPOSE_CONTROL_GAP_CONFIRMED_AT_MODEL_CARD_SETTINGS`; IP-Adapter, I/PI, benchmark, confirmation, walk e routing SDXL permanecem bloqueados.

## v0.5.5 - review snapshot integrity

Corrige o falso positivo de `seed` no empacotador local, adiciona regras de filename ancoradas e um verificador tracked que executa a suíte dentro da extração limpa. Os 9 outputs A/C/R e a decisão de pose v0.5.4 permanecem intactos. Nenhum job GPU foi executado.

## v0.5.4 - historical provider lane recheck

O estimador MediaPipe foi qualificado de modo independente com uma política global, license evidence oficial para QA local, detectabilidade histórica e sanity visual. O recheck autorizado executou A/C/R em 9 outputs frescos. O estado final é `LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED`: C/R não passaram pose por junta, embora identidade/arma tenham passado.

## v0.5.3 - historical corrective slice

Calibrou detected-joint pose error, corrigiu o gate causal impossível e parou em `POSE_QA_MODEL_LICENSE_GAP`. O documento e as evidências v0.5.3 não são reescritos.

## v0.5.2 and earlier - historical slices

Incluem a escalada OpenPose/RefControl, multi-reference nativo, âncoras e o piloto walk. Seus resultados são históricos e não autorizam promoção atual.

## Next gate

Somente uma nova decisão governada pode definir a correção do cutout-rig. Walk/front/8, âncoras v3, novos providers, DWPose, ControlNet, custom nodes e novos strengths estão fora do slice atual. O próximo passo autorizado é revisar/reparar Q1/Q2 e repetir a qualificação estática.
