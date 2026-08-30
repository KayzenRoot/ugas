# Installing UGAS 0.5.4

## Requirements

- Python 3.12+ com Pillow e MediaPipe disponíveis.
- ComfyUI local em `http://127.0.0.1:8188` para a rechecagem real.
- FLUX.2 Klein Base NVFP4, BiRefNet e o LoRA RefControl registrados/verificados fora do repositório.
- GPU testada: NVIDIA GeForce RTX 5050, 8 GiB.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -q
python scripts/validation/run_validation.py
```

## v0.5.4 pose QA and lane recheck

Leia `docs/evidence/current-state.json` antes de iniciar qualquer execução. Os thresholds precisam existir e estar congelados em `docs/evidence/pose-thresholds-v054.json`. A ordem é: consistência, calibração histórica, MediaPipe QA-only, sanity/detectabilidade, e somente então o recheck A/C/R autorizado.

O estimador MediaPipe não é provider nem nó de geração. A documentação oficial do [Pose Landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker) e o [model card oficial](https://storage.googleapis.com/mediapipe-assets/Model%20Card%20BlazePose%20GHUM%203D.pdf) resolvem a licença para QA local; o arquivo `pose_landmarker_full.task` fica em `%LOCALAPPDATA%\UGAS\pose-qa` e não pode ser copiado para este repositório ou para o review ZIP.

O estado atual é `LOCAL_POSE_CONTROL_PROVIDER_GAP_CONFIRMED`. As nove saídas estão em `docs/evidence/v054-lanes/` para review técnico. Não execute walk, âncoras v3 ou provider alternativo a partir deste estado.
