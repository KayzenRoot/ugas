# UGAS v0.9.0 test coverage

| Area | Evidence | Negative control |
| --- | --- | --- |
| Spec/schema | four Draft 2020-12 v1 schemas and semantic loader | frame count and ambiguous timing |
| Generic lifecycle | validate-spec, compile, qa, package | package without qualified QA |
| Walk compatibility | eight canonical RGBA hashes and spritesheet | mutated target hash |
| Idle deterministic runtime | two compile manifests with identical target/RGBA hashes | zero motion and overmotion |
| Frame QA | source, transform, alpha, structural, topology, retention, MediaPipe, sword, duplicate body | +3 px foot and frozen z-order mutation |
| Review governance | visual manifest and Review Index v2 | self-referential `head_commit` rejected |
| Historical integrity | v0.8.1 snapshot and validator | historical snapshot must remain green |

Production routing is BLOCKED and external idle-front review remains REQUIRED.
