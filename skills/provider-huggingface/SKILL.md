---
name: provider-huggingface
description: Represents Hugging Face as an explicit game asset fallback with model license quota and availability checks. Use only when policy and declared capabilities permit it.
license: MIT
metadata:
  ugas-version: "0.2.1"
---

# provider-huggingface

## Description and trigger
Use as a declared alternative provider when policy and availability permit.

## When to use
Route eligible requests to a free or remote alternative after local-first failures.

## When NOT to use
Do not assume a hosted model, quota, license, or network response exists.

## Conceptual dependencies
Provider router, provider manifest, license auditor, and provenance.

## Execution
Use model metadata and explicit availability; never persist tokens in the repository.

## Outputs
Fallback decision or a clearly unavailable state.

## Limits and care
V0.2 does not call Hugging Face or download models.
