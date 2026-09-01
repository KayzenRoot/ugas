# UGAS v0.11.2 test coverage matrix

| Área | Teste/evidência | Critério |
|---|---|---|
| Scope recovery | `tests/test_qa_integrity_v0112.py`, `identity-proof-v0112.json` | `motion_tracks` e `key_pose_bindings` iguais ao v0.11.0 antes do render |
| Semantic thresholds | `threshold-binding-v0112.json` | oito nomes semânticos, valores preservados, adapter consumidor único |
| Attack-v1 reference | `attack-v1-baseline-fail-closed-v0112.json` | caminho conhecido, commit e SHA imutáveis; ausência/divergência falha fechado |
| Body mechanics | `attack-v2-body-mechanics-qa-v0112.json` | root, torso, braço direito, contra-movimento esquerdo e cabeça passam |
| Weapon relation | `attack-v2-weapon-arc-qa-v0112.json` | unwrap angular, pico ativo relativo, aceleração coerente e follow-through direcional |
| Foot ground | `attack-v2-foot-ground-qa-v0112.json` | soles/ankles e balance permanecem qualificados |
| NC-01 | `negative-controls-v0112.json` | curvas malformadas são REJECTED |
| NC-02..NC-04 | `negative-controls-v0112.json` | isolamento corporal produz `BODY_MECHANICS_GAP` |
| NC-05 | `negative-controls-v0112.json` | attack-v1 ausente/incorreto falha fechado |
| NC-06 | `negative-controls-v0112.json` | threshold impossível derruba o gate |
| NC-07..NC-08 | `negative-controls-v0112.json` | aceleração incoerente/reversão produzem `WEAPON_ARC_GAP` |
| NC-09 | `negative-controls-v0112.json` | foot slide produz `FOOT_GROUND_GAP` |
| NC-10 | `negative-controls-v0112.json` | package rejeita `QUALIFIED` com hard gate falso |
| Pixel identity | `qa-integrity-scope-recovery-v0112.json`, `identity-proof-v0112.json` | 12 frames, spritesheet e GIF byte-identical ao v0.11.0 |
| Historical replay | `historical-replay-v0112.json` | review/evidência v0.11.1 preservados no commit rejeitado |
| Runtime/package | `execution-evidence-v0.11.2.json`, compiled/QA/package manifests | source-only, 12 frames, markers/tracks hash-bound, production BLOCKED |
| State/governance | `validate_state_consistency_v0112.py`, `run_validation.py` | estado atual, limites externos e próximo passo único consistentes |

## Commands

```powershell
python -m unittest discover -s tests -q
python scripts/validation/run_validation.py
python scripts/validation/validate_review_index_v0112.py docs/evidence/review-index-v0.11.2.json
```
