# UGAS custom-node boundary

The UGAS repository stores metadata only. Custom-node source is never vendored
into Git or the review ZIP. The v0.6.0 candidate is installed externally at an
exact commit and is removable without deleting shared model files.

The only permitted candidate is the pinned `cubiq/ComfyUI_IPAdapter_plus`
checkout recorded in `registry.json`. A floating branch, unreviewed update,
fork or alternate provider is a qualification gap.
