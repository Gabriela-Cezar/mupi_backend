# 04 — Visitas

A visita é o registro de que o usuário esteve em um ponto MUPI. Ela é a base de tudo: libera o conteúdo, alimenta as insígnias e o avanço nas rotas.

**Regra principal:** uma visita é registrada quando o usuário, **estando próximo** do ponto, **clica no ponto e abre o menu dele** no app. Não é preciso interagir com as mídias.

---

### VIS-01 — Abrir um ponto [MVP]
- Nova rota `POST /mupi-objects/{id}/open` (exige login).
- Corpo: latitude, longitude e precisão do GPS (em metros, informada pelo Flutter).
- O servidor:
  1. confere se o ponto existe e está ativo (senão, 404);
  2. se o ponto **não** existe individualmente, confere se a rota ativa do usuário contém o ponto (senão, 404 — o ponto "não existe" para ele);
  3. calcula a distância até o ponto e compara com a distância máxima (VIS-02); se estiver longe, responde 403 com a distância atual e a distância máxima;
  4. registra a visita, se for a primeira desse usuário nesse ponto (VIS-03);
  5. avalia e concede as insígnias (ver `06_insignias.md`);
  6. devolve o conteúdo completo do ponto (PT-13), se a visita é nova, as insígnias ganhas agora e o total de visitas.
- Abrir o mesmo ponto de novo, estando perto, devolve o conteúdo normalmente (sem nova visita).
- Substitui a rota atual `POST /users/me/visits` e a coleta manual `POST /users/me/badges` (ver INS-02).
- **Impacto no app:** ao tocar no ponto no mapa, o app envia a posição atual. Se o usuário estiver longe, mostra a mensagem "Aproxime-se do ponto (você está a X m)" e, opcionalmente, o botão de rota a pé até ele.

### VIS-02 — Distância máxima [MVP]
- Valor único para todos os pontos, definido em configuração (`.env`), sem precisar alterar o código.
- **Valor inicial sugerido:** 25 m (50 m foi considerado muito). Ajustar durante o beta.
- Tolerância ao erro do GPS: somar a precisão informada pelo celular até um limite (ex.: distância máxima + mínimo entre a precisão e 15 m). Assim um GPS com erro de 10 m não impede quem está realmente no local.
- **[DESEJÁVEL]** permitir alterar o valor pelo painel, sem reiniciar o servidor.

### VIS-03 — Registro da visita [MVP]
- Tabela `user_visits` (já existe): uma linha por usuário e ponto, com a data da primeira visita.
- Acrescentar: latitude, longitude e precisão no momento da visita (para análise de fraude e ajuste da distância — FAL-21).
- Visitas não são apagadas quando o ponto é desativado (FAL-11, FAL-12).
- Visitar um ponto fora da rota ativa vale normalmente.

### VIS-04 — Histórico de pontos visitados [MVP]
- Nova rota `GET /users/me/visits`.
- Devolve apenas a lista dos pontos visitados: id, nome, foto (miniatura). Ordenação sugerida: visita mais recente primeiro.
- Inclui pontos hoje inativos? **Sugestão:** sim, marcados como indisponíveis, para o histórico não "sumir".
- No mapa (PT-10), cada ponto indica se o usuário já o visitou.

### VIS-05 — Concorrência [MVP]
- Duas aberturas simultâneas do mesmo ponto não podem gerar duas visitas nem insígnias duplicadas (o código atual já trata isso com a chave primária; manter e testar).
