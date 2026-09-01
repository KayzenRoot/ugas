# Installing UGAS 0.11.1

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
```

## v0.11.1 deterministic weapon-continuity correction

Use `python -m ugas.animation validate-spec profiles/animation/attack-front-v2.json`, ou o runner completo `python scripts/validation/run_animation_runtime_v0111.py --json`. Ele executa o proxy pré-render, regressão das curvas, replay histórico, QA estrutural/pose, package e evidências em `docs/evidence/animation-runtime-v0111/`. A lane é source-only: não baixa pesos, não executa ComfyUI/SAM2/diffusion e não autoriza produção. Depois, construa e valide o índice com `python scripts/validation/build_review_index_v0111.py --tests-count <N> --validation-checks <N> --json` e `python scripts/validation/validate_review_index_v0111.py docs/evidence/review-index-v0.11.1.json`.

## v0.11.0 deterministic motion-quality attack (historical)

O v0.11.0 permanece preservado em `docs/evidence/animation-runtime-v0110/` como baseline histórico, inclusive o resultado false-green de continuidade identificado pelo v0.11.1.

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

O v0.9.1 permanece preservado em `current-state-v0.9.1.json`, `REVIEW-v0.9.1.md` e suas evidências. O estado ativo v0.11.1 é `CUTOUT_ANIMATION_RUNTIME_V2_ATTACK_FRONT_TECHNICALLY_QUALIFIED`; walk continua `pilot_only`, walk/idle/attack-v1 preservam decisões externas históricas `APPROVED_PILOT`, attack-v2 requer revisão externa, produção permanece bloqueada e nenhum resultado local equivale à aprovação externa do attack.
## v0.10.0 runtime check

After installation, validate a profile with `python -m ugas.animation validate-spec profiles/animation/attack-front-v1.json`. The v0.10.0 runner proves event markers, loop/non-loop lifecycle, deterministic 10-frame attack pose/weapon/foot/structural/MediaPipe QA, and the package gate: `python scripts/validation/run_animation_runtime_v0100.py`. The tracked pilot package is generated only after QA qualification; it is not production approval.
