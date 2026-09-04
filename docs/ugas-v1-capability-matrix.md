# UGAS V1 capability matrix - v0.15.1

This matrix is a planning contract for the functional rounds. v0.15.1 technically qualifies the corrected source-only DEATH_ANIMATION_FRONT pilot; external visual review is still REQUIRED and production remains blocked. The rejected v0.15.0 evidence remains historical.

| ID | Capability | Status after v0.12.3 | Planned order |
| --- | --- | --- | --- |
| `core_2d_generation` | Core 2D generation / master / transparency / provenance | Existing foundation | Preserve |
| `deterministic_cutout_rig` | Deterministic cutout rig + walk/idle/attack pilots | Pilot-qualified history | Preserve |
| `local_always_on_observability` | Local always-on observability | Technically qualified; external visual review pending | Close now |
| `github_native_review_infrastructure` | GitHub-native review infrastructure | This increment | v0.12.3 |
| `run_front_v1` | Run animation - front | APPROVED_PILOT | v0.13.1 closed |
| `hit_reaction_front` | Hit reaction - front | APPROVED_PILOT | v0.14.1 closed |
| `death_animation_front` | Death animation - front | TECHNICALLY_QUALIFIED_EXTERNAL_VISUAL_REQUIRED | current |
| `multi_direction_animation_runtime` | Multi-direction animation/runtime | Pending | after front library proves reusable |
| `equipment_outfits` | Equipment / outfits | Pending | later V1 |
| `creatures_monsters` | Creatures / monsters | Pending | later V1 |
| `items_props` | Items / props | Pending | later V1 |
| `environment_tilesets` | Environment / tilesets | Pending | later V1 |
| `maps_minimap_assets` | Maps / minimap assets | Pending | later V1 |
| `ui_asset_family` | UI asset family | Pending | later V1 |
| `vfx_asset_family` | VFX asset family | Pending | later V1 |
| `orchestration_runtime_hardening` | Orchestration / runtime integration / hardening | Pending | V1 completion gates |

## Freeze and gate

The current functional candidate after the governed v0.14.1 HIT_REACTION_FRONT merge is `DEATH_ANIMATION_FRONT`. `production_approved=false`, `production_routing=BLOCKED`, `new_generation=0`, and the only allowed next action is `external_visual_review_death_animation_front`. Do not mark death `APPROVED_PILOT` before external visual review.
