# UGAS Review v0.5.0

## STATUS

`READY_FOR_REVIEW / ANIMATION_PILOT_VISUAL_REVIEW_REQUIRED`. Os gates técnicos passaram; a revisão visual humana e qualquer aprovação de produção permanecem pendentes.

## VERSION

`0.5.0` / PROMPT-04-UGAS-MULTIVIEW-POSE-WALK-PILOT-v0.5.0.

## PHASE

Multi-view identity anchor, deterministic pose guides, directional anchor set and closed walk/front/8 pilot.

## OBJECTIVE

Qualificar multi-reference nativo FLUX.2 Klein no RTX 5050, criar vistas coerentes e testar oito frames front/down condicionados sempre pelo mesmo R4 e por um guia source-controlled.

## SCOPE

Incluídos: identidade, vistas front/left/right/back, walk/front/8, transparência, normalização, pivot/ground, spritesheet, GIF preview, QA e evidência. Excluídos: animação genérica, outros ciclos, todas as direções, 3D, áudio, engine integration, DWPose/OpenPose/ControlNet/custom nodes, cloud e pagos.

## BASELINE / V0.4.3 ANCHOR

Baseline `7d9954d1fba21ef2ff32e5758e7ce12731cdab04`. Anchor: asset `asset-2fec6fed1d714d0cb58ad75b56d7ba71`, R4 `revision-3a425d184b1a49be9f6d6c8d52d04b96`, SHA-256 `7c2d0ea531de5996bd747971c9daedef60a5ca9f2e5b57b2a52f80c05f8f5798`. A aprovação externa fornecida foi registrada como `external-pipeline-anchor` para este incremento; não é aprovação de produção.

## MULTI-REFERENCE QUALIFICATION

`MULTI_REFERENCE_QUALIFIED` após quatro jobs reais A/B (seeds 50501/50502). A usa R4; B usa R4 + guia left. O workflow Base usa 20 passos, CFG 5, Euler, quatro `ReferenceLatent` nativos e nenhum custom node. B manteve margens e identidade heurística com pose forte; a comparação requer revisão visual humana porque a diferença média não foi material.

## POSE GUIDE SYSTEM

Os JSONs em `pose-guides/views/` e `pose-guides/walk-front-8/` têm 512x512, keypoints explícitos, baseline 478, centerline 256, pivot/ground policy, são determinísticos e declaram `generated_ai_content=false`. O render Pillow e o contact sheet são reproduzíveis.

## DIRECTIONAL ANCHOR PILOT

`DIRECTIONAL_ANCHORS_VISUAL_REVIEW_REQUIRED`. Front é cópia byte-identical do R4. Left/right/back tiveram dois candidatos cada, com seed/job/path únicos; todos os selecionados passaram BiRefNet, alpha, margem, ocupação e normalização. Candidatos e falhas permanecem em `tmp/` fora do Git.

## DIRECTIONAL CONSISTENCY QA

Canvas 512, alpha, safe margin, baseline, pivot, escala e ocupação passaram. Paleta, armor, cloth, skin, head, weapon, proporções e fidelidade de cada vista precisam de inspeção visual humana; o contato direcional é evidência, não decisão automática.

## WALK-CYCLE PILOT

`WALK_CYCLE_VISUAL_REVIEW_REQUIRED`. O piloto é exatamente `walk/front/down/8`, com um guia por frame e R4 em `reference[0]`. Os oito frames passaram como conjunto; nenhum frame anterior foi usado como entrada.

## FRAME QA

Todos os frames selecionados são PNG RGBA 512x512, não vazios, sem contato de borda, com transparência, margem e hashes distintos. Foram permitidas no máximo duas tentativas por frame; o frame 07 selecionou a segunda tentativa, preservando a primeira evidência.

## NORMALIZATION / PIVOT / GROUND

Normalização aplica apenas translação, sem stretch: alpha bbox é registrado antes, pé mais baixo é colocado na baseline `y=478` e o pivot x fica em `256`. Cada frame registra translation, scale, bbox, guide hash e caminho original/normalizado.

## TEMPORAL QA

8 frames, hashes únicos, diferenças adjacentes `0.038470–0.053988`, altura relativa `0.077391`, pivot jitter `0.5 px`, sem outlier, loop compatível e `no_previous_frame_chaining=true`. O contato de diferenças está em `docs/evidence/walk-frame-diff-contact.png`.

## SPRITESHEET / METADATA / PREVIEW

`walk-front-8-spritesheet.png` é uma linha de 8 células 512x512; `walk-front-8.json` e `walk-front-8-animation-spec.json` registram animation/view/frames/fps/loop/dimensions/pivot/frame files/frame hashes. O GIF é apenas preview; o contact sheet é a conferência visual.

## EXECUTION EVIDENCE

`docs/evidence/multiref-qualification.json`, `directional-anchor-set.json`, `walk-front-8-animation-qa.json` e os jobs em `tmp/` registram client job ID, Comfy prompt ID, history exact, outputs, hashes, source anchor hash, guide hash, workflow/model hashes, seed, runtime, cache/history, stage e fresh binding. O `execution-evidence.json` aponta para os três conjuntos.

## CAPABILITY STATES

`multi-reference-edit`: declared → ready → verified/qualified pelo A/B real, com revisão visual requerida. `directional-anchor-set`: declared → ready → visual-review-required. `walk-front-8-pilot`: declared → ready → visual-review-required. Capacidades genéricas de animação e ciclos não autorizados permanecem unavailable/out-of-scope.

## TESTS

79 regressões históricas preservadas mais a cobertura v0.5 de identidade, guias, topology/order, fail-closed, no-chain, limites de candidatos, normalização, temporal QA, pack e manifest hash-bound.

## VALIDATION

Executar `python -m compileall -q src scripts tests`, `python -m unittest discover -s tests -q` e `python scripts/validation/run_validation.py`. O snapshot Git e o snapshot no-Git também são gates.

## TRACKED SNAPSHOT / GITHUB

Baseline de trabalho foi `main` em `7d9954d1fba21ef2ff32e5758e7ce12731cdab04`; publicação do commit v0.5.0 e verificação de `origin/main` são obrigatórias antes do ZIP final.

## SECURITY / LICENSES

Pesos ficam fora do Git; hashes e licenças são registrados nos manifests. Não há secrets, cloud, paid provider ou custom node no workflow. O template upstream e FLUX.2/BiRefNet permanecem referenciados conforme os registros existentes.

## VISUAL REVIEW STATUS

Pendente revisão humana do A/B, quatro âncoras, oito frames, transparência visual, silhueta, espada, rosto, tecido, palette drift, leitura em gameplay e loop. Nenhuma aprovação visual automática foi inferida.

## PENDING

Revisão visual humana, eventual decisão de aprovação de pipeline e eventual aprovação de produção, que são estados distintos.

## BLOCKERS

Nenhum blocker técnico do slice. O gate externo é a revisão visual humana; portanto o projeto não é `PRODUCTION_READY`.

## DECISIONS

Preservar R4 sem regeneração; usar somente `ReferenceLatent`; guias sem IA; nunca encadear frames; aceitar somente oito frames como conjunto; manter candidatos/falhas fora do estado selecionado.

## NEXT STEP

Revisar visualmente os contatos e, se aprovado, registrar a decisão em fluxo próprio. Não iniciar novo ciclo nem integração sem prompt/autorização posterior.

## DEFINITION OF DONE

Código, schemas, CLI, guias, workflow, A/B, âncoras, walk, QA, testes, documentação, snapshot Git, commit/push verificado e review ZIP seguro com hashes e evidência visual. Cumprido tecnicamente; aprovação visual/produção ainda não.

## REVIEW ZIP

O pacote final deve ser `review/UGAS-review-v0.5.0-*.zip`, criado por `create_review_zip.py` somente após push verificado. Ele inclui `__REVIEW__/visual-evidence/` com imagens e JSONs v0.5, exclui Git/cache/pesos/secrets e é a última ação de filesystem.
