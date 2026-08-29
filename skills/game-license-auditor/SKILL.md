---
name: game-license-auditor
description: Checks game asset source license attribution restrictions and commercial-use metadata before registry approval. Use whenever a reference model image or generated output becomes distributable.
license: MIT
metadata:
  ugas-version: "0.2.1"
---

# game-license-auditor

## Description and trigger
Use before adding an asset or reference to a distributable registry.

## When to use
Check declared source, license, attribution, restrictions, and commercial-use status.

## When NOT to use
Do not infer permission from a URL or from an absent license field.

## Conceptual dependencies
Registry, provenance, references, and project license policy.

## Execution
Require explicit metadata and flag unknown or incompatible terms for review.

## Outputs
A license status attached to the asset decision.

## Limits and care
This is metadata governance, not legal advice.
