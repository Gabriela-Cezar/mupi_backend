# MUPI — Museu Urbano de Percurso Interativo
## Requisitos — Visão geral

Versão: 17/11/2026, escrita a partir do código (backend na migração `0017`,
1031 testes; app com 451 testes). Substitui os requisitos de 10/11/2026,
que continuam no histórico do git.

Os mesmos arquivos ficam em `mupi_backend/requisitos` e
`mupi_application/requisitos` e devem continuar idênticos (conferir com `cmp`).

---

## 1. O produto

O usuário anda pela cidade guiado pelo app e visita **pontos MUPI** (lugares
turísticos e históricos).

- O conteúdo de cada ponto (blocos de texto, foto, áudio, vídeos do YouTube,
  informações do local) só é entregue quando o usuário **está perto e abre o
  ponto**. Abrir o ponto perto registra a **visita**.
- Os pontos podem ser visitados soltos ou dentro de **rotas**: sequência fixa
  de pontos ligados por um trajeto a pé. Dentro de uma rota, um ponto pode
  mostrar um **conteúdo próprio da rota**.
- Visitas e rotas concluídas rendem **insígnias**, que ficam para sempre no
  perfil.
- O conteúdo é cadastrado por **administradores** num painel web servido pelo
  próprio backend.

Metas: **beta com 10 usuários** e lançamento em **janeiro de 2027**; cerca de
**40 pontos em uma cidade**; conteúdo só em português; **3 administradores**
com o mesmo nível de acesso.

## 2. Decisões de produto

| Tema | Decisão |
|---|---|
| Login | Obrigatório para usar o app. E-mail e senha ou conta Google |
| Sessão no app | 30 dias, renovada a cada abertura |
| Conteúdo | Só aparece quando o usuário está perto e abre o ponto |
| Visita | Vale a abertura perto do ponto; não precisa ver as mídias. Uma visita por ponto por usuário |
| Distância | Igual para todos os pontos, configurável (padrão 25 m + até 15 m de tolerância ao GPS), a ajustar no beta |
| Blocos de texto | Vários por ponto: título (em negrito) + texto, na ordem do administrador |
| Foto | Uma por ponto, visível no mapa mesmo de longe |
| Áudio | No máximo um por ponto, opcional, até cerca de 10 min |
| Vídeo | Só links do YouTube, tocados dentro do app |
| Leitura em voz alta | O texto do ponto pode ser ouvido |
| Temas | Um ponto pode ter vários temas; uma rota também |
| Estabelecimento parceiro | Endereço, horário e acessibilidade no próprio ponto |
| Ponto só de rota | Não aparece no mapa nem na busca; abre só com a rota ativa que o contém |
| Rotas | Ordem fixa, trajeto real a pé, uma rota ativa por vez, sem pausa; abandonar perde o progresso |
| Conteúdo na rota | O ponto pode ter outro conteúdo (até nome e foto) dentro de cada rota; vale só com aquela rota ativa |
| Insígnias | Concedidas sozinhas; ficam com o usuário mesmo se o ponto ou a rota sair do ar |
| Histórico | Lista dos pontos visitados |
| Exclusão de conta | Permitida, pelo próprio app |
| Offline, ranking, compartilhamento, notificações, outros idiomas | Não no lançamento |

## 3. Arquitetura

| Parte | Tecnologia | Onde |
|---|---|---|
| API e painel | Python, FastAPI, SQLAlchemy, Alembic, Jinja2 | `mupi_backend` |
| Banco | PostgreSQL (SQLite nos testes) | — |
| Arquivos | Amazon S3 privado, com links assinados; pasta local no desenvolvimento | — |
| E-mail | Resend | — |
| Trajeto a pé | OpenRouteService (`foot-walking`) | — |
| Login Google | `google-auth` (backend), `google_sign_in` (app) | — |
| App | Flutter (Android e iOS; roda no Chrome para testes) | `mupi_application` |
| Mapa no app | `flutter_map` com OpenStreetMap | — |
| Hospedagem prevista | AWS: Lightsail (API) + banco gerenciado + S3, região São Paulo | `infra/` |

## 4. Arquivos

| Arquivo | Assunto | Prefixo |
|---|---|---|
| `01_contas_e_acesso.md` | Cadastro, login, Google, sessão, senha, exclusão | `CON` |
| `02_pontos_e_conteudo.md` | Pontos, temas, conteúdo, mapa, busca, "Como chegar", tela do ponto | `PON` |
| `03_visitas.md` | Abertura do ponto, proximidade, visita, histórico | `VIS` |
| `04_rotas.md` | Rotas, trajeto, rota ativa, conteúdo do ponto na rota | `ROT` |
| `05_insignias_e_perfil.md` | Insígnias, concessão, perfil | `INS` |
| `06_painel_administrativo.md` | Painel web dos administradores | `ADM` |
| `07_infraestrutura_e_qualidade.md` | Configuração, arquivos, segurança, backups, testes, acessibilidade | `INF` |
| `08_publicacao.md` | Produção, identidade do app, lojas, beta | `PUB` |
| `09_plano.md` | O que falta, em ordem | — |
| `10_api_do_app.md` | Referência das rotas da API usadas pelo app | — |

## 5. Como ler cada requisito

```
### PON-03 — Título [Prioridade] Status
- Comportamento esperado (o que o sistema faz ou deve fazer)
- Onde: arquivos principais
- Testes: arquivos de teste
```

**Prioridade:** `[Lançamento]` necessário para o beta e o lançamento;
`[Desejável]` melhora o produto, mas não bloqueia; `[Futuro]` fora do lançamento.

**Status:**
- ✅ **Feito**: implementado e coberto por testes automáticos;
- 📱 **Feito, a conferir**: implementado e testado, mas ainda não conferido
  num celular de verdade (GPS, áudio, câmera, permissões, leitor de tela);
- 🟡 **Parcial**: parte feita; o que falta está descrito;
- ⬜ **Pendente**: ainda não feito;
- 💡 **Futuro**: ideia registrada, fora do lançamento.

## 6. Regras de trabalho

- **Testes junto com cada mudança:** `pytest` no backend e `flutter test` no
  app; `flutter analyze` sem problemas.
- **Mensagens ao usuário em português**, prontas para mostrar.
- **Configuração só pelo `.env`** (backend: lida apenas em `app/core/config.py`)
  e por `--dart-define` (app).
- **Toda mudança de banco por migração do Alembic**, testada para subir e descer.
- **Mudança numa rota da API:** atualizar `10_api_do_app.md` e dizer se o
  app precisa mudar.
- **Estes arquivos e o plano ficam idênticos nos dois repositórios.**
