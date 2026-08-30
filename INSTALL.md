# Installing UGAS 0.5.2

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

## v0.5.2 pose-control escalation

Leia `docs/evidence/current-state.json` antes de iniciar qualquer execução. O fluxo é: consistência de estado, guia OpenPose COCO-18 v3, benchmark nativo A/B/C com seeds frescas 52701–52703 e, somente se houver gap nativo, verificação estrita do RefControl LoRA e de um loader LoRA nativo compatível. A ordem das referências, prompt, histórico, seed, workflow e hashes são evidências obrigatórias.

Os pesos não são publicados. Âncoras v3, walk/front/8 v3 e spritesheet são proibidos enquanto a pose não estiver qualificada. A aprovação visual humana é independente dos gates automatizados.
