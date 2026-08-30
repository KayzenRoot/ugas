# UGAS checkpoint - v0.5.2

**STATUS:** LOCAL_POSE_CONTROL_PROVIDER_GAP. A execução v0.5.2 parou fail-closed: nenhum lane de controle de pose foi qualificado e a revisão visual humana permanece separada.
**VERSION:** 0.5.2
**PHASE:** PROMPT-04D / POSE_CONTROL_ESCALATION

## Current state

O estado machine-authoritative é [`docs/evidence/current-state.json`](docs/evidence/current-state.json). O release v0.5.1 terminou corretamente em `MULTI_REFERENCE_POSE_CONTROL_GAP`: o ganho causal B-A foi 0.140250, abaixo do limiar fixo de 0.15. No v0.5.2, A/B/C também não qualificaram; o RefControl verificou hash/licença/loader, mas seu melhor ganho foi 0.097855. Portanto, os resultados positivos antigos ou parciais não autorizam uma lane atual de âncoras ou walk.

## Canonical anchor

Asset `asset-2fec6fed1d714d0cb58ad75b56d7ba71`, revisão R4 `revision-3a425d184b1a49be9f6d6c8d52d04b96`, SHA-256 `7c2d0ea531de5996bd747971c9daedef60a5ca9f2e5b57b2a52f80c05f8f5798`. A aprovação histórica é somente `external-pipeline-anchor`; `PRODUCTION_READY` continua falso até aprovação separada.

## Phase 0 correction

- A contradição do checkpoint anterior foi corrigida: não há afirmação ativa de que âncoras ou walk v2 tenham passado.
- `REVIEW-v0.5.1.md` permanece histórico e separado; não é reescrito para alterar o resultado auditado.
- O validador fatal compara este checkpoint, o review v0.5.2 e `current-state.json`; uma fixture com promoção contraditória deve falhar.
- `LOCAL_POSE_CONTROL_PROVIDER_GAP` é o stop final desta execução: o melhor RefControl foi força 0.8, média 0.992258, piso 0.991656 e ganho +0.097855 sobre A=0.894403; o limiar causal +0.15 não foi atingido.
- Nenhum novo download, workflow ou job ComfyUI é permitido antes do resultado verde dessa consistência.

## Current gate and boundaries

O guia determinístico OpenPose COCO-18 v3 e o benchmark nativo A/B/C foram executados. A baseline A ficou em 0.894403; B e C não tiveram 3/3 tecnicamente válidos por falhas de QA BiRefNet, portanto nenhuma lane qualificou. A próxima ação autorizada é verificar o RefControl, seu hash/licença e um loader LoRA nativo. O limiar de ganho de pose permanece `0.15` e não pode ser reduzido. DWPose, `controlnet_aux`, ControlNet, nós customizados, loaders LoRA customizados, cloud, serviços pagos e pesos fora do contrato estão proibidos.

Âncoras v3, walk/front/8 v3 e qualquer spritesheet permanecem bloqueados até existir uma lane de controle de pose qualificada e a QA correspondente.

## Evidence and publication

O review ativo é [`REVIEW-v0.5.2.md`](REVIEW-v0.5.2.md). O review ZIP v0.5.2 só será criado depois de commit, push, verificação pública do `main` e validação final; será a última escrita do processo. Reviews anteriores permanecem históricos.
Animação genérica permanece fora deste slice e não autoriza qualquer promoção de walk sem uma lane de pose qualificada e QA correspondente.
