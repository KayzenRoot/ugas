# UGAS checkpoint - v0.5.5

**STATUS:** `REVIEW_ARCHIVE_VERIFIED`. Esta release corrigiu a integridade do snapshot do review sem executar GPU, ComfyUI ou MediaPipe. A decisão técnica de pose do v0.5.4 permanece separada como `LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED`.
**VERSION:** `0.5.5`
**PHASE:** `PROMPT-04G / REVIEW_SNAPSHOT_INTEGRITY`

## Current state

O estado machine-authoritative está em [docs/evidence/current-state.json](docs/evidence/current-state.json). O release gate é `REVIEW_SNAPSHOT_INTEGRITY_FIXED` e o snapshot verificado é `REVIEW_ARCHIVE_VERIFIED`. A decisão de pose continua `LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED`, registrada na evidência [v054-provider-qualification.json](docs/evidence/v054-provider-qualification.json).

O v0.5.4 é histórico e seus 9 outputs A/C/R, hashes, thresholds e execution evidence permanecem byte/hash-exatos. A licença `POSE_QA_LOCAL_USE_LICENSE_RESOLVED` continua válida apenas para QA local; o bundle `.task` não é redistribuído.

## Review snapshot integrity

O matcher local do packager usa nomes exatos, componentes de caminho e padrões ancorados. `seed`, `tokenizer` e `monkey` em nomes de assets não são segredos genéricos. Segredos, credenciais, tokens explícitos, private keys, pesos e arquivos de modelo permanecem excluídos com motivos específicos.

O verificador tracked [scripts/validation/verify_review_archive.py](scripts/validation/verify_review_archive.py) não depende de `.git`: verifica o ZIP, preserva os 9 paths canônicos em `docs/evidence/v054-lanes/`, confere hashes e cópias, e executa compileall, unittest e repository validation dentro de uma extração temporária externa.

## Boundary

`generation_provider_change_authorized=false`, `walk_authorized=false`, `new_generation_started=false` e `new_generation_jobs=0`. Nenhum provider alternativo, custom node, strength, estimator, walk, âncora v3, spritesheet ou GIF foi executado nesta release.

O review ativo é [REVIEW-v0.5.5.md](REVIEW-v0.5.5.md). A aprovação visual humana, GitHub Actions, deployment e aprovação de produção não são inferidos da validação local ou do verificador.

Animação genérica permanece fora deste slice e não autoriza promoção de walk.
