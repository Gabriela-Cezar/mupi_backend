# 05 — Insígnias e perfil (`INS`)

---

### INS-01 — Tipos de insígnia [Lançamento] ✅
| Tipo | Condição | Configuração |
|---|---|---|
| Visita a ponto (`point_visit`) | Visitar um ponto | O ponto |
| Quantidade geral (`visit_count`) | Visitar N pontos | N (1 a 1000) |
| Quantidade por tema (`theme_visit_count`) | Visitar N pontos de um tema | O tema e N |
| Conclusão de rota (`route_completion`) | Concluir uma rota | A rota (uma insígnia por rota) |

- Cada insígnia tem nome único (sem diferenciar maiúsculas), descrição e
  imagem opcionais e pode ser desativada.
- O banco garante que cada tipo tenha só os campos dele.
- Onde: `model/badge.py`, `badge_form.py`.
- Testes: `test_insignias.py`, `test_insignia_de_rota.py`, `test_migracao_tipos_de_insignia.py`.

### INS-02 — Concessão automática [Lançamento] ✅
- Visita e quantidade: ao abrir um ponto (nova visita). Conclusão de rota: ao
  concluir a rota. A resposta traz as insígnias ganhas (`awarded`), com onde
  foram conquistadas (ponto ou rota).
- **Retroativa:** insígnia criada depois que o usuário já cumpria a condição
  é concedida na próxima vez que ele vê o perfil.
- Uma vez por usuário; refazer a rota não concede de novo.
- Insígnia **desativada** não é concedida nem conta no total; quem já tinha
  continua com ela.
- Onde: `badge_service.py`.
- Testes: `test_insignias.py`, `test_insignia_de_rota.py`.

### INS-03 — Regras protegidas [Lançamento] ✅
- Insígnia já conquistada não muda de regra (tipo, ponto, tema, quantidade,
  rota) nem pode ser excluída; o painel oferece desativar.
- Ponto ligado a uma insígnia e tema usado por insígnia não podem ser excluídos.
- Testes: `test_admin_insignias.py`.

### INS-04 — Perfil [Lançamento] ✅
- `GET /users/me`: e-mail, data de cadastro, total de visitas, insígnias
  conquistadas (com data e onde), **em progresso** (quantidade: progresso e
  meta), **bloqueadas** (visita a ponto e conclusão de rota: só o tipo, sem
  revelar o ponto ou a rota), total de insígnias, rota ativa, se tem senha e
  se está ligada ao Google.
- **App:** tela "Meu perfil" com o resumo, "Insígnias conquistadas" (toque
  mostra o detalhe), "Em progresso" (barras), "Para descobrir" (bloqueadas),
  "Pontos visitados", "Sair" e "Excluir minha conta". Atualiza ao voltar a ela.
- Onde: `user_controller.py`; app `profile_view.dart`, `badge_image.dart`.
- Testes: `test_perfil_e_conta.py`; app `profile_view_test.dart`, `user_profile_test.dart`.

### INS-05 — Aviso de conquista [Lançamento] ✅
- **App:** janela de parabéns com a imagem e o nome das insígnias ganhas, ao
  abrir um ponto e na tela de conclusão da rota.
- Onde: app `award_dialog.dart`.
- Testes: app `award_dialog_test.dart`.

### INS-06 — Ranking, compartilhamento e notificações [Futuro] 💡
