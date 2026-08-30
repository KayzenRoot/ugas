# Installing UGAS 0.6.1

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

## v0.6.1 smoke correction

Leia [docs/evidence/current-state.json](docs/evidence/current-state.json) antes de iniciar. A consistência do estado e a auditoria do custom node devem passar antes dos downloads; pesos e o custom node permanecem fora do Git e do review ZIP.

Depois, use os scripts e gates descritos em [REVIEW-v0.6.1.md](REVIEW-v0.6.1.md). Esta correção não baixa modelos nem altera o pin do `ComfyUI_IPAdapter_plus`; executa somente o smoke P/I/PI com seed 61701. A evidência de geração é materializada antes do BiRefNet, e falhas posteriores permanecem estruturadas. Benchmark, confirmação, walk e anchors permanecem proibidos.

O v0.5.5 permanece histórico como `REVIEW_ARCHIVE_VERIFIED`, e o v0.5.4 permanece a fonte da decisão de pose `LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED`. Walk permanece não autorizado; nenhum resultado de qualificação desta lane autoriza animação automaticamente.
