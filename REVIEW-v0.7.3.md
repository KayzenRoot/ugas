# UGAS review v0.7.3 — cutout structural coverage correction

## STATUS

`CUTOUT_RIG_KEY_POSES_TECHNICALLY_QUALIFIED`. Esta é uma qualificação técnica local. A revisão visual externa continua `REQUIRED`; aprovação externa e aprovação de produção não são reivindicadas.

## VERSION

UGAS v0.7.3. Previous release: v0.7.2. Baseline commit: `4fd860319d01d04c7da2562431c1d522c1fd2890`.

## PHASE

`DETERMINISTIC_CUTOUT_RIG_POSE_PROVIDER`. A lane reutiliza somente os inputs R4/v0.7.1 e os targets K1–K4 hash-bound do v0.7.2. Não há geração, walk ou mudança de provider de produção.

## OBJECTIVE

Corrigir os buracos estruturais reais de cintura/cinto/pelve observados na auditoria visual externa do v0.7.2. O trabalho adiciona um núcleo estrutural determinístico derivado da fonte, integridade de camada baseada em área esperada, regiões explícitas de oclusão e diagnósticos de owner sem SAM2, ComfyUI, edição manual de máscaras ou geração de pixels.

## V0.7.2 EXTERNAL AUDIT RESULT

O resultado técnico v0.7.2 e seu ZIP permanecem imutáveis. A auditoria visual externa rejeitou os key poses por buracos transparentes reais em cintura/cinto/pelve, embora os gates técnicos históricos tivessem passado. O walk de oito frames não foi executado e continua bloqueado.

O histórico de pose preserva `LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED`, o snapshot histórico preserva `REVIEW_ARCHIVE_VERIFIED`, o smoke v0.6.2 permanece `SDXL_OPENPOSE_CONTROL_GAP_CONFIRMED_AT_MODEL_CARD_SETTINGS`, `sdxl-openpose-p-qualification.json` e `review-visuals-v0.6.1.json` continuam sendo referências históricas, e `provider_smoke_status` permanece distinto do histórico de smoke.

## VISUAL REJECTION EVIDENCE

As imagens históricas v0.7.2, incluindo `cutout-k4-passing-right-v072.png`, permanecem disponíveis no review histórico. A revisão v0.7.3 inclui checkerboard, zoom de cintura e overlay magenta dos buracos estruturais corrigidos; os PNGs canônicos não contêm labels incorporados.

## RETENTION TAUTOLOGY FINDING

O v0.7.2 comparava a retenção com uma área esperada derivada do próprio output transformado. Isso não é prova independente. O v0.7.3 calcula `source_active_pixels * uniform_scale^2` a partir da máscara pré-transformação, mede a área rasterizada, registra erro, clipping previsto pelo forward affine, perda e ganho.

## STRUCTURAL CORE

`docs/evidence/cutout-structural-core-v073.json` e `cutout-structural-core-mask-v073.png` registram o núcleo central torso/abdomen/cinto/ponte pélvica. Ele é derivado apenas da alpha R4, máscara de torso, máscaras de partes e skeleton; segue a transformação do torso/root, não cobre head/sword e mapeia 100% para pixels da fonte. O núcleo é composto antes das camadas articuladas, com exclusão final explícita de head e sword.

## STRUCTURAL COVERAGE QA

`cutout-structural-coverage-v073.json` mede envelope estrutural esperado transformado independentemente, pixels cobertos, buracos, fração, maior componente e bbox, além de cobertura de torso/cinto/ponte pélvica. Gates: hole fraction `<=0.0025`, maior componente `<=12`, nenhum componente com largura e altura simultaneamente `>=4`, e cobertura de torso/belt/pelvis `>=0.995`. K1–K4 passam com zero buracos estruturais.

## SOURCE OWNER DISPLACEMENT

`cutout-structural-hole-owner-diagnostics-v073.json` registra source coordinate, `owner_at_source`, destino forward de cada owner, duplicação pelo core e motivo. O arquivo passa sem buracos residuais; o diagnóstico existe para impedir que um deslocamento de parte seja confundido com fonte ausente.

## TRUE LAYER INTEGRITY

`cutout-layer-integrity-v073.json` e `cutout-layer-integrity-calibration-v073.json` registram a calibração sintética: fixture sem crop passa e fixture deliberadamente cropped falha. A qualificação real passa raster error `<=0.03`, clipping previsto zero, perda `<=0.02` e ganho `<=0.02` para todas as partes.

## AUTHORIZED OCCLUSION REGIONS

`cutout-authorized-occlusion-regions-v073.json` usa corredores geométricos explícitos por fase: shoulder attachment, head/shoulder, hip socket, elbow, knee, grip/wrist, hand/hip e a pequena lane blade-over-trail-thigh. As regiões são calculadas de targets e skeleton; não são obtidas da interseção observada no output.

## PAIRWISE OVERLAP V3

`cutout-pairwise-overlap-matrix-v073.json` classifica `JOINT_OVERLAP` somente dentro do corredor estrito da junta; `EXPECTED_OCCLUSION` somente dentro da região geométrica autorizada e com ordem front/back correta; todo o restante é `UNEXPECTED_OVERLAP`. Adjacência sozinha não autoriza overlap. Pares sword/head, sword/torso e outros críticos continuam críticos e exigem zero pixels. K1–K4 passam sem colisão crítica, sem mismatch de z-order e sem overlap significativo fora das regiões.

## TOPOLOGICAL SEAM

`cutout-seam-topology-qa-v073.json` retém o QA topológico v0.7.2 com o mesmo plano e thresholds. As dez conexões permanecem hash-bound; costura, conectividade e tolerância de alpha passam em K1–K4.

## RETENTION / OCCLUSION V3

`cutout-retention-occlusion-v073.json` só mede retenção após a integridade independente. Front limbs exigem `>=0.85`, back limbs `>=0.55` com explicação `>=0.95`, head `>=0.97` e sword `>=0.95`; perda sem occluder, clipping e occluder inesperado falham. Todas as partes e fases passam.

## Q0 REGRESSION

`cutout-q0-regression-v073.png` e sua QA preservam a identidade R4: alpha IoU `>=0.995`, RGB MAE `<=1.5`, zero pixels gerados/residuais e nenhuma alteração visível causada pela duplicação do core. O gate passa com alpha IoU `1.0`, RGB MAE `1.147443` e zero buracos estruturais.

## K1 CONTACT-LEFT

`cutout-k1-contact-left-v073.png` passa cobertura estrutural, integridade, pairwise, costura, retenção e MediaPipe; o target joint hash é o mesmo do v0.7.2.

## K2 PASSING-LEFT

`cutout-k2-passing-left-v073.png` passa os mesmos gates, incluindo o crossing sword/trail-thigh explicitamente delimitado.

## K3 CONTACT-RIGHT

`cutout-k3-contact-right-v073.png` passa os mesmos gates com o plano espelhado de lower-body e braço counter-swing.

## K4 PASSING-RIGHT

`cutout-k4-passing-right-v073.png` passa os mesmos gates e não reproduz os buracos transparentes estruturais rejeitados na auditoria v0.7.2.

## CHECKERBOARD / WAIST ZOOM

`cutout-key-poses-checkerboard-v073.png`, `cutout-key-poses-waist-zoom-v073.png` e `cutout-structural-hole-overlay-v073.png` são a evidência visual canônica. A inspeção checkerboard-first inclui escala geral, cintura ampliada e overlay de hole sem labels dentro dos PNGs de saída.

## MEDIAPIPE POSE QA

MediaPipe é somente estimator de QA. Os thresholds v0.5.4 permanecem inalterados. Os quatro targets são os mesmos do v0.7.2 por hash; K1–K4 passam PCK/NME e lower-body gates. Nenhum modelo de geração é inferido desse resultado.

## FINAL PROVIDER DECISION

`CUTOUT_RIG_KEY_POSES_TECHNICALLY_QUALIFIED`. O provider é tecnicamente qualificado somente para os quatro key poses frontais deste slice. `walk_authorized=false` e `generation_provider_change_authorized=false` continuam obrigatórios até revisão visual externa.

## NO SAM2 / NO COMFYUI / NO WALK

SAM2 runs: `0`; ComfyUI generation jobs: `0`; eight-frame walk: `NOT_RUN`; spritesheet: `NOT_RUN`; GIF: `NOT_RUN`. Nenhum source/checkpoint SAM2 é incluído no Git ou no review ZIP.

## TESTS

O conjunto histórico v0.7.2 permanece preservado. Os novos testes cobrem derivação determinística do core, exclusão de head/sword, área esperada independente, fixture cropped que falha, fixture de hole estrutural v0.7.2 K4 que falha, seam AA de 1 px, cobertura torso/belt/pelvis, owner displacement, regiões geométricas, pairwise fora da região, ordem z, colisão crítica e limites de execução.

## VALIDATION

Foram executados o qualifier v0.7.3 com `--json`, `python -m compileall -q src scripts tests`, `python -m unittest discover -s tests`, `python scripts/validation/run_validation.py` e o verificador do ZIP final. O resultado final e as contagens ficam nos artefatos machine-readable e no handoff.

## REVIEW ARCHIVE SELF-TEST

O ZIP final deve passar CRC, traversal, hashes, secrets scan e validação após extração limpa sem `.git`. O empacotamento ocorre somente depois do snapshot publicado e limpo; não há escrita posterior ao ZIP final bem-sucedido.

## TRACKED SNAPSHOT / GITHUB

O snapshot publicado é `main` no commit v0.7.3 e `origin/main` deve ser idêntico a `HEAD` antes do pacote. Runtime models, caches, temporários, secrets e ZIPs históricos não entram no tracked snapshot nem no pacote final.

## SECURITY / LICENSES

Nenhum token, credential, checkpoint, `.venv` ou cache é incluído. A licença permanece MIT. MediaPipe e a proveniência histórica SAM2 são documentados sem distribuição dos pesos.

## VISUAL REVIEW STATUS

O gate técnico local passa. Revisão visual humana externa: `REQUIRED`. Aprovação de produção: `not-granted`. Aprovação externa: `not-claimed`.

## BLOCKERS / GAPS

Não há gap técnico interno nos gates deste slice. O blocker deliberado é a revisão visual externa; sem ela, walk de oito frames e promoção para routing de produção permanecem bloqueados.

## DECISIONS

Manter todos os artefatos v0.7.2 imutáveis; reutilizar R4/v0.7.1; derivar o core somente de fonte/máscaras/skeleton; medir integridade a partir de área independente; exigir regiões geométricas e ordem z; não executar SAM2, ComfyUI, walk, spritesheet ou GIF.

## NEXT STEP

Após registrar revisão visual externa, o único próximo prompt permitido é `external_review_then_run_8_frame_walk_prompt`.

## DEFINITION OF DONE

Este slice está concluído quando o baseline histórico e seus snapshots estão preservados, Q0/K1–K4 passam todos os gates v0.7.3, as fixtures negativas falham como esperado, os 224 testes históricos mais os novos passam, o snapshot `main` é publicado limpo e o ZIP final se auto-valida. Isso não equivale a aprovação visual externa.

## REVIEW ZIP

Artefato final: `review/UGAS-REVIEW-v0.7.3-final-<timestamp>.zip`, com SHA-256 registrado no handoff.
