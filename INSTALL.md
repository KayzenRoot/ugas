# Installing UGAS 0.7.2

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

## v0.7.2 deterministic cutout-rig occlusion/gait qualification

Leia [docs/evidence/current-state.json](docs/evidence/current-state.json) antes de iniciar. O provider é uma lane isolada e não altera o routing de produção. A origem SAM2 oficial é fixada por commit; source, checkpoint e runtime ficam fora do Git e do review ZIP.

Depois, use os scripts e gates descritos em [REVIEW-v0.7.2.md](REVIEW-v0.7.2.md). A qualificação reutiliza a revisão, skeleton, máscaras e partes v0.7.1 hash-bound, executa somente Q0/K1/K2/K3/K4, e usa o plano topológico de oclusão com QA MediaPipe. O renderer usa somente Pillow; não há nova execução SAM2, ComfyUI ou walk.

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

O v0.7.0 permanece preservado em `current-state-v0.7.0.json` e `REVIEW-v0.7.0.md`; o v0.6.2 permanece histórico como `REVIEW_ARCHIVE_VERIFIED`, e o v0.5.4 permanece a fonte dos thresholds de pose. O estado atual é `CUTOUT_RIG_SEAM_GAP`; walk permanece não autorizado e nenhum resultado local equivale a aprovação externa.
