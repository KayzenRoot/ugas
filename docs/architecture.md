# Architecture

```text
request -> classifier/profile/Art DNA -> capability evidence -> provider router
       -> qualified workflow/model -> ComfyUI /prompt -> history -> /view PNG
       -> technical QA -> provenance -> consumer asset registry
```

The HTTP client, model/workflow registries, capability evidence, job state machine, image utilities, QA and provenance modules are dependency-light. Pillow is the only runtime image dependency. Job transitions are durable JSON with bounded retries. Technical validity never implies visual or production approval.

The consumer installer copies the runtime under `.game-assets/tools`; source checkout location is not persisted as a runtime dependency. Weight files and generated outputs remain outside Git.
