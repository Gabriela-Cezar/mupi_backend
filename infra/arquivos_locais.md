# Arquivos numa pasta local (desenvolvimento sem S3)

Enquanto não há bucket (nem MinIO), o backend pode guardar fotos, imagens de
insígnia e áudios numa pasta do computador. **Só para desenvolvimento.**

## Como funciona

- Os arquivos ficam em `LOCAL_STORAGE_DIR` (ex.: `arquivos_locais/points/3/photo-<uuid>.jpg`).
  A pasta está no `.gitignore`.
- O banco guarda a mesma chave que guardaria com o S3. Ao trocar para o S3
  depois, basta copiar a pasta para o bucket mantendo os caminhos.
- O app e o painel recebem um link **relativo, assinado e temporário**:
  `/local-files/<chave>?expires=...&signature=...`. É o mesmo papel do link
  assinado do S3: sem assinatura válida, ou depois de vencer, o backend responde 403.
- O app completa o link relativo com o endereço do backend (`ApiConfig.resolve`):
  funciona no emulador Android (`10.0.2.2:8000`) sem `adb reverse`.

## `.env` do backend

Deixe as variáveis do S3 vazias ou comentadas (as duas opções juntas dão erro):

```
# S3_BUCKET=
LOCAL_STORAGE_DIR=arquivos_locais
```

Caminho relativo = relativo à raiz do backend.

## Conferir

Com o backend rodando (`uvicorn main:app`):

```
python -m app.scripts.check_storage
```

## Migrar um banco antigo (Etapa 1)

```
alembic upgrade 0006
python -m app.scripts.move_images_to_s3   # copia as imagens do banco para a pasta
alembic upgrade head
```

## Trocar para o S3 depois

1. Copie a pasta para o bucket mantendo os caminhos
   (ex.: `aws s3 sync arquivos_locais/ s3://<bucket>/`).
2. No `.env`, remova `LOCAL_STORAGE_DIR` e preencha as variáveis do S3.
3. `python -m app.scripts.check_storage`.
