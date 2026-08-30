# UGAS 0.5.1

Universal Game Asset Studio: pipeline local-first para assets 2D com ComfyUI nativo, evidência reproduzível, transparência e governança de revisão.

O slice atual corrige a reprodutibilidade e a fidelidade do piloto experimental de multi-reference FLUX.2 Klein: `reference[0]` é a identidade canônica R4 e `reference[1]` é um mannequin determinístico de pose/vista. A qualificação A/B v2 só passa com ganho causal de pose sobre o baseline A; se isso falhar, o estado é `MULTI_REFERENCE_POSE_CONTROL_GAP` e o walk não é fabricado.

O escopo deliberadamente não inclui animação genérica, todas as direções, idle/run/attack/hit/death, 3D, áudio, integração de engine, DWPose/OpenPose/ControlNet/custom nodes, cloud ou provedores pagos.

## Quick start

```powershell
$env:PYTHONPATH = "src"
python -m ugas.cli pose-guides validate --json
python -m ugas.cli identity inspect asset-2fec6fed1d714d0cb58ad75b56d7ba71 --json
python -m ugas.cli multiref qualify --json
python -m ugas.cli anchors generate asset-2fec6fed1d714d0cb58ad75b56d7ba71 --directions front left right back --json
python -m ugas.cli animation generate asset-2fec6fed1d714d0cb58ad75b56d7ba71 --animation walk --view front --frames 8 --json
```

Todos os comandos experimentais falham com código não zero quando o gate correspondente não passa. Pesos, caches e jobs ficam fora do Git; o resultado visual permanece sujeito a revisão humana.

Consulte [INSTALL.md](INSTALL.md), [docs/2d-master-pipeline.md](docs/2d-master-pipeline.md), [docs/comfyui.md](docs/comfyui.md), [CHECKPOINT.md](CHECKPOINT.md), [REVIEW-v0.5.1.md](REVIEW-v0.5.1.md) e [docs/test-coverage-matrix-v0.5.1.md](docs/test-coverage-matrix-v0.5.1.md). Os documentos `REVIEW-v0.5.0.md`, `REVIEW-v0.4.2.md` e `REVIEW-v0.4.3.md` são históricos e permanecem imutáveis.
