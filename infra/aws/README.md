# AWS — arquivos do MUPI no S3 (INF-04)

Um bucket por ambiente, na região São Paulo (`sa-east-1`):

| Ambiente | Bucket (sugestão) | Usuário IAM |
|---|---|---|
| Desenvolvimento | `mupi-arquivos-dev-<sufixo>` | `mupi-app-dev` |
| Produção (Etapa 3) | `mupi-arquivos-prod-<sufixo>` | `mupi-app-prod` |

O nome do bucket é único no mundo inteiro: o `<sufixo>` evita conflito (ex.: 4 letras aleatórias).

## 1. Bucket

S3 → **Create bucket**:
- **Region:** South America (São Paulo) `sa-east-1`
- **Object Ownership:** ACLs disabled (padrão)
- **Block all public access:** marcado (padrão). Nunca desmarcar: o app recebe links assinados.
- **Bucket Versioning:** Enable
- **Default encryption:** SSE-S3 (padrão)

Não é preciso configurar CORS: o app de celular não depende disso e o painel envia os arquivos pelo backend.

## 2. Versões antigas apagadas em 30 dias

Bucket → **Management** → **Create lifecycle rule**:
- Nome: `apagar-versoes-antigas-30-dias`; escopo: **Apply to all objects in the bucket**
- Ações:
  - **Permanently delete noncurrent versions of objects** → 30 dias
  - **Delete expired object delete markers or incomplete multipart uploads** → marcar os dois; multipart: 7 dias

(Equivale a `ciclo-de-vida.json`, para quem usar a AWS CLI.)

## 3. Usuário IAM da aplicação

IAM → **Users** → **Create user**:
- Nome: `mupi-app-dev`; **sem** acesso ao console
- Permissões: **Attach policies directly** → não marcar nenhuma → criar
- No usuário criado: **Add permissions** → **Create inline policy** → **JSON** → colar `politica-iam-app.json`, trocando `NOME-DO-BUCKET` → nome: `mupi-arquivos`
- **Security credentials** → **Create access key** → caso de uso **Local code** (no servidor de produção: **Application running outside AWS**, porque o Lightsail não usa roles do IAM)
- Copiar o *Access key ID* e o *Secret access key* (o segredo só aparece uma vez)

## 4. `.env` do backend

```
S3_BUCKET=mupi-arquivos-dev-<sufixo>
AWS_REGION=sa-east-1
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
```

## 5. Conferir e migrar

```
python -m app.scripts.check_storage        # envio, link assinado, bucket privado, exclusão
python -m app.scripts.move_images_to_s3    # só se o banco ainda tiver imagens antigas
alembic upgrade head
```

## Segurança da conta (Etapa 0)

- MFA no usuário raiz; não usar o raiz no dia a dia (criar um usuário IAM próprio com MFA).
- **Billing → Budgets:** alertas por e-mail em US$ 30 e US$ 50 por mês.
- Se uma chave vazar: IAM → usuário → desativar a chave e criar outra.
