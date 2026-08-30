# UGAS Review - Prompt 04G v0.5.5

## STATUS

`REVIEW_ARCHIVE_VERIFIED`. Esta release corrige a integridade do snapshot distribuído e prova que o ZIP extraído é uma representação autoconsistente e executável do commit publicado. O resultado técnico de pose v0.5.4 permanece separado e é `LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED`.

## VERSION

`0.5.5`; review tooling local `1.8.0`.

## PHASE

`PROMPT-04G / REVIEW_SNAPSHOT_INTEGRITY`.

## OBJECTIVE

Corrigir o falso positivo do matcher de filenames, preservar os paths canônicos dos 9 outputs A/C/R, adicionar um verificador tracked independente de Git e executar a suíte completa dentro de uma extração limpa do novo review ZIP.

## V0.5.4 AUDIT FINDING

O snapshot anterior excluiu os 9 PNGs canônicos porque o substring `seed` foi classificado como sensível. As cópias em `__REVIEW__/visual-evidence/` não substituíam os paths canônicos usados por testes e manifests. A falha era de packaging/distribution integrity, não de geração A/C/R.

## ROOT CAUSE

`create_review_zip.py` usava matching amplo para `seed` e `mnemonic`. Isso confundia metadado público de reprodutibilidade (`a-seed-54701.png`) com segredo.

## SENSITIVE PATH MATCHER FIX

As regras agora são ancoradas em componentes de caminho, nomes exatos ou padrões completos documentados. `seed`, `tokenizer` e `monkey` isolados não são secretos. Permanecem bloqueados `.env`, credenciais, auth/API/access tokens, private keys, pesos, extensões criptográficas e nomes explícitos de wallet/recovery (`seed_phrase`, `recovery_seed`, `mnemonic`, `wallet_backup`). O self-test pode ser executado com `python create_review_zip.py --self-test` sem criar ZIP.

## CANONICAL SNAPSHOT CONTRACT

O packager exige que todos os `source_path` do manifest ativo e os nove paths em `docs/evidence/v054-lanes/` sejam incluídos. Uma exclusão de fonte referenciada somente pode ser aceita como security exclusion específica; os nove outputs canônicos não podem ser classificados como segredo. O ZIP mantém cópias convenientes sob `__REVIEW__/visual-evidence/`, mas elas não substituem os paths canônicos.

## REVIEW ARCHIVE VERIFIER

`scripts/validation/verify_review_archive.py` é tracked e não depende de `.git`. Ele valida CRC, traversal, paths absolutos, pesos, segredos, manifest, HEAD, manifest visual, 9 PNGs, hashes e cópias. Em seguida extrai em diretório temporário externo e executa `compileall`, `unittest` e `scripts/validation/run_validation.py`, capturando exit codes, contagem exata e summary.

## V054 LANE OUTPUT PRESERVATION

Os 9 outputs A/C/R e o `v054-pose-error-table.json` permanecem byte/hash-exatos. As lanes, seeds `54701/54702/54703`, execution evidence, identidade/arma e conclusão machine-readable v0.5.4 não foram reexecutados nem reinterpretados.

## HASH VERIFICATION

Cada PNG é aberto com Pillow e seu SHA-256 é comparado ao `output_sha256` da tabela v0.5.4. Cada cópia visual presente no ZIP é comparada byte a byte ao source canônico. O `head_commit` do manifest é comparado a `__REVIEW__/git-head.txt`.

## SECURITY EXCLUSIONS

Segredos, credenciais, chaves privadas, pesos e o bundle local Pose Landmarker continuam fora do Git e do ZIP. `excluded-files.txt` registra a regra específica que causou cada exclusão. Nenhuma regra genérica de `seed` pode excluir um output canônico.

## POSE DECISION PRESERVED

O estado de pose permanece `LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED`. Nenhum threshold, PCK, NME, limb-angle, orientação, causal gate ou decisão técnica do v0.5.4 foi alterado.

## NO NEW GENERATION EVIDENCE

Não houve ComfyUI, MediaPipe, provider, strength, seed de geração, estimator, walk, anchors v3, spritesheet ou GIF novo nesta release. `new_generation_started=false` e `new_generation_jobs=0` no estado v0.5.5.

## TESTS

Os 129 testes do snapshot v0.5.4 foram preservados e os testes de packaging cobrem matcher, falsos positivos, secrets, pesos, canonical outputs, ausência de um PNG, hash divergente de cópia, independência de Git e binding do HEAD.

## VALIDATION

No checkout, `python -m compileall -q src scripts tests`, `python -m unittest discover -s tests -q` e `python scripts/validation/run_validation.py` passam. A validação final registrada pelo verificador também passa dentro do ZIP extraído, sem `.git`.

## EXTRACTED ZIP SELF-TEST

O resultado final do verificador é `REVIEW_ARCHIVE_VERIFIED`, com ZIP sem corrupção, 9 outputs canônicos presentes, hashes conferidos, cópias iguais, testes unitários e validação de repositório executados na extração limpa.

## TRACKED SNAPSHOT / GITHUB

O branch publicado é `main` no repositório [csn1985-ship-it/ugas](https://github.com/csn1985-ship-it/ugas). O manifest do review registra o mesmo `head_commit` de `origin/main` usado para criar o ZIP. CI, deployment e aprovação externa não são inferidos.

## STATE CONSISTENCY

`docs/evidence/current-state.json` separa `pose_lane_status=LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED` de `review_snapshot_status=REVIEW_ARCHIVE_VERIFIED`. O gate de release é `REVIEW_SNAPSHOT_INTEGRITY_FIXED`; provider change e walk permanecem não autorizados.

## BLOCKERS / GAPS

Não há blocker de distribuição no review final. O gap técnico de controle causal de pose v0.5.4 permanece aberto e não é resolvido por esta correção de packaging. A aprovação visual humana e a aprovação de produção continuam externas.

## DECISIONS

1. Tratar seeds de geração como metadado público quando o nome não contém um padrão explícito de wallet/recovery.
2. Preservar integralmente os 9 outputs, hashes e evidências v0.5.4.
3. Exigir verificação e execução limpa do ZIP antes de considerar o snapshot verificável.
4. Manter a decisão de pose e o estado de release em campos distintos.
5. Não iniciar nenhuma nova geração nesta release.

## NEXT STEP

Após `REVIEW_ARCHIVE_VERIFIED`, o próximo passo autorizado é `design_next_pose_control_provider_strategy`. Nenhuma execução de provider é autorizada por este review.

## DEFINITION OF DONE

Concluído quando o novo ZIP contém os 9 paths canônicos, não os lista em `excluded-files.txt`, bloqueia segredos/pesos reais, valida hashes/cópias/HEAD, e a extração limpa passa compileall, pelo menos 129 testes e a validação completa sem `.git`.

## REVIEW ZIP

O artefato final é gerado em `review/UGAS-REVIEW-v0.5.5-<timestamp>.zip`. O ZIP inclui `__REVIEW__/manifest.json`, `excluded-files.txt`, metadata Git, manifest visual e as evidências necessárias; seu SHA-256 deve ser registrado no handoff final.
