# Windows/NVIDIA Render Node

The render-node helper is local-only by default and stores configuration/workspace below `%LOCALAPPDATA%\\UGAS`. It never installs arbitrary custom nodes and never binds a local server to `0.0.0.0`.

```powershell
ugas render-node doctor
ugas render-node setup
ugas render-node start
ugas render-node status
ugas render-node probe
ugas render-node stop
```

`doctor` reports OS, Python, `nvidia-smi`, GPU/driver/VRAM, disk, ComfyUI path, endpoint and health. `setup` is idempotent and first inspects `comfy --help` and `comfy install --help`; the actual official install is an explicit operator action. Start/stop/status use the configured workspace and an argument list rather than a shell string.

The RTX 5050 is a target constraint, not proof of successful generation. OOM, missing models, missing native nodes or unavailable server remain recorded blockers. A remote node is a separate provider: it must be reachable on a private network and gets no local GPU inference.
