# UGAS Review - Prompt 05-C v0.6.1

## STATUS

`SDXL_OPENPOSE_CONTROL_GAP` — smoke corretivo P/I/PI concluído: P e PI falharam no raw pose QA; P também falhou no pós-processamento. Esta release não autoriza benchmark, confirmation, walk, anchors ou novo provider.

O estado atual é `SDXL_OPENPOSE_CONTROL_GAP`; o manifesto histórico `docs/evidence/review-visuals-v0.6.0.json` e a evidência v0.6.0 permanecem preservados.

## VERSION

`0.6.1`; runtime, package, pyproject e documentação corrente devem permanecer alinhados.

## PHASE

`SDXL_CONTROL_POSE_PROVIDER_SMOKE_CORRECTION`.

## OBJECTIVE

Corrigir a perda de evidência depois de uma geração bem-sucedida, executar QA de pose no PNG bruto antes do BiRefNet e tornar os gates de identidade, proporção corporal, roupa preta, cabeça/rosto, armadura, espada e sujeito único realmente hard gates.

## V0.6.0 AUDIT FINDINGS

O commit-base público é `13c5c9ee1d70f08dcfafdd25cc65e30d271146a7`. O v0.6.0 registrou `SDXL_OPENPOSE_CONTROL_GAP`, mas a lane P perdeu o `prompt_id`, history e PNG bruto quando o BiRefNet falhou. O v0.6.0 permanece preservado como histórico.

## EXECUTION EVIDENCE PRESERVATION FIX

Após `_run_job()`, o record de geração e o PNG bruto são materializados imediatamente em `docs/evidence/sdxl-qualification/raw/`. Falhas posteriores são registradas em `postprocess.error` e não substituem a evidência de geração.

## RAW GENERATION EVIDENCE

Cada lane deve registrar `submitted`, `completed`, `prompt_id`, `history_record_key`, `history_key_matches_prompt_id`, `fresh_binding`, `raw_output_path` e `raw_output_sha256`. O agregado é `docs/evidence/execution-evidence-v0.6.1.json`.

## RAW POSE QA

P e PI usam o PNG bruto, com a política fixa e versionada `raw_rgb_neutral_gray`, antes do BiRefNet. Os thresholds são os congelados em `docs/evidence/pose-thresholds-v054.json`; o legado de silhueta não é gate. No smoke, P registrou PCK@.10=0.333/NME=0.551 e PI PCK@.10=0.000/NME=0.827; ambos falharam o gate absoluto.

## POSTPROCESS QA

BiRefNet valida transparência, preservação RGB, halo e asset alpha. I e PI passaram o pós-processamento; P registrou `POSTPROCESS_FAILED` com diagnóstico preservado. Falha de pós-processamento é `POSTPROCESS_FAILED`/`SDXL_POSTPROCESS_GAP` e não é confundida com falha de pose.

## IDENTITY HARD GATES

`identity_pass` exige score agregado, espada, `head_face`, `armor_palette`, `black_cloth`, `body_proportions` e `single_subject`. Um score alto não compensa qualquer hard failure; `failure_reasons` inclui `head_face_drift`, `armor_palette_drift`, `black_cloth_drift` e `body_proportion_drift`.

## SINGLE SUBJECT GATE

Connected components determinístico sobre alpha/foreground calcula `large_foreground_components` e `secondary_to_primary_area_ratio`. Um segundo componente body-sized falha com `multiple_subjects_detected`; componentes pequenos de arma/acessório são classificados separadamente. A fixture I histórica v0.6.0 com duas figuras falha com `large_foreground_components=2` e `multiple_subjects_detected`.

## P / I / PI CORRECTIVE SMOKE

Executar exatamente três jobs, um por lane, todos com a seed `61701`, mesmo Base SDXL, ControlNet, IP-Adapter, ViT-H, prompt, negative prompt, 512x512 e strengths congelados do v0.6.0. A ordem é P geração → raw pose → BiRefNet; I geração → BiRefNet → identity; PI geração → raw pose → BiRefNet → identity.

Resultado observado: os três jobs completaram com prompt/history/raw SHA-256 preservados; P e PI falharam no raw pose QA, P falhou também no BiRefNet, e I passou identidade/sujeito único.

## FINAL SMOKE CLASSIFICATION

Os únicos estados permitidos são `SDXL_POSTPROCESS_GAP`, `SDXL_OPENPOSE_CONTROL_GAP`, `SDXL_COMBINED_CONDITIONING_INTERFERENCE_GAP`, `SDXL_IDENTITY_ADAPTER_GAP`, `SDXL_COMBINED_IDENTITY_GAP` e `SDXL_SMOKE_GREEN_READY_FOR_BENCHMARK_PROMPT`. Nenhum autoriza benchmark automaticamente.

## MODEL / CUSTOM NODE BOUNDARY

Os quatro modelos permanecem hash-bound, sem novo download, fora do Git e fora do ZIP. O `ComfyUI_IPAdapter_plus` permanece pinado em `a0f451a5113cf9becb0847b92884cb10cbdec0ef`, local-only, GPL-3.0 e não vendorizado.

## EXECUTION EVIDENCE

O agregado deve distinguir `attempted_record_count` de `generation_completed_count` e exigir prompt/history/raw hash para todo job que chegou ao ComfyUI. `target_existed_before_submission=false` e `previous_frame_chaining=false` são obrigatórios.

## TESTS

Os 143 testes históricos foram preservados e a suíte v0.6.1 totalizou 151 testes, incluindo regressões para preservação pós-exceção, raw pose pré-BiRefNet, bindings, hard gates, multi-subject, espada pequena, fixture I histórica e bloqueio de benchmark/walk.

## VALIDATION

Compileall, unittest, state-consistency, `scripts/validation/run_validation.py` e o smoke `--smoke-only --seed 61701` passaram nos gates aplicáveis; o ZIP final ainda será auto-validado após o push. Falhas interrompem a promoção.

## REVIEW ARCHIVE SELF-TEST

O ZIP deve conter o manifesto v0.6.1, evidência histórica v0.6.0/v0.5.5, os três raw PNGs quando as gerações concluírem e executar compilação, testes e validação no snapshot extraído.

## TRACKED SNAPSHOT / GITHUB

`main` deve publicar o commit final, com `origin/main == HEAD` e working tree limpo. Pesos, bundle MediaPipe e source GPL não entram no Git nem no ZIP.

## SECURITY / LICENSES

Não baixar modelos, não alterar o pin, não copiar source GPL e preservar os records de licença/hash do v0.6.0. Aprovação externa e aprovação de produção continuam não concedidas.

## VISUAL REVIEW STATUS

O review deve incluir `sdxl-smoke-raw-p-i-pi-contact-sheet.png`, overlays P/PI com target versus joints, tabela de fases e contato pós-processado somente das lanes aprovadas no BiRefNet. PNGs brutos individuais são hash-bound.

## BLOCKERS / GAPS

Antes do smoke, o único gate é `SDXL_P_I_PI_SMOKE_REQUIRED`. Depois, o estado deve refletir a cadeia observada, inclusive um `POSTPROCESS_GAP` quando aplicável. Benchmark, confirmation, walk e anchors permanecem NOT_RUN.

## DECISIONS

Esta release corrige instrumentação e classificação; não tenta provar a capacidade do provider com uma lane P cujo raw job desaparece. O resultado é uma classificação confiável do smoke.

## NEXT STEP

Revisar a classificação `SDXL_OPENPOSE_CONTROL_GAP`, manter `walk_authorized=false` e `generation_provider_change_authorized=false`, publicar o commit final e criar o ZIP de review por último.

## DEFINITION OF DONE

143 testes históricos mais novos testes passam; todos os três jobs submetidos mantêm prompt/history/raw output; P raw é auditável e possui pose QA; identity é fail-closed; multi-subject é hard failure; benchmark/confirmation/walk/anchors são NOT_RUN; `main` está publicado; ZIP final auto-validado e criado por último.

## REVIEW ZIP

`review/UGAS-REVIEW-v0.6.1-<timestamp>.zip`, criado por último, com auto-validação sem alterações posteriores no filesystem.
