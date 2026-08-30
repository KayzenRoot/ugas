# Installing UGAS 0.5.0

## Requirements

- Python 3.12+ with Pillow available.
- ComfyUI local em `http://127.0.0.1:8188`.
- FLUX.2 Klein Base NVFP4 and BiRefNet registrados com hashes aprovados fora do repositório.
- GPU testada: NVIDIA GeForce RTX 5050, 8 GiB.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -q
python scripts/validation/run_validation.py
```

## v0.5 pilot

O workflow `flux2-klein-base-4b-quality-multi-reference-edit` usa apenas nós nativos e encadeia `ReferenceLatent`. A execução começa pelo anchor R4 exato, valida os guias JSON/Pillow, mede A/B com seeds pareadas, gera duas tentativas por direção e no máximo uma tentativa direcionada por frame. O piloto walk usa sempre R4 + guia do frame; nunca usa o frame anterior como entrada.

Os pesos não são publicados. A saída técnica atual e o histórico completo estão em `docs/evidence/`; a aprovação visual humana é independente dos gates automatizados.
