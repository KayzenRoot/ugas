# game-atlas-packer

## Description and trigger
Use when compatible 2D assets need atlas packing rules.

## When to use
Plan page size, padding, rotation policy, naming, and engine import settings.

## When NOT to use
Do not pack assets that have not passed registry and license checks.

## Conceptual dependencies
Registry, budget manager, sprite/tileset studios, and engine adapter.

## Execution
Return a packing plan and constraints; keep source paths traceable.

## Outputs
Atlas manifest and budget report.

## Limits and care
The bootstrap does not ship a heavy atlas binary toolchain.
