# UGAS V1 capability matrix - v0.19.0

This matrix is a planning contract for the functional rounds. v0.18.2 is the externally approved creatures/monsters runtime foundation; real creature artwork remains NONE and production remains blocked. The rejected v0.18.0 and v0.18.1 corrections remain historical.

| ID | Capability | Status after v0.12.3 | Planned order |
| --- | --- | --- | --- |
| `core_2d_generation` | Core 2D generation / master / transparency / provenance | Existing foundation | Preserve |
| `deterministic_cutout_rig` | Deterministic cutout rig + walk/idle/attack pilots | Pilot-qualified history | Preserve |
| `local_always_on_observability` | Local always-on observability | Technically qualified; external visual review pending | Close now |
| `github_native_review_infrastructure` | GitHub-native review infrastructure | This increment | v0.12.3 |
| `run_front_v1` | Run animation - front | APPROVED_PILOT | v0.13.1 closed |
| `hit_reaction_front` | Hit reaction - front | APPROVED_PILOT | v0.14.1 closed |
| `death_animation_front` | Death animation - front | TECHNICALLY_QUALIFIED_EXTERNAL_VISUAL_REQUIRED | current |
| `multi_direction_animation_runtime` | Multi-direction animation/runtime | APPROVED_FOUNDATION | v0.16.2 closed |
| `equipment_outfits` | Equipment / outfits | APPROVED_FOUNDATION | v0.17.1 closed |
| `creatures_monsters` | Creatures / monsters | APPROVED_FOUNDATION | v0.18.2 closed |
| `items_props` | Items / props | NEXT NECESSARY | v0.19.0 active; external review required |
| `environment_tilesets` | Environment / tilesets | Pending | later V1 |
| `maps_minimap_assets` | Maps / minimap assets | Pending | later V1 |
| `ui_asset_family` | UI asset family | Pending | later V1 |
| `vfx_asset_family` | VFX asset family | Pending | later V1 |
| `orchestration_runtime_hardening` | Orchestration / runtime integration / hardening | Pending | V1 completion gates |

## Freeze and gate

The current functional candidate after the governed v0.18.2 CREATURES_MONSTERS closure is `ITEMS_PROPS`. `creatures_monsters=APPROVED_FOUNDATION`, `equipment_outfits=APPROVED_FOUNDATION`, `multi_direction_animation_runtime=APPROVED_FOUNDATION`, `next_candidate=ITEMS_PROPS`, `next_capability_started=false`, `production_approved=false`, `production_routing=BLOCKED`, and `new_generation=0`. Items/props may begin only on a new v0.19.0 branch after PR #8 is merged through the protected path.
