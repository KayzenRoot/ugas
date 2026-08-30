# Installing UGAS 0.5.3

## Requirements

- Python 3.12+ with Pillow available.
- ComfyUI local em `http://127.0.0.1:8188` para o benchmark real.
- FLUX.2 Klein Base NVFP4 e BiRefNet registrados com hashes aprovados fora do repositório.
- GPU testada: NVIDIA GeForce RTX 5050, 8 GiB.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -q
python scripts/validation/run_validation.py
```

## v0.5.3 pose-metric calibration

Leia `docs/evidence/current-state.json` antes de iniciar qualquer execução. O fluxo é: consistência de estado, guard de impossibilidade, calibração sintética de joints, qualificação do estimador QA e só então uma eventual rechecagem A/C/R com seeds 53701–53703. A métrica antiga de silhueta é diagnóstica. O estimador não é provider nem nó de geração.

Os pesos e bundles não são publicados. Âncoras v3, walk/front/8 v3 e spritesheet são proibidos enquanto a pose não estiver qualificada. O estado atual é `POSE_QA_MODEL_LICENSE_GAP`; resolver os termos do bundle é pré-requisito. A aprovação visual humana é independente dos gates automatizados.
