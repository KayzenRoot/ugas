# UGAS v0.5.5 test coverage matrix

| Requirement | Automated evidence | Acceptance |
|---|---|---|
| Generation filenames containing `seed` are public metadata | `src/ugas/review_snapshot.py`, `tests/test_review_packaging_v055.py` | `a-seed-54701.png`, `some-model-seed-metadata.json`, `tokenizer.json` and `monkey.png` are included by the matcher |
| Explicit secrets remain blocked | `src/ugas/review_snapshot.py`, matcher self-test | `.env`, credentials, private keys, API/access tokens and wallet recovery names are excluded with specific reasons |
| Review tooling version | `create_review_zip.py --self-test`, archive manifest | Script version `1.8.0` |
| Canonical v0.5.4 outputs | `scripts/validation/verify_review_archive.py` | Exactly 9 PNG paths are present and valid |
| Canonical hashes | `v054-pose-error-table.json` plus archive verifier | Every PNG SHA-256 matches the table |
| Human convenience copies | Archive verifier | Every `__REVIEW__/visual-evidence` copy equals its canonical source |
| Snapshot completeness | Local packager and archive verifier | Manifest/test-required sources cannot disappear through a generic security matcher |
| Archive safety | Archive verifier | CRC, path traversal, absolute paths, weights and secret paths fail closed |
| Clean extraction | Archive verifier | `compileall`, unittest and repository validation execute outside the repository and without `.git` |
| Git binding | Archive verifier | `__REVIEW__/manifest.json.head_commit` equals `__REVIEW__/git-head.txt` |
| Pose decision preservation | `current-state.json`, `state_consistency.py`, `REVIEW-v0.5.5.md` | Pose remains `LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED`; no new generation evidence |

The v0.5.4 generation evidence, thresholds and 9 lane outputs are historical
inputs to this packaging correction. This release does not run ComfyUI,
MediaPipe, walk, anchors or a new provider.
