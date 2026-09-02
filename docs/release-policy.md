# UGAS release and evidence policy

## Version tags and candidates

Release tags are created only after the corresponding PR has been externally reviewed, merged through the protected `main` path and has evidence bound to the exact commit. Release candidates use an explicit versioned branch/PR and never rewrite previous history.

## Changelog and GitHub Releases

Each release PR records its scope, changed files, tests, validation, evidence, risks, known gaps and production boundary. GitHub Releases are currently absent from the repository. Publishing historical releases or tags is a later milestone and must be evidence-bound; this v0.12.3 round does not backfill them.

## Evidence requirements

The GitHub review workflow is the transport surface for machine manifests and bounded review visuals. It must identify repository, PR number, base/head/merge-base, changed-file statistics, current state/gate, production flags, actual test/validation totals, review-index status, known gaps and dashboard policy. Visual manifests must contain path, media type, byte size and SHA-256 for every visual referenced by the active increment.

Secrets, local credentials, telemetry databases, model weights and large generation directories never belong in tracked evidence or workflow artifacts. A local green result does not claim external approval or production readiness.
