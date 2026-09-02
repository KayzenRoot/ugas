# Installing UGAS 0.12.1

## Requirements

- Python 3.12+ com Pillow disponível para validação.
- ComfyUI local em `http://127.0.0.1:8188` quando a lane real for executada.
- GPU NVIDIA compatível; a qualificação mantém resolução mínima de 512x512.
- Os pesos ficam fora deste repositório e fora do review ZIP.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
$env:PYTHONPATH = "src"
python scripts/validation/validate_state_consistency.py
python -m unittest discover -s tests -q
python scripts/validation/run_validation.py
python scripts/validation/run_observability_v0121.py
python -m ugas.cli dashboard --host 127.0.0.1 --port 8765 --no-open
```

## Local observability dashboard

The v0.12.1 dashboard is a local read-only HTTP/SSE service. It binds to loopback by default, stores bounded telemetry in `.ugas/runtime/telemetry.db`, and never uploads analytics or serves arbitrary files. Start it with `python -m ugas.cli dashboard`; `--port 0` selects an ephemeral port for smoke tests and `--no-open` suppresses browser launch. Non-loopback hosts are rejected.

The UI reports `N/A`, `UNAVAILABLE`, `TIMEOUT` or `STALE_LAST_KNOWN` with a reason when the NVIDIA stack, process metrics or ComfyUI endpoint is not available. It does not start a generation job, and untrusted values are rendered through DOM text nodes. See [REVIEW-v0.12.1.md](REVIEW-v0.12.1.md) and `docs/evidence/observability-v0121/` for the runtime proof.

## v0.12.1 governance boundary

The v0.11.2 external visual decision is recorded as `APPROVED_PILOT` only. `production_approved=false` and `production_routing=BLOCKED` remain authoritative in `docs/evidence/current-state.json`; the next action waits for external review of the v0.12.1 dashboard. The v0.12.0 correction history is preserved separately.

## v0.11.2 QA integrity and scope recovery

Use `python -m ugas.animation validate-spec profiles/animation/attack-front-v2.json`, ou o runner completo `python scripts/validation/run_animation_runtime_v0112.py`. Ele verifica a restauração dos tracks/bindings v0.11.0, thresholds declarados, baseline attack-v1 fail-closed, regras relacionais, NC-01..NC-10, replay e package em `docs/evidence/animation-runtime-v0112/`. A lane é source-only: não baixa pesos, não executa ComfyUI/SAM2/diffusion e não autoriza produção. Depois, construa e valide o índice com `python scripts/validation/build_review_index_v0112.py --tests-count <N> --validation-checks <N> --json` e `python scripts/validation/validate_review_index_v0112.py docs/evidence/review-index-v0.11.2.json`.

## v0.11.0 deterministic motion-quality attack (historical)

O v0.11.0 permanece preservado em `docs/evidence/animation-runtime-v0110/` como baseline visual histórico. O v0.11.1 permanece preservado em `REVIEW-v0.11.1.md`, `current-state-v0.11.1.json` e `docs/evidence/animation-runtime-v0111/` como rejected history.

## v0.8.1 deterministic front-walk QA correction

Leia [docs/evidence/current-state.json](docs/evidence/current-state.json) antes de iniciar. O provider é uma lane isolada e não altera o routing de produção. A origem SAM2 oficial é fixada por commit; source, checkpoint e runtime ficam fora do Git e do review ZIP.

Depois, use os scripts e gates descritos em [REVIEW-v0.8.1.md](REVIEW-v0.8.1.md). A qualificação reutiliza a revisão, skeleton, máscaras e partes v0.7.1 hash-bound, o core estrutural v0.7.3 e os targets K1–K4 exatos; o renderer usa somente Pillow e a geração intermediária é de skeleton, sem nova execução SAM2 ou ComfyUI. Execute `python scripts/validation/run_cutout_front_walk_v081.py --json` e depois `python scripts/validation/run_validation.py`.

### Runtime SAM2 externo

Use um diretório fora do repositório e fixe o commit registrado no review. O caminho pode ser informado por `UGAS_SAM2_PYTHON`; sem essa variável a CLI procura `%LOCALAPPDATA%/UGAS/comfyui/.venv/Scripts/python.exe`.

```powershell
$samRoot = Join-Path $env:LOCALAPPDATA "UGAS/tools/sam2"
git clone https://github.com/facebookresearch/sam2.git $samRoot
git -C $samRoot checkout 2b90b9f5ceec907a1c18123530e92e794ad901a4
# Instale o pacote e o checkpoint no runtime externo, nunca neste repositório.
$env:UGAS_SAM2_PYTHON = "<isolated-python.exe>"
$env:PYTHONPATH = "src"
python -m ugas.cli cutout-rig qualify-sam2 --json
```

O checkpoint oficial `sam2.1_hiera_small.pt` deve ficar em `%LOCALAPPDATA%/UGAS/models/sam2/` e ser conferido pelo SHA-256 registrado em `docs/evidence/sam2-checkpoint-provenance-v071.json`. A instalação não usa custom node ComfyUI nem executa jobs ComfyUI.

O v0.9.1 permanece preservado em `current-state-v0.9.1.json`, `REVIEW-v0.9.1.md` e suas evidências. O estado ativo v0.11.2 é `CUTOUT_ANIMATION_RUNTIME_V2_ATTACK_FRONT_TECHNICALLY_QUALIFIED`; walk continua `pilot_only`, walk/idle/attack-v1 preservam decisões externas históricas `APPROVED_PILOT`, attack-v2 requer revisão externa, produção permanece bloqueada e nenhum resultado local equivale à aprovação externa do attack.
## v0.10.0 runtime check

After installation, validate a profile with `python -m ugas.animation validate-spec profiles/animation/attack-front-v1.json`. The v0.10.0 runner proves event markers, loop/non-loop lifecycle, deterministic 10-frame attack pose/weapon/foot/structural/MediaPipe QA, and the package gate: `python scripts/validation/run_animation_runtime_v0100.py`. The tracked pilot package is generated only after QA qualification; it is not production approval.
