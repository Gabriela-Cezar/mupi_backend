# 03 — Visitas (`VIS`)

Abrir o ponto estando perto entrega o conteúdo e registra a visita.

---

### VIS-01 — Abrir o ponto [Lançamento] ✅
- `POST /mupi-objects/{id}/open` com `{latitude, longitude, accuracy?}`.
- **Perto:** registra a visita (VIS-04), concede as insígnias (INS-02) e
  devolve o conteúdo completo, `new_visit`, `visits_total` e `awarded`.
- **Longe:** 403 "Aproxime-se do MUPI (você está a X m; o limite é Y m)".
- Ponto inexistente ou desativado: 404 "MUPI não encontrado."
- Com rota ativa que tem conteúdo próprio para o ponto, devolve o conteúdo
  da rota (ROT-12).
- Onde: `mupi_object_controller.py`, `proximity_service.py`.
- Testes: `test_mupi_content_access.py`, `test_proximidade.py`.

### VIS-02 — Regra de distância [Lançamento] ✅
- Pode abrir quem está a no máximo **distância máxima + tolerância**, em que a
  tolerância é a precisão informada pelo celular, limitada a um teto.
  Padrões: **25 m + até 15 m** (`VISIT_MAX_DISTANCE_M`, `VISIT_GPS_TOLERANCE_M`).
  Sem a precisão, vale só a distância máxima.
- `GET /app-settings` entrega os dois valores, para o app ligar o "Abrir" com
  a mesma regra.
- Onde: `proximity_service.py`, `app_settings_controller.py`.
- Testes: `test_proximidade.py`; app `app_settings_test.dart`, `app_settings_service_test.dart`.

### VIS-03 — Ponto só de rota [Lançamento] ✅
- Ponto que não existe solto só abre com a rota ativa que o contém; fora
  dela responde como ponto inexistente.
- Testes: `test_rota_ativa.py`.

### VIS-04 — Registro da visita [Lançamento] ✅
- **Uma visita por usuário e ponto**: abrir de novo entrega o conteúdo, mas
  não conta outra visita (`new_visit: false`). Duas aberturas ao mesmo tempo
  não duplicam.
- A visita guarda a data e a **posição e precisão** do celular na primeira
  abertura (para ajustar a distância no beta, VIS-07).
- Visitar pontos fora da rota ativa vale normalmente.
- Onde: `badge_service.py` (`register_visit`), `model/user_visit.py`.
- Testes: `test_visit_counts.py`, `test_migracao_posicao_da_visita.py`.

### VIS-05 — Abrir no app [Lançamento] 📱
- "Abrir" no cartão do ponto (ou no aviso de chegada) pede a posição atual,
  chama a abertura e mostra a tela do ponto. Longe ou sem GPS, mostra a
  mensagem; o ponto passa a aparecer como visitado no mapa.
- Insígnia ganha aparece numa janela de parabéns (INS-05).
- Onde: app `mupi_service.dart`, `map_view.dart`.
- Testes: app `mupi_service_test.dart`.

### VIS-06 — Histórico de visitas [Lançamento] ✅
- `GET /users/me/visits`: pontos visitados, do mais recente ao mais antigo,
  com nome, foto e data. Ponto desativado depois aparece como indisponível.
- **App:** lista "Pontos visitados" no perfil.
- Testes: `test_perfil_e_conta.py`; app `profile_view_test.dart`.

### VIS-07 — Ajustar a distância no beta [Lançamento] ⬜
- Com as posições e precisões guardadas nas visitas do beta, conferir se
  25 m + 15 m é justo (ninguém perto barrado, ninguém longe abrindo) e
  ajustar as variáveis no `.env` de produção.
