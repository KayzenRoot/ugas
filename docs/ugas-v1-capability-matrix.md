# UGAS V1 capability matrix - v0.20.3 approved closure

This matrix is a planning contract for the functional rounds. v0.20.3 Environment/Tilesets is externally approved as a runtime, QA and governance foundation; real environment artwork remains NONE and production remains blocked. The next necessary capability is the v0.21.0 Maps/Minimap runtime foundation, limited to TEST_ONLY fixtures.

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
| `environment_tilesets` | Environment / tilesets | APPROVED_FOUNDATION | v0.20.3 closed |
| `maps_minimap_assets` | Maps / minimap assets | NEXT NECESSARY | v0.21.0 active |
| `ui_asset_family` | UI asset family | Pending | later V1 |
| `vfx_asset_family` | VFX asset family | Pending | later V1 |
| `orchestration_runtime_hardening` | Orchestration / runtime integration / hardening | Pending | V1 completion gates |

## Freeze and gate

The current functional candidate after the governed v0.20.3 ENVIRONMENT_TILESETS closure is `MAPS_MINIMAP`. `environment_tilesets=APPROVED_FOUNDATION`, `maps_minimap_assets=NEXT NECESSARY`, `next_candidate=MAPS_MINIMAP`, `next_capability_started=false`, `production_approved=false`, `production_routing=BLOCKED`, and `new_generation=0`. Maps/Minimap may begin only on a new v0.21.0 branch from the merged main commit, and only with TEST_ONLY fixtures.
