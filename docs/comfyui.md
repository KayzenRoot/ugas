# ComfyUI integration notes - UGAS v0.12.0

The active release is v0.12.0. The local observability dashboard probes ComfyUI read-only and never starts generation; the deterministic QA-integrity/scope-recovery cutout-rig lane from v0.11.2 remains historical. The v0.8.0/v0.7.3/v0.9.0/v0.9.1/v0.10.0/v0.11.0 structural and runtime/model/custom-node records below remain historical; v0.11.1 remains rejected history.

The v0.6.0 release records the bounded SDXL ControlNet/IP-Adapter runtime qualification. The ComfyUI/RTX 5050 and A/C/R evidence below is historical and remains unchanged. v0.8.1 reuses v0.7.1 parts and the v0.7.3 structural core as immutable inputs, uses deterministic skeleton interpolation plus Pillow transforms, and has zero ComfyUI generation jobs; it remains blocked from production routing until external visual review.

O alvo local é ComfyUI `0.34.0` com NVIDIA GeForce RTX 5050. O runtime e o grafo nativo foram verificados para as lanes A, C e R. Não houve custom node nem troca de provider.

`reference[0]` é o anchor R4 de identidade; `reference[1]`, quando presente, é o guia determinístico de pose. A lane C usa a ordem nativa pose-first/identity-second descrita pelo workflow; R usa `LoraLoaderModelOnly` nativo a `0.8` com o LoRA verificado.

O estimador MediaPipe é somente QA. A documentação oficial do [Pose Landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker) e o [model card oficial](https://storage.googleapis.com/mediapipe-assets/Model%20Card%20BlazePose%20GHUM%203D.pdf) são registrados nas evidências. O bundle `.task` fica fora do Git e do ZIP.

O recheck histórico foi end-to-end: prompt, polling de history, output, BiRefNet para QA transparente, MediaPipe, métricas por junta e overlays. A calibração 05D atualiza somente a lane P, sem IP-Adapter e sem BiRefNet na qualificação. Health, GPU e cache sozinhos nunca substituem essa prova.
## v0.11.2 boundary

The v0.11.2 animation runtime performs no ComfyUI generation. `comfyui_generation_jobs=0`, `sam2_runs=0`, `new_generation=0`, and `diffusion_runs=0`; the source-only cutout runtime is the qualified lane for this slice. `motion_tracks` and `key_pose_bindings` are restored byte-for-byte at semantic level from v0.11.0, QA thresholds are consumed from the declared profile, attack-v1 comparison is fail-closed, and relational weapon gates are evidenced. The package gate is `decision=QUALIFIED`, external attack-front-v2 review remains required, and production routing is blocked.
