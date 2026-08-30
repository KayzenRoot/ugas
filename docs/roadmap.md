# UGAS roadmap

## v0.6.0 - SDXL ControlNet/IP-Adapter provider qualification

Audita e instala somente o custom node IP-Adapter Plus pinado localmente, registra os quatro artefatos externos, valida o runtime RTX 5050 e executa o smoke factorial P/I/PI. O estado atual é `SDXL_OPENPOSE_CONTROL_GAP`; benchmark, confirmação, walk e routing SDXL permanecem bloqueados.

## v0.5.5 - review snapshot integrity

Corrige o falso positivo de `seed` no empacotador local, adiciona regras de filename ancoradas e um verificador tracked que executa a suíte dentro da extração limpa. Os 9 outputs A/C/R e a decisão de pose v0.5.4 permanecem intactos. Nenhum job GPU foi executado.

## v0.5.4 - historical provider lane recheck

O estimador MediaPipe foi qualificado de modo independente com uma política global, license evidence oficial para QA local, detectabilidade histórica e sanity visual. O recheck autorizado executou A/C/R em 9 outputs frescos. O estado final é `LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED`: C/R não passaram pose por junta, embora identidade/arma tenham passado.

## v0.5.3 - historical corrective slice

Calibrou detected-joint pose error, corrigiu o gate causal impossível e parou em `POSE_QA_MODEL_LICENSE_GAP`. O documento e as evidências v0.5.3 não são reescritos.

## v0.5.2 and earlier - historical slices

Incluem a escalada OpenPose/RefControl, multi-reference nativo, âncoras e o piloto walk. Seus resultados são históricos e não autorizam promoção atual.

## Next gate

Somente uma nova decisão governada pode definir estratégia de correção do provider. Walk/front/8, âncoras v3, novos providers, DWPose, ControlNet, custom nodes e novos strengths estão fora do slice atual. O próximo passo autorizado após `REVIEW_ARCHIVE_VERIFIED` é `design_next_pose_control_provider_strategy`.
