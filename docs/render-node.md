# RTX 5050 Render Node

The Render Node is a separate PC that hosts ComfyUI, typically with an NVIDIA RTX 5050. Cursor or Codex may run on another machine and route approved generation work to the node.

## Recommended topology

Use a private overlay such as Tailscale or an equivalent VPN. Bind ComfyUI to the private interface, restrict access to the consumer machine or service identity, and do not expose the ComfyUI port directly to the public internet. Keep the endpoint and credentials in consumer-local configuration.

## Readiness sequence

1. Verify the private network path.
2. Probe the node's ComfyUI `/system_stats` endpoint.
3. Confirm the expected GPU and compatible CUDA/driver stack on the node.
4. Resolve a versioned workflow and model manifest.
5. Submit only after policy, budget, license, and human approval gates pass.
6. Poll and retrieve outputs with request ID and provenance.

If the node is unavailable, `local-first` tries local ComfyUI and then Hugging Face; a route is not a generation result. The V0.2 dry-run explicitly reports the RTX 5050 as an expected remote target rather than asserting that this workstation has one.
