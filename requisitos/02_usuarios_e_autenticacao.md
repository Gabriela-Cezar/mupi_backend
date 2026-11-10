# 02 — Usuários e autenticação

Usuários do aplicativo (não inclui administradores; ver `07_painel_administrativo.md`).
O login é **obrigatório** para usar o app: todas as rotas usadas pelo app, exceto as de `/auth`, exigem token.

---

## O que já existe e se mantém

- Cadastro por e-mail e senha, com código de 6 dígitos enviado por e-mail (válido 10 min, 5 tentativas).
- Usuário só é criado depois de confirmar o código.
- Login devolve token JWT válido por 7 dias.
- Recuperação de senha: código por e-mail → `reset_token` de 10 min → nova senha.
- Trocar a senha invalida os tokens antigos.

## Requisitos

### USR-01 — Cadastro por e-mail [MVP]
- Manter o fluxo atual `POST /auth/register` → `POST /auth/verify-email`.
- Senha: mínimo 8, máximo 128 caracteres.
- Se o e-mail já tiver conta criada pelo Google, responder "E-mail já cadastrado" (o usuário entra com o Google).
- Intervalo mínimo de 60 s entre envios para o mesmo e-mail (FAL-07).

### USR-02 — Reenvio do código de verificação [MVP]
- Corrigir `POST /auth/resend-verification` (FAL-01).

### USR-03 — Login por e-mail e senha [MVP]
- Manter `POST /auth/login`.
- Limite de tentativas por e-mail e IP (FAL-08).
- Usuário sem senha (conta só Google) que tentar entrar por senha recebe a mesma mensagem genérica de "E-mail ou senha inválidos".

### USR-04 — Login com Google [MVP]
- Nova rota `POST /auth/google` recebendo o `id_token` obtido pelo app Flutter (pacote `google_sign_in`).
- O backend valida o token com a biblioteca oficial do Google, conferindo assinatura, validade, emissor e se o `aud` é um dos Client IDs do projeto (Android, iOS e o Client ID "web" usado pelo Flutter). Os Client IDs ficam no `.env`.
- Só aceitar se `email_verified` for verdadeiro no token.
- Regras de vínculo:
  1. Já existe usuário com esse `google_sub` → login.
  2. Não existe `google_sub`, mas existe usuário com o mesmo e-mail → vincular o `google_sub` a essa conta e fazer login (o e-mail foi confirmado pelo Google).
  3. Não existe → criar usuário com `email_verified = true` e sem senha.
- Resposta igual à do login por senha (token, `user_id`, e-mail).
- **Mudanças no modelo:** `users.google_sub` (texto, único, opcional); `users.password_hash` passa a aceitar nulo.
- **Pré-requisito externo:** criar o projeto no Google Cloud Console e as credenciais OAuth para Android (com o SHA-1 do app) e iOS.

### USR-05 — Invalidação de sessão sem depender da senha [MVP]
- Hoje o token carrega uma "impressão digital" do hash da senha. Contas só Google não têm senha.
- Substituir por um campo `users.token_version` (inteiro). O token carrega a versão; o servidor rejeita tokens com versão diferente.
- Incrementar `token_version` ao trocar a senha, ao redefinir a senha e ao excluir a conta.
- O `reset_token` de recuperação continua de uso único (pode usar a mesma versão).

### USR-06 — Recuperação de senha [MVP]
- Manter o fluxo atual.
- Se a conta for só Google (sem senha), a recuperação permite **criar** uma senha; depois disso o usuário pode entrar das duas formas.
- Intervalo mínimo de 60 s entre envios (FAL-07).

### USR-07 — Perfil [MVP]
- `GET /users/me` continua devolvendo e-mail, data de cadastro, insígnias conquistadas, insígnias em progresso, total de visitas e a rota ativa, se houver (ver `05_rotas.md`).
- Não haverá nome, apelido ou foto de perfil por enquanto.

### USR-08 — Exclusão de conta [MVP]
- Nova rota `DELETE /users/me`.
- Conta com senha: exigir a senha atual no corpo da requisição. Conta só Google: exigir um `id_token` recente do Google.
- Apagar definitivamente: usuário, visitas, insígnias conquistadas, progresso de rota ativa, conclusões de rota e códigos pendentes.
- Após a exclusão, todos os tokens deixam de valer.
- Estatísticas do painel passam a não contar esse usuário (aceitável).
- **Impacto no app:** tela de confirmação com aviso de que a ação não pode ser desfeita.
- **Observação:** a Google Play e a App Store exigem que o app ofereça exclusão de conta quando há cadastro.

### USR-09 — Códigos guardados no banco [MVP]
- Nova tabela `email_codes`: e-mail, finalidade (`verificacao` ou `recuperacao`), hash do código, hash da senha pendente (só no cadastro), expira em, tentativas, enviado em.
- O código não é guardado em texto puro (guardar hash).
- Mantém as regras atuais: 6 dígitos, 10 min, 5 tentativas, uso único, 60 s entre envios.
- Códigos expirados podem ser apagados periodicamente ou na próxima solicitação do mesmo e-mail.

### USR-10 — Todas as rotas do app exigem login [MVP]
- Mapa, abertura de ponto, rotas, insígnias, perfil e arquivos de conteúdo exigem token válido.
- Exceção: rotas de `/auth`.
- Arquivos (foto/áudio) são servidos por link assinado do S3, que só é entregue a usuários logados (ver `08_infraestrutura.md`, INF-04).

### USR-11 — Renovação do token [DESEJÁVEL]
- Hoje o token dura 7 dias e depois o usuário precisa entrar de novo.
- Avaliar uma rota `POST /auth/refresh` para renovar o token enquanto o usuário usa o app, evitando novo login a cada semana.

### USR-12 — Outros provedores de login [FUTURO]
- Login com Apple. Atenção: a App Store costuma exigir "Entrar com a Apple" quando o app oferece login com Google. Verificar antes da publicação no iOS.
