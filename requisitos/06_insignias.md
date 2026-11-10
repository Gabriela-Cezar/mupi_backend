# 06 — Insígnias

Insígnias são conquistas liberadas pelo uso do app. São **coletadas automaticamente** e ficam registradas **para sempre** no perfil do usuário, mesmo que o ponto, a rota ou a própria insígnia sejam desativados depois.

---

### INS-01 — Tipos de insígnia [MVP]
| Tipo | Regra | Ligada a |
|---|---|---|
| **Visita a ponto** | visitar um ponto específico | exatamente **um** ponto |
| **Quantidade geral** | visitar N pontos quaisquer | — (N ≥ 1) |
| **Quantidade por tema** | visitar N pontos quaisquer de um tema (ex.: "Visitar 5 pontos Arte Deco" — quaisquer 5 dos 40) | um tema (N ≥ 1) |
| **Conclusão de rota** | encerrar uma rota com todos os pontos finalizados | exatamente **uma** rota |

- Campos comuns (já existem): nome (único), descrição, imagem (PNG/JPEG/WebP até 5 MB).
- Acrescentar: `ativa` (sim/não) e `route_id` (para conclusão de rota).
- O tipo atual `manual` passa a se chamar **visita a ponto** (`point_visit`).
- Hoje a ligação insígnia ↔ ponto é muitos-para-muitos (`mupi_object_badges`). Como a insígnia de ponto é de **um único ponto**, trocar por uma coluna `object_id` na insígnia. Um ponto pode ter mais de uma insígnia, se o administrador quiser.
- Atualizar a regra de consistência do banco (`ck_badges_rule_consistency`) para os quatro tipos.

### INS-02 — Insígnia de visita a ponto [MVP]
- Concedida automaticamente na primeira abertura do ponto com proximidade (VIS-01).
- Se o usuário visitou o ponto **antes** de a insígnia ser criada, ele a recebe na próxima vez que abrir o ponto ou ao carregar o perfil (INS-06).
- A coleta manual atual (`POST /users/me/badges`, "tocar na insígnia") deixa de existir.

### INS-03 — Insígnias de quantidade (geral e por tema) [MVP]
- Avaliadas a cada nova visita.
- Quantidade geral: total de pontos distintos visitados pelo usuário.
- Por tema: total de pontos distintos visitados que têm aquele tema. Como um ponto pode ter vários temas, **uma visita conta para todos os temas do ponto**.
- Pontos que só existem em rotas contam normalmente.

### INS-04 — Insígnia de conclusão de rota [MVP]
- Concedida ao encerrar a rota (ROT-08).
- Concedida uma única vez, mesmo que o usuário refaça a rota.
- Uma rota tem no máximo uma insígnia de conclusão (recomendado; simplifica o painel).

### INS-05 — Contagem não diminui [MVP]
- As contagens consideram **todas as visitas registradas**, inclusive em pontos hoje inativos (corrige FAL-12).
- Se o administrador remover um tema de um ponto, a contagem do tema diminui para o progresso futuro, mas insígnias já ganhas permanecem.

### INS-06 — Avaliação retroativa [MVP]
- Quando o administrador cria uma nova insígnia de quantidade (ex.: "Visitar 3 pontos") e um usuário já cumpre a condição, ele deve recebê-la sem precisar de nova visita.
- Implementação: avaliar as insígnias pendentes também ao carregar `GET /users/me`.
- Mesma lógica para insígnia de visita a ponto criada depois da visita e para insígnia de rota criada depois da conclusão (usando `user_route_completions`).

### INS-07 — Registro da conquista [MVP]
- Tabela `user_badges` (já existe): usuário, insígnia, data, ponto onde foi conquistada.
- Acrescentar a rota onde foi conquistada (para insígnias de rota).
- Ao excluir a conta, as conquistas do usuário são apagadas (USR-08).
- Ao desativar insígnia/ponto/rota, as conquistas permanecem (FAL-11).

### INS-08 — Exibição no perfil [MVP]
- `GET /users/me` devolve:
  - **conquistadas:** nome, descrição, imagem, tipo, data, onde foi conquistada;
  - **em progresso:** insígnias de quantidade ainda não ganhas, com progresso (ex.: 3 de 5);
  - **total possível:** insígnias ativas que ainda podem ser conquistadas.
- Insígnias desativadas aparecem apenas para quem já as conquistou.
- Insígnias de visita a ponto e de rota ainda não ganhas: **sugestão** — mostrar como "bloqueadas" (silhueta) sem revelar qual ponto/rota, para manter a surpresa. Confirmar com a equipe do app.

### INS-09 — Retorno imediato ao ganhar [MVP]
- Abertura de ponto (VIS-01) e encerramento de rota (ROT-08) devolvem a lista de insígnias ganhas naquela ação, para o app exibir uma animação/aviso.

### INS-10 — Ranking, compartilhamento e notificações [FUTURO]
- Não fazem parte do lançamento.
