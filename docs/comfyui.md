# ComfyUI v0.4.2

UGAS uses the official local ComfyUI HTTP API with native nodes only. The model registry keeps explicit FLUX.2 Klein Base and Distilled records and compatible text-to-image/edit graphs, plus native BiRefNet.

- FAST Distilled: 4 steps, guidance 1.0;
- QUALITY Base: 50 steps, guidance 4.0;
- BiRefNet: mask -> original RGB + foreground alpha -> unique revision output.

Health, inventory and node discovery are evidence inputs, not proof of visual quality. A real qualification requires exact hashes and a live job. The request path is upload, graph binding, `/prompt`, bounded history polling, output retrieval, QA and revision persistence.

Keep ComfyUI on localhost/private networks. Never put tokens, private configuration, weights or generated output in the repository. No arbitrary custom nodes or paid provider is enabled.
