"""Copia para o S3 as imagens que ainda estão guardadas no banco (INF-04).

Uso (na raiz do projeto, com S3_BUCKET e as credenciais no .env):
    alembic upgrade 0006
    python -m app.scripts.move_images_to_s3
    alembic upgrade head

- Ponto: a primeira imagem vira a foto do ponto (mupi_objects.photo_key).
  As demais imagens do mesmo ponto não são copiadas (PT-05: uma foto por ponto)
  e serão apagadas pela migração 0007.
- Insígnia: badges.image vai para badges.image_key.

Pode ser rodado de novo sem problema: o que já tem chave é pulado. Tudo é
gravado numa única transação: se algo falhar, nenhuma chave é salva.
"""
from sqlalchemy import Connection, inspect, text

from app.core.file_types import sniff_image_mime
from app.database.database import engine
from app.service import storage_service

PONTOS = text("""
    SELECT DISTINCT ON (m.object_id) m.object_id, m.id, m.data, m.mime_type
    FROM mupi_object_media m
    JOIN mupi_objects o ON o.id = m.object_id
    WHERE m.type = 'image' AND m.data IS NOT NULL AND o.photo_key IS NULL
    ORDER BY m.object_id, m.id
""")

PONTOS_SQLITE = text("""
    SELECT m.object_id, m.id, m.data, m.mime_type
    FROM mupi_object_media m
    JOIN mupi_objects o ON o.id = m.object_id
    WHERE m.type = 'image' AND m.data IS NOT NULL AND o.photo_key IS NULL
      AND m.id = (SELECT MIN(m2.id) FROM mupi_object_media m2
                  WHERE m2.object_id = m.object_id AND m2.type = 'image'
                    AND m2.data IS NOT NULL)
""")

INSIGNIAS = text("""
    SELECT id, image, image_mime_type FROM badges
    WHERE image IS NOT NULL AND image_key IS NULL
""")


def _content_type(data: bytes, declared: str | None) -> str:
    return sniff_image_mime(data) or declared or "application/octet-stream"


def blobs_still_in_database(bind=engine) -> bool:
    """As colunas antigas ainda existem (migração 0007 não aplicada)?"""
    columns = {c["name"] for c in inspect(bind).get_columns("badges")}
    return "image" in columns


def move_images(conn: Connection) -> tuple[int, int]:
    """Copia as imagens e devolve (pontos, insígnias) copiados.

    Grava as chaves na conexão recebida; quem chama confirma a transação.
    """
    points = badges = 0
    query = PONTOS_SQLITE if conn.dialect.name == "sqlite" else PONTOS

    for object_id, media_id, data, mime in conn.execute(query).all():
        data = bytes(data)
        content_type = _content_type(data, mime)
        key = storage_service.build_key(f"points/{object_id}", "photo", content_type)
        storage_service.save(key, data, content_type)

        conn.execute(
            text("UPDATE mupi_objects SET photo_key = :key WHERE id = :id"),
            {"key": key, "id": object_id},
        )
        points += 1
        print(f"Ponto {object_id}: imagem {media_id} → {key}")

    for badge_id, data, mime in conn.execute(INSIGNIAS).all():
        data = bytes(data)
        content_type = _content_type(data, mime)
        key = storage_service.build_key(f"badges/{badge_id}", "image", content_type)
        storage_service.save(key, data, content_type)

        conn.execute(
            text("UPDATE badges SET image_key = :key WHERE id = :id"),
            {"key": key, "id": badge_id},
        )
        badges += 1
        print(f"Insígnia {badge_id} → {key}")

    return points, badges


def main() -> None:
    if not storage_service.is_configured():
        print("Erro: defina S3_BUCKET (e as credenciais da AWS) no .env.")
        raise SystemExit(1)

    if not blobs_still_in_database():
        print("Nada a fazer: as imagens já não ficam no banco (migração 0007 aplicada).")
        return

    with engine.begin() as conn:
        points, badges = move_images(conn)
    print(f"\nCopiados: {points} foto(s) de ponto e {badges} imagem(ns) de insígnia.")
    print("Agora aplique o restante das migrações: alembic upgrade head")


if __name__ == "__main__":
    main()
