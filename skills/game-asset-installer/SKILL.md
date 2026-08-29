---
name: game-asset-installer
description: Installs UGAS into consumer game projects by detecting engine context selecting a profile and creating the .game-assets contract. Use when bootstrapping or safely refreshing a consumer project.
license: MIT
metadata:
  ugas-version: "0.2.1"
---

# game-asset-installer

## Description and trigger
Use when a consumer project asks to install or refresh UGAS.

## When to use
Inspect the project, select a profile, and create the `.game-assets/` contract.

## When NOT to use
Do not use for generating final assets, changing gameplay code, or overwriting a non-empty bootstrap without confirmation.

## Conceptual dependencies
`game-context-resolver`, profiles, schemas, and provider manifests.

## Execution
Resolve engine and language, validate the requested profile, write deterministic base files, and record provenance.

## Outputs
`.game-assets/`, an installation review, and a checkpoint ready for human review.

## Limits and care
Never persist credentials, download models, or claim external provider health from file creation alone.
