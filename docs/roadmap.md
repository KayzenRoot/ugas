# UGAS roadmap

## v0.5.2 - current corrective slice

O slice atual terminou em `LOCAL_POSE_CONTROL_PROVIDER_GAP` após avaliar OpenPose COCO-18, A/B/C nativo e RefControl nativo. Âncoras/walk v3 seguem bloqueados.

## v0.5.1 - historical corrective slice

Correção de reprodutibilidade do walk, mannequin preenchido determinístico, métricas de pose/identidade, seleção por qualidade e QA temporal v2. O corretivo para em `MULTI_REFERENCE_POSE_CONTROL_GAP` se os três pares A/B não demonstrarem ganho causal mínimo de 0.15.

## v0.5.0 - historical slice

Qualificação experimental de multi-reference nativo FLUX.2 Klein, guias determinísticos, quatro âncoras coerentes e walk/front/8. O resultado técnico está `READY_FOR_REVIEW / ANIMATION_PILOT_VISUAL_REVIEW_REQUIRED`; aprovação visual humana e eventual aprovação de produção permanecem pendentes.

## Next gate

Somente após a revisão visual do usuário e nova autorização explícita podem ser definidos outros ciclos, mais vistas ou integração de runtime. Nenhuma capacidade não testada é inferida a partir deste piloto.

## Explicitly not in v0.5.2

Animação genérica, idle/run/attack/hit/death, todas as direções, 3D/Blender, áudio, engine integration, DWPose/OpenPose/ControlNet, custom nodes, cloud inference, paid providers e produção automática.
