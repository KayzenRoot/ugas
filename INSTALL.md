# Installing UGAS 0.5.5

## Requirements

- Python 3.12+ com Pillow disponível para validação e verificador.
- ComfyUI, MediaPipe e GPU não são necessários nesta release: nenhum job novo é autorizado.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -q
python scripts/validation/run_validation.py
```

## v0.5.5 review snapshot integrity

Leia `docs/evidence/current-state.json` antes de iniciar qualquer execução. Esta release corrige somente review tooling, snapshot validation, testes e documentação. Não reexecute ComfyUI ou MediaPipe e não modifique `docs/evidence/pose-thresholds-v054.json`.

O verificador tracked recebe um ZIP final e prova CRC, ausência de traversal, ausência de pesos/segredos, presença dos 9 paths canônicos, igualdade dos hashes e execução limpa de compileall, unittest e repository validation fora do Git.

O estado de pose continua `LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED`; o estado de release é `REVIEW_SNAPSHOT_INTEGRITY_FIXED` / `REVIEW_ARCHIVE_VERIFIED`. Não execute walk, âncoras v3, provider alternativo ou nova geração a partir deste estado.
