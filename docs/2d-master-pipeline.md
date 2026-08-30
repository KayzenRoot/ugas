# 2D master pipeline v0.5.0

O v0.5 acrescenta um piloto fechado de identidade + pose/view. O R4 aprovado como anchor de pipeline é imutável; não é regenerado para a direção front/down.

1. `identity-manifest.json` fixa hash, dimensões, alpha bbox, palette, armor, tecido, pele, cabeça, espada, proporções, pivot e transformações permitidas.
2. `pose-guides/` contém JSONs de vista e o conjunto walk/front/8; Pillow os renderiza sem IA.
3. O workflow nativo encadeia duas referências: `reference[0]` controla identidade/material/style; `reference[1]` controla pose/view.
4. Cada job grava seed, workflow/model hashes, hashes das referências, prompt ID, history, output e fresh binding.
5. Saídas geradas são removidas por BiRefNet, normalizadas sem stretch para baseline/pivot compartilhados, e somente então submetidas a QA.
6. O walk é aceito como conjunto de oito ou rejeitado integralmente; não existe ciclo parcial publicado.

A revisão visual humana continua separada de todos os gates técnicos.
