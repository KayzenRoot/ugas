---
name: provider-manifest-registry
description: Registers and validates provider capability availability endpoint and credential-policy declarations for the UGAS router. Use when adding or reviewing a provider contract.
license: MIT
metadata:
  ugas-version: "0.2.1"
---

# provider-manifest-registry

## Description and trigger
Use when registering a provider contract for routing.

## When to use
Validate provider identity, capabilities, endpoint policy, and supported operations.

## When NOT to use
Do not mark an untested endpoint healthy.

## Conceptual dependencies
Provider manifest schema and provider router.

## Execution
Load versioned JSON manifests and preserve declared status separately from live probes.

## Outputs
Discoverable provider manifest set.

## Limits and care
Registry metadata is not live service availability.
