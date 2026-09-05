# Regras do projeto

## Execucao integral de prompts

- Arquivos `.pdf` e `.md` fornecidos como prompts devem ser lidos integralmente antes da execucao.
- Distinguir sempre as instrucoes do documento do pedido direto do usuario.
- Executar toda a ordem, escopo, validacao, evidencia e gates autorizados pelo documento.
- Respeitar rigorosamente stop conditions, escopo proibido e regras de handoff.
- Validar objetivamente cada resultado e reportar blockers, estado externo e aprovacao somente quando houver evidencia verificavel.
- Nunca declarar conclusao, merge, deploy, aprovacao externa ou sucesso funcional com base apenas em evidencia parcial ou historica.
