# S3 local com MinIO (desenvolvimento)

> **Atenção (nov/2025):** a MinIO deixou de publicar as imagens Docker da
> edição comunitária e o download da imagem fixada aqui passou a ser recusado.
> Sem uma imagem disponível, use a pasta local: `infra/arquivos_locais.md`.

Permite desenvolver com fotos, imagens de insígnia e áudios sem depender do
provedor de nuvem (AWS ou alternativa, ainda em decisão). O código é o mesmo
de produção: o `storage_service` fala o protocolo do S3 e só muda o `.env`.

## 1. `.env` do backend

```
S3_BUCKET=mupi-arquivos-dev
AWS_REGION=sa-east-1
AWS_ACCESS_KEY_ID=mupi-dev
AWS_SECRET_ACCESS_KEY=<senha longa qualquer, só para o MinIO local>
S3_ENDPOINT_URL=http://localhost:9000
```

## 2. Subir o MinIO

Na raiz do backend (o usuário precisa estar no grupo `docker`):

```
docker compose --env-file .env -f infra/minio/docker-compose.yml up -d
```

Console web: http://localhost:9001 (entrar com as chaves do `.env`).

## 3. Criar o bucket (uma vez)

```
python -c "from app.service import storage_service as s; from app.core import config; s._s3().create_bucket(Bucket=config.S3_BUCKET)"
python -m app.scripts.check_storage
```

O bucket nasce privado: só os links assinados funcionam (o `check_storage`
confere isso).

## 4. Celular e emulador Android

O link assinado leva o endereço `localhost:9000` dentro da assinatura: não dá
para trocar o endereço no app. Para o aparelho enxergar o MinIO do computador:

```
adb reverse tcp:9000 tcp:9000
```

Vale para o emulador e para o celular no cabo USB; refazer a cada vez que o
aparelho for reconectado. No iOS Simulator `localhost` já é o computador.

## Parar e apagar

```
docker compose --env-file .env -f infra/minio/docker-compose.yml down      # para (mantém os arquivos)
docker compose --env-file .env -f infra/minio/docker-compose.yml down -v   # apaga também os arquivos
```
