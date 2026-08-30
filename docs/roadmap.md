# UGAS roadmap

## v0.5.3 - current corrective slice

O slice atual terminou em `POSE_QA_MODEL_LICENSE_GAP` após corrigir o gate impossível e passar a calibração de joints. A biblioteca MediaPipe foi importada, mas o bundle .task não tem termos de redistribuição/comercial determinados. Âncoras/walk v3 seguem bloqueados.

## v0.5.2 - historical corrective slice

Escalada histórica de OpenPose COCO-18, A/B/C nativo e RefControl. Seu provider gap foi reclassificado no v0.5.3 como `POSE_METRIC_GATE_DESIGN_GAP`.

## v0.5.1 - historical corrective slice

Correção de reprodutibilidade do walk, mannequin preenchido determinístico, métricas de pose/identidade, seleção por qualidade e QA temporal v2. O corretivo para em `MULTI_REFERENCE_POSE_CONTROL_GAP` se os três pares A/B não demonstrarem ganho causal mínimo de 0.15.

## v0.5.0 - historical slice

Qualificação experimental de multi-reference nativo FLUX.2 Klein, guias determinísticos, quatro âncoras coerentes e walk/front/8. O resultado técnico está `READY_FOR_REVIEW / ANIMATION_PILOT_VISUAL_REVIEW_REQUIRED`; aprovação visual humana e eventual aprovação de produção permanecem pendentes.

## Next gate

Somente após a revisão visual do usuário e nova autorização explícita podem ser definidos outros ciclos, mais vistas ou integração de runtime. Nenhuma capacidade não testada é inferida a partir deste piloto.

## Explicitly not in v0.5.3

Animação genérica, idle/run/attack/hit/death, todas as direções, 3D/Blender, áudio, engine integration, DWPose/OpenPose/ControlNet, custom nodes, cloud inference, paid providers e produção automática.
