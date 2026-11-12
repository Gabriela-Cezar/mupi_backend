# 07 — Painel administrativo

Painel web servido pelo próprio backend (templates HTML/Jinja2, como hoje). Usado por **3 administradores com o mesmo nível de acesso**. Não há rascunho: o que é salvo como ativo aparece no app.

---

## Acesso

### ADM-01 — Login de administrador [MVP — crítico]
- Todas as páginas e rotas `/admin/*` exigem login (corrige FAL-04).
- Administradores ficam em tabela própria (`admins`: e-mail, hash da senha, ativo), separada dos usuários do app.
- Login por e-mail e senha em uma página `/admin/login`; sessão por cookie seguro (`HttpOnly`, `Secure`, `SameSite=Lax`), com validade de 12 horas.
- Proteção contra envio de formulário por outro site (token CSRF em todos os formulários).
- Limite de tentativas de login (como FAL-08).
- Botão "Sair".
- Os 3 administradores iniciais são criados por um comando de terminal (ex.: `python -m app.scripts.create_admin`), não por tela pública.

### ADM-02 — Recuperar senha de administrador [DESEJÁVEL]
- Pelo mesmo fluxo de código por e-mail, ou um administrador redefine a senha de outro.

### ADM-03 — Níveis de acesso [FUTURO]
- Por enquanto todos têm o mesmo acesso.

## Cadastros

Para cada item: **listar, criar, editar, desativar/reativar e excluir**. Toda lista deve ter busca por nome.

### ADM-04 — Pontos MUPI [MVP]
- Formulário com todos os campos de PT-01:
  - nome, latitude/longitude (**[DESEJÁVEL]** escolher no mapa clicando, em vez de digitar), ativo, existe individualmente;
  - temas (seleção múltipla);
  - blocos de texto: adicionar, editar, remover, reordenar (título livre + texto);
  - foto (enviar/substituir, com pré-visualização);
  - áudio (enviar/substituir/remover, com player para conferir);
  - vídeos do YouTube (adicionar/remover/reordenar, título opcional; validação do link);
  - endereço, horário de funcionamento, acessibilidade;
  - insígnias de visita ligadas ao ponto (atalho para criar).
- Lista: nome, ativo, existe individualmente, temas, se tem foto/áudio, quantidade de rotas em que aparece, quantidade de visitas.

### ADM-05 — Temas [MVP]
- Nome e descrição. Hoje só existem listar e criar (sem tela).

### ADM-06 — Insígnias [MVP]
- Formulário que muda conforme o tipo (corrige FAL-03):
  - visita a ponto → escolher o ponto;
  - quantidade geral → N;
  - quantidade por tema → tema + N;
  - conclusão de rota → escolher a rota.
- Imagem com pré-visualização, nome, descrição, ativa.
- Lista: nome, tipo, condição resumida ("5 pontos de Arte Deco"), quantos usuários já conquistaram.

### ADM-07 — Rotas [MVP]
- Todos os campos de ROT-01.
- Seleção e reordenação dos pontos (arrastar para ordenar).
- Pré-visualização do trajeto no mapa após o cálculo, com distância e tempo.
- Botão "recalcular trajeto" e aviso de erro do cálculo (ROT-03).
- Aviso quando a alteração encerrará o progresso de usuários que estão fazendo a rota (ROT-10).

### ADM-08 — Desativar [MVP]
- Desativar esconde o item do app sem apagar histórico.
- Ponto desativado: some do mapa; rotas que o contêm são desativadas automaticamente com aviso (ROT-02).
- Insígnia desativada: deixa de ser concedida; quem já tem continua tendo.
- Rota desativada: some da lista; progresso ativo é encerrado.

### ADM-09 — Excluir [MVP]
- Para cumprir "a insígnia continua com o usuário" (corrige FAL-11):
  - **ponto** com visitas, ou ligado a insígnia ou rota → exclusão bloqueada; o painel oferece desativar;
  - **insígnia** já conquistada por alguém → exclusão bloqueada; oferecer desativar;
  - **rota** já concluída por alguém ou com insígnia → exclusão bloqueada; oferecer desativar;
  - **tema** usado por insígnia → exclusão bloqueada; usado por pontos/rotas → remove só as ligações, após confirmação.
- Itens sem histórico podem ser excluídos de verdade (inclusive os arquivos de foto/áudio).
- Sempre pedir confirmação antes de excluir.
- No banco, trocar os `ON DELETE CASCADE` de `user_visits` e `user_badges` para `RESTRICT` (proteção extra). ✅ Feito na FAL-11 (migração 0003). Ao implementar a exclusão, verificar o histórico antes de excluir e tratar `IntegrityError` como "exclusão bloqueada".

## Estatísticas

### ADM-10 — Painel de estatísticas [DESEJÁVEL]
- Totais: usuários cadastrados, usuários ativos nos últimos 7/30 dias (que abriram algum ponto), visitas.
- Pontos mais e menos visitados.
- Rotas: iniciadas, concluídas, abandonadas (exige registrar o abandono — ver observação).
- Insígnias: quantas vezes cada uma foi conquistada.
- Período filtrável (últimos 7 dias, 30 dias, tudo).
- **Observação:** para medir rotas iniciadas/abandonadas, registrar esses eventos já no MVP (tabela simples de eventos de rota), mesmo que a tela fique para depois.

## Outros

### ADM-11 — Rota de teste de e-mail [MVP]
- Mover `POST /email/test` para dentro do painel (somente administradores) ou removê-la (FAL-05).

### ADM-12 — Usabilidade do painel [MVP]
- Mensagens de sucesso/erro na própria página (hoje as rotas devolvem JSON cru no navegador).
- Após salvar, voltar para a lista.
- Funcionar bem em tela de notebook (não precisa ser otimizado para celular).
