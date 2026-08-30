# 2D master pipeline v0.5.3

O v0.5.3 executa a calibração da medição de pose com estado consistente e fail-closed. O R4 aprovado como anchor de pipeline é imutável; nenhuma lane de provider, âncora ou walk é promovida sem métrica calibrada e estimador QA independente qualificado.

1. `identity-manifest.json` fixa hash, dimensões, alpha bbox, palette, armor, tecido, pele, cabeça, espada, proporções, pivot e transformações permitidas.
2. `pose-guides/` contém JSONs de vista, mannequin preenchido v2, challenge A/B e o conjunto walk/front/8; Pillow os renderiza sem IA. A imagem de controle enviada ao modelo não tem texto ou labels; overlays são somente para review.
3. A calibração exige target >=0.90, negativos pelo menos 0.20 abaixo do target, PCK@0.10 >=0.80, NME <=0.10, erro angular <=18 graus, lower-body PCK >=0.75, orientação correta e invariância à espada. A antiga métrica de silhueta/keypoint é apenas diagnóstica.
4. O estimador MediaPipe é somente QA e mapeia landmarks para joints UGAS; nenhum bundle ou dependência de QA é inserido no grafo de geração.
3. O workflow nativo encadeia duas referências: `reference[0]` controla identidade/material/style; `reference[1]` controla pose/view.
4. Cada job grava seed, workflow/model hashes, hashes das referências, prompt ID, history, output e fresh binding.
5. Saídas geradas são removidas por BiRefNet, normalizadas sem stretch para baseline/pivot compartilhados, e somente então submetidas a QA.
6. O walk é aceito como conjunto de oito ou rejeitado integralmente; não existe ciclo parcial publicado.

A revisão visual humana continua separada de todos os gates técnicos.
