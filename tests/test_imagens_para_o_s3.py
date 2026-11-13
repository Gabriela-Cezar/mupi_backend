"""Mudança das imagens do banco para o S3: migrações 0006/0007 e o script (INF-04).

Simula o banco de desenvolvimento: imagens guardadas nas colunas antigas.
"""
import pytest
from alembic import command
from sqlalchemy import create_engine, inspect, text

from app.scripts import move_images_to_s3
from app.scripts.move_images_to_s3 import blobs_still_in_database
from tests.conftest import BUCKET_DE_TESTE, chaves_no_bucket
from tests.test_migrations import alembic_cfg

PNG = b"\x89PNG\r\n\x1a\n" + b"foto-1"
PNG_2 = b"\x89PNG\r\n\x1a\n" + b"foto-2"
JPEG = b"\xff\xd8\xff" + b"insignia"


@pytest.fixture
def banco_antigo(tmp_path):
    """Banco na 0006 com imagens ainda nas colunas antigas."""
    url = f"sqlite:///{tmp_path / 'imagens.db'}"
    command.upgrade(alembic_cfg(url), "0006")

    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO mupi_objects (id, name, latitude, longitude) VALUES "
            "(1, 'Com duas fotos', 0, 0), (2, 'Só vídeo', 0, 0)"
        ))
        conn.execute(
            text(
                "INSERT INTO mupi_object_media (id, object_id, type, data, mime_type, url) VALUES "
                "(10, 1, 'image', :png, 'image/png', NULL), "
                "(11, 1, 'image', :png2, 'image/png', NULL), "
                "(12, 1, 'video', NULL, NULL, 'https://youtu.be/a'), "
                "(13, 2, 'video', NULL, NULL, 'https://youtu.be/b')"
            ),
            {"png": PNG, "png2": PNG_2},
        )
        conn.execute(
            text(
                "INSERT INTO badges (id, name, rule_type, image, image_mime_type) VALUES "
                "(5, 'Com imagem', 'manual', :jpeg, 'image/png'), "
                "(6, 'Sem imagem', 'manual', NULL, NULL)"
            ),
            {"jpeg": JPEG},
        )

    yield url, engine
    engine.dispose()


def move_images(engine):
    with engine.begin() as conn:
        return move_images_to_s3.move_images(conn)


def valores(engine, sql):
    with engine.connect() as conn:
        return conn.execute(text(sql)).all()


def colunas(engine, tabela):
    return {c["name"] for c in inspect(engine).get_columns(tabela)}


def test_0007_se_recusa_antes_de_copiar_as_imagens(banco_antigo):
    url, engine = banco_antigo

    with pytest.raises(RuntimeError, match="move_images_to_s3"):
        command.upgrade(alembic_cfg(url), "head")

    # Nada foi apagado
    assert "data" in colunas(engine, "mupi_object_media")
    assert "image" in colunas(engine, "badges")


def test_script_copia_a_primeira_foto_do_ponto(banco_antigo, s3_simulado):
    _, engine = banco_antigo

    assert move_images(engine) == (1, 1)

    [(chave_foto,)] = valores(engine, "SELECT photo_key FROM mupi_objects WHERE id = 1")
    assert chave_foto.startswith("points/1/photo-") and chave_foto.endswith(".png")
    arquivo = s3_simulado.get_object(Bucket=BUCKET_DE_TESTE, Key=chave_foto)
    assert arquivo["Body"].read() == PNG  # a primeira, não a segunda

    assert valores(engine, "SELECT photo_key FROM mupi_objects WHERE id = 2") == [(None,)]


def test_script_copia_a_imagem_da_insignia_com_o_tipo_real(banco_antigo, s3_simulado):
    _, engine = banco_antigo

    move_images(engine)

    [(chave,)] = valores(engine, "SELECT image_key FROM badges WHERE id = 5")
    assert chave.startswith("badges/5/image-") and chave.endswith(".jpg")
    arquivo = s3_simulado.get_object(Bucket=BUCKET_DE_TESTE, Key=chave)
    assert arquivo["ContentType"] == "image/jpeg"  # pelo conteúdo, não pelo declarado
    assert valores(engine, "SELECT image_key FROM badges WHERE id = 6") == [(None,)]


def test_rodar_o_script_de_novo_nao_duplica(banco_antigo, s3_simulado):
    _, engine = banco_antigo
    move_images(engine)

    assert move_images(engine) == (0, 0)
    assert len(chaves_no_bucket(s3_simulado)) == 2


def test_depois_do_script_a_0007_remove_as_imagens_do_banco(banco_antigo, s3_simulado):
    url, engine = banco_antigo
    move_images(engine)

    command.upgrade(alembic_cfg(url), "head")

    assert not blobs_still_in_database(engine)
    assert {"data", "mime_type"}.isdisjoint(colunas(engine, "mupi_object_media"))
    assert {"image", "image_mime_type"}.isdisjoint(colunas(engine, "badges"))
    # Os vídeos continuam; as linhas de imagem saem
    assert valores(engine, "SELECT id, type FROM mupi_object_media ORDER BY id") == [
        (12, "video"), (13, "video"),
    ]
    # As chaves continuam apontando para os arquivos
    assert len(chaves_no_bucket(s3_simulado)) == 2


def test_banco_sem_imagens_passa_direto_pela_0007(tmp_path):
    url = f"sqlite:///{tmp_path / 'vazio.db'}"

    command.upgrade(alembic_cfg(url), "head")
    command.downgrade(alembic_cfg(url), "0005")
    command.upgrade(alembic_cfg(url), "head")
