# UGAS — regras Codex (Windows)

## Python

- Use `python` ou `py -3.12` do sistema (`C:/Users/csn19/AppData/Local/Programs/Python/Python312/python.exe`).
- Não use `$py`, `.cache/codex-runtimes` nem Python bundled do Codex para scripts do repositório.
- Comandos de smoke test rodam em foreground e devem retornar saída imediata.

## Fluxo

- Não pausar após cada comando simples aguardando play manual.
- Continue a tarefa automaticamente até blocker real (erro, input obrigatório, ou fim do escopo).

## Protocolo de entrega de projeto existente

- Para Work Orders governados, leia `.engineering/ENGINEERING-DELIVERY-PROTOCOL.md` e o Work Order/Context Lock antes de editar.
- Inspecione o repositório, registre o baseline exato e execute somente o escopo aprovado.
- Se uma fonte crítica mudar, marque o Context Lock como `STALE`, registre o evento e relocke antes de continuar.
- Não remova código suspeito, dependências, contratos, migrations, jobs, flags ou evidência histórica sem um Work Order posterior e prova `VERIFIED_DEAD`.
- Execute as mesmas validações antes/depois, corrija apenas regressões introduzidas e produza Evidence Bundle e Checkpoint Delta proposto.
- Não promova sozinho `CHECKPOINT.md`/canonical truth, não faça self-merge e pare para revisão independente.
