# ComfyUI integration notes - UGAS v0.6.2

The active release is v0.6.2 and only executes the bounded P-only OpenPose model-card calibration. The v0.6.1 and v0.6.0 runtime/model/custom-node records below remain historical.

The v0.6.0 release records the bounded SDXL ControlNet/IP-Adapter runtime qualification. The ComfyUI/RTX 5050 and A/C/R evidence below is historical v0.5.4 evidence and remains unchanged; the v0.6.2 model-card calibration executed P0/P1/P2 and remains stopped at `SDXL_OPENPOSE_CONTROL_GAP_CONFIRMED_AT_MODEL_CARD_SETTINGS`.

O alvo local é ComfyUI `0.34.0` com NVIDIA GeForce RTX 5050. O runtime e o grafo nativo foram verificados para as lanes A, C e R. Não houve custom node nem troca de provider.

`reference[0]` é o anchor R4 de identidade; `reference[1]`, quando presente, é o guia determinístico de pose. A lane C usa a ordem nativa pose-first/identity-second descrita pelo workflow; R usa `LoraLoaderModelOnly` nativo a `0.8` com o LoRA verificado.

O estimador MediaPipe é somente QA. A documentação oficial do [Pose Landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker) e o [model card oficial](https://storage.googleapis.com/mediapipe-assets/Model%20Card%20BlazePose%20GHUM%203D.pdf) são registrados nas evidências. O bundle `.task` fica fora do Git e do ZIP.

O recheck histórico foi end-to-end: prompt, polling de history, output, BiRefNet para QA transparente, MediaPipe, métricas por junta e overlays. A calibração 05D atualiza somente a lane P, sem IP-Adapter e sem BiRefNet na qualificação. Health, GPU e cache sozinhos nunca substituem essa prova.
