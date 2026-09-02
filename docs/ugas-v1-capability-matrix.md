# UGAS V1 capability matrix - v0.12.3 freeze

This matrix is a planning contract for the next functional rounds. v0.12.3 implements review infrastructure only; it does not create a new asset family, generate an animation, alter `attack-front-v2`, or enable production.

| ID | Capability | Status after v0.12.3 | Planned order |
| --- | --- | --- | --- |
| `core_2d_generation` | Core 2D generation / master / transparency / provenance | Existing foundation | Preserve |
| `deterministic_cutout_rig` | Deterministic cutout rig + walk/idle/attack pilots | Pilot-qualified history | Preserve |
| `local_always_on_observability` | Local always-on observability | Technically qualified; external visual review pending | Close now |
| `github_native_review_infrastructure` | GitHub-native review infrastructure | This increment | v0.12.3 |
| `run_front_v1` | Run animation - front | NEXT NECESSARY | v0.13.0 candidate |
| `hit_reaction_front` | Hit reaction - front | Pending | after run |
| `death_animation_front` | Death animation - front | Pending | after hit |
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

The next functional candidate after external approval of the v0.12.3 PR is `RUN_FRONT_V1`. The external reviewer may change the order if this matrix exposes a stronger dependency. Until that decision, `production_approved=false`, `production_routing=BLOCKED`, `new_generation=0`, and the only allowed next action is `external_review_github_native_v0123_and_dashboard_v0122`.
