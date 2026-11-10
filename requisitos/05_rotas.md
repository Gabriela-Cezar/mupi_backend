# 05 — Rotas

Uma rota é uma sequência fixa de pontos MUPI ligados por um trajeto real a pé. Ao iniciar uma rota, o usuário vê todos os pontos ligados entre si no mapa e avança ponto a ponto, na ordem, até encerrar e receber a insígnia da rota.

Funcionalidade inteiramente nova.

---

## Cadastro (painel)

### ROT-01 — Dados da rota [MVP]
| Campo | Tipo | Obrigatório | Observação |
|---|---|---|---|
| nome | texto (até 150) | sim | único |
| descrição | texto | não | |
| imagem de capa | arquivo (PNG/JPEG/WebP, até 5 MB) | sim, para ativar | |
| pontos | lista ordenada | sim (mínimo 2) | ROT-02 |
| distância total | metros | automático | calculado pelo trajeto (ROT-03) |
| tempo estimado | minutos | automático, editável | o tempo de caminhada do OpenRouteService não inclui o tempo em cada ponto; o administrador pode ajustar |
| dificuldade | lista: fácil, média, difícil | sim | |
| temas | lista | não | uma rota pode ter vários temas (como o ponto) |
| classificação indicativa | lista: Livre, 10, 12, 14, 16, 18 anos | sim | segue as faixas do sistema brasileiro |
| ativa | sim/não | sim | rota inativa não aparece no app |

### ROT-02 — Pontos da rota [MVP]
- Tabela `route_points`: rota, ponto, posição.
- A ordem é fixa e definida pelo administrador (com reordenação no painel).
- O mesmo ponto pode estar em várias rotas, mas não duas vezes na mesma rota.
- A rota pode conter pontos que existem individualmente e pontos que só existem em rota (PT-09).
- Só pontos ativos podem ser adicionados. Se um ponto da rota for desativado, o painel deve avisar e a rota deve ser **desativada automaticamente** até ser corrigida (senão o usuário nunca conseguiria concluí-la).

### ROT-03 — Trajeto a pé entre os pontos [MVP]
- Ao salvar a rota (ou mudar a ordem/os pontos), o backend calcula o trajeto a pé completo, do primeiro ao último ponto, passando por todos, usando o OpenRouteService (perfil `foot-walking`, que já é usado).
- Guardar no banco: as coordenadas do trajeto, a distância total, o tempo de caminhada e, de preferência, o trecho de cada ponto até o próximo (para o app destacar o trecho atual).
- O trajeto é calculado uma vez e reutilizado por todos os usuários (economiza a cota do OpenRouteService e deixa o app rápido).
- Se o cálculo falhar, a rota é salva mas fica sem trajeto e **não pode ser ativada**; o painel mostra o erro e um botão "recalcular trajeto".
- O trajeto do usuário até o **primeiro ponto** (ou até o próximo ponto) continua sendo calculado na hora, pela rota já existente (PT-12).

## Uso no app

### ROT-04 — Listar e ver rotas [MVP]
- `GET /routes` — rotas ativas: id, nome, capa, distância, tempo, dificuldade, temas, classificação indicativa, quantidade de pontos, se o usuário já concluiu.
- `GET /routes/{id}` — dados completos + lista ordenada dos pontos (resumo como no mapa: id, nome, posição, foto) + trajeto completo.
- A lista de pontos e o trajeto podem ser vistos antes de iniciar, mas o **conteúdo** de cada ponto continua liberado só pela abertura com proximidade.

### ROT-05 — Iniciar rota [MVP]
- `POST /routes/{id}/start`.
- O usuário só pode ter **uma rota ativa por vez**. Se já houver outra ativa, responder 409 informando qual é; o app pergunta se deseja encerrar a atual (perdendo o progresso) e iniciar a nova.
- Iniciar cria um registro de progresso: usuário, rota, iniciada em, índice do próximo ponto (começa no primeiro).
- Tabela `user_active_routes` (no máximo uma por usuário — chave única no usuário).
- Iniciar uma rota já concluída anteriormente é permitido (o usuário pode refazer).

### ROT-06 — Ver rota ativa [MVP]
- `GET /users/me/active-route` (e também dentro de `GET /users/me`).
- Devolve: rota, pontos em ordem com o estado de cada um (finalizado / atual / pendente), trajeto completo, trecho atual.

### ROT-07 — Finalizar um ponto da rota [MVP]
- `POST /users/me/active-route/points/{object_id}/finish` com a posição do usuário.
- Regras:
  1. o ponto deve ser **o próximo da sequência** (não pode pular nem finalizar fora de ordem) — senão 409;
  2. o usuário deve ter **aberto o ponto** com proximidade (VIS-01) — a visita precisa existir. Se o usuário já visitou o ponto antes (em outro dia ou outra rota), basta abri-lo de novo agora, perto do ponto;
  3. conferir a proximidade também no momento de finalizar (mesma distância de VIS-02).
- Ao finalizar, o índice avança para o próximo ponto.
- **Impacto no app:** dentro do menu do ponto, quando há rota ativa e o ponto é o atual, aparece o botão "Finalizar ponto e ir para o próximo".

### ROT-08 — Encerrar a rota concluída [MVP]
- `POST /users/me/active-route/complete`.
- Só é aceito quando **todos os pontos** foram finalizados.
- Registra a conclusão em `user_route_completions` (usuário, rota, concluída em) — guarda todas as conclusões, inclusive repetidas.
- Concede a insígnia da rota, se houver e se o usuário ainda não a tiver (ver INS-04).
- Remove o progresso ativo.
- Devolve as insígnias ganhas.

### ROT-09 — Abandonar a rota [MVP]
- `DELETE /users/me/active-route`.
- Apaga o progresso. Não existe pausa: para fazer a rota de novo, o usuário reinicia do primeiro ponto.
- As **visitas** feitas durante a rota **continuam valendo** para as insígnias de ponto e de contagem.

### ROT-10 — Rota alterada durante o uso [MVP]
- Se o administrador alterar os pontos/ordem ou desativar uma rota que algum usuário está fazendo, o progresso desses usuários é encerrado (como se abandonassem). O app mostra a mensagem "Esta rota foi atualizada; inicie novamente".
- Alterações que não mexem nos pontos (nome, descrição, capa) não afetam o progresso.

## Futuro

### ROT-11 — Rota de estabelecimento parceiro [FUTURO]
- Uma rota poderá pertencer a um estabelecimento parceiro (ver PT-08, futuro).

### ROT-12 — Filtros de rota [FUTURO]
- Filtrar a lista por tema, dificuldade, duração e classificação indicativa (com 40 pontos, a lista inicial será pequena).
