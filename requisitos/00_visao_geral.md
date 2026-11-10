# MUPI — Museu Urbano de Percurso Interativo
## Requisitos do backend — Visão geral

Data: 10/11/2026
Meta: lançamento em **janeiro/2027**, precedido de um **beta com 10 usuários**.
Escopo inicial: **40 pontos MUPI em uma única cidade**, conteúdo apenas em português.
Cliente: app mobile em **Flutter** (repositório separado). Não haverá versão web do app.
Administração: painel web servido pelo próprio backend, usado por **3 administradores com o mesmo nível de acesso**.

---

## 1. O que é o produto

O usuário anda pela cidade guiado pelo aplicativo e visita pontos turísticos e históricos (pontos MUPI).
- Os pontos podem ser visitados **individualmente** ou dentro de **rotas** (sequência fixa de pontos ligados por um trajeto a pé).
- O conteúdo de cada ponto (blocos de texto, foto, áudio, vídeos do YouTube, informações de estabelecimento) só é liberado quando o usuário **está próximo e abre o ponto no app**.
- Abrir o ponto perto dele registra a **visita**. As visitas liberam **insígnias**, que ficam registradas para sempre no perfil do usuário.

## 2. Áreas do projeto (um arquivo por área)

| Arquivo | Área |
|---|---|
| `01_correcoes_e_falhas.md` | Falhas encontradas no código atual e dívidas técnicas |
| `02_usuarios_e_autenticacao.md` | Cadastro, login (e-mail e Google), recuperação de senha, perfil, exclusão de conta |
| `03_pontos_mupi_e_conteudo.md` | Pontos MUPI, temas, blocos de texto, foto, áudio, vídeos, dados de estabelecimento, mapa |
| `04_visitas.md` | Abertura do ponto, validação de proximidade, registro de visita, histórico |
| `05_rotas.md` | Cadastro de rotas, trajeto a pé, iniciar/encerrar rota, progresso, conclusão |
| `06_insignias.md` | Tipos de insígnia, regras de concessão, progresso, perfil |
| `07_painel_administrativo.md` | Login de admin, cadastro/edição/desativação/exclusão de tudo, estatísticas |
| `08_infraestrutura.md` | Banco, migrações, armazenamento de arquivos, hospedagem, segurança, testes, beta |

## 3. Decisões já tomadas (Etapa 2)

| Tema | Decisão |
|---|---|
| Blocos de texto | Vários por ponto; título livre (em negrito no app) + texto; ordem definida pelo admin |
| Leitura acessível | O texto deve poder ser ouvido (leitura em voz alta) |
| Foto | Uma por ponto, sem legenda/autor; visível no mapa mesmo de longe |
| Áudio | No máximo um por ponto, opcional (a maioria não terá), até ~10 min, tocado pelo usuário, sem transcrição |
| Vídeo | Apenas links do YouTube |
| Temas | Um ponto pode ter vários temas |
| Estabelecimento parceiro | Campos dentro do próprio ponto (endereço, horário, acessibilidade). No futuro, uma rota também poderá ser de um estabelecimento |
| Conteúdo | Só aparece quando o usuário está próximo e clica no ponto |
| Visita | Validada por localização + abertura do menu do ponto; não precisa interagir com as mídias |
| Distância máxima | Igual para todos os pontos; 50 m parece muito → valor configurável, ajustado no beta |
| Login | Obrigatório para usar o app |
| Offline | Não haverá no primeiro momento |
| Rotas | Ordem fixa; trajeto real a pé entre todos os pontos; nome, descrição, capa, distância, tempo, dificuldade, tema, classificação indicativa |
| Ponto em rotas | Pode estar em várias rotas; um campo define se ele também existe individualmente (se não, não aparece no mapa geral) |
| Rota ativa | Apenas uma por vez; não pode pausar; ao encerrar perde o progresso e precisa reiniciar |
| Avanço na rota | O usuário finaliza cada ponto em ordem; só finaliza o próximo após o anterior |
| Conclusão da rota | Todos os pontos finalizados → usuário encerra a rota → recebe a insígnia da rota |
| Visitas durante rota | Visitar pontos fora da rota vale normalmente |
| Insígnias | Coletadas automaticamente; ficam com o usuário mesmo que o ponto seja removido |
| Login social | Conta Google |
| Exclusão de conta | Permitida |
| Histórico | Só a lista de pontos visitados |
| Ranking / compartilhamento / notificações | Não, por enquanto |
| Rascunho de conteúdo | Não |
| Estatísticas no painel | Desejável |
| Hospedagem | AWS: Lightsail (API) + PostgreSQL gerenciado (Lightsail DB ou RDS) + S3 (arquivos), região São Paulo; e-mail continua no Resend |
| Equipe de desenvolvimento | Uma única desenvolvedora (backend e app) |

## 4. Classificação de prioridade usada nos arquivos

- **[MVP]** — obrigatório para o beta/lançamento de janeiro.
- **[DESEJÁVEL]** — entra em janeiro se houver tempo.
- **[FUTURO]** — registrado para não se perder, fora do escopo de janeiro.

## 5. Ordem sugerida de execução (≈ 8 semanas até janeiro)

1. **Semana 1** — Correções críticas (arquivo 01), migrações com Alembic, `requirements.txt`, conta AWS configurada (alertas de custo, bucket S3, banco) e camada de armazenamento (arquivo 08).
2. **Semana 2** — Login do painel admin + novo modelo de ponto (temas múltiplos, blocos de texto, foto única, áudio, vídeos, campos de estabelecimento).
3. **Semana 3** — Mapa, abertura do ponto com proximidade, registro de visita, novo fluxo de insígnias de ponto e de contagem.
4. **Semanas 4 e 5** — Rotas (cadastro, trajeto, iniciar/finalizar pontos/encerrar, insígnia de rota).
5. **Semana 6** — Login com Google, exclusão de conta, histórico, edição/exclusão completas no painel.
6. **Semana 7** — Hospedagem, testes, cadastro do conteúdo real, início do beta.
7. **Semana 8** — Ajustes do beta (inclusive a distância de proximidade) e estatísticas, se houver tempo.

## 6. Pendências ainda abertas

- Valor inicial da distância de proximidade (sugestão: 25 m, ajustar no beta).
- Data exata do beta.
