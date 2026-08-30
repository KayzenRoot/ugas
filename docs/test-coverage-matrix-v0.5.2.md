# UGAS v0.5.2 test coverage matrix

| Contract | Automated evidence | Gate |
|---|---|---|
| State consistency | current-state schema, checkpoint/review scan, contradiction fixture | fatal before new jobs |
| OpenPose COCO-18 v3 | deterministic JSON/PNG, 18-joint topology, unavailable joints explicit | required |
| Native order benchmark | fresh A/B/C seeds, exact workflow/history/output hashes, no previous frame | 3/3 per lane |
| Pose qualification | mean/floor thresholds and fixed gain >= 0.15 | required |
| RefControl fallback | exact model hash/license, native loader, reference order, strength benchmark | only after native gap |
| Identity and weapon | regional descriptor and hard 3/3 weapon gate | required |
| Escalation guard | no anchors/walk/spritesheet without qualified lane | fatal |
| Publication | full tests, validator, clean GitHub main, archive audit | required |

All v0.5.1 tests remain in the suite. Historical v0.5.1 evidence is never reclassified by the current release.
