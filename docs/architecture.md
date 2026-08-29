# UGAS architecture

UGAS has a neutral metadata plane and optional provider adapters. The orchestrator receives an asset request, resolves consumer context, loads a profile and Art DNA, checks registry reuse, creates a plan, routes to a provider, validates outputs, and records provenance.

```text
request
  -> context resolver + profile
  -> orchestrator
  -> reuse / registry / budget / license checks
  -> asset tool router
  -> generation provider router
  -> ComfyUI | private RTX 5050 Render Node | Hugging Face fallback
  -> manifests + validators + provenance
```

The V0.2.1 Python runtime implements bounded context inspection, evidence-backed profile resolution, consumer bootstrap, deterministic capability-aware request classification, provider ordering, and safe readiness probes. The Agent Skills carry the operational contracts for later agents. No provider is allowed to make the game runtime or server authoritative state implicit.

## Boundaries

- The repository owns contracts, profiles, metadata, and checks.
- The consumer project owns gameplay, engine import behavior, final approval, and secret storage.
- Providers own generation execution and service health.
- Human reviewers own visual, license, and release decisions.

## Policies

`free-first` prefers Hugging Face, then local ComfyUI, then the Render Node. `local-first` prefers local ComfyUI, then the private Render Node, then Hugging Face. `remote-first` reverses the local order. `paid-disabled` filters only providers whose manifest cost class is `paid`; a `self-hosted` remote Render Node remains eligible. Availability is `available`, `unavailable`, or `unknown`, and no unprobed provider is selected.
