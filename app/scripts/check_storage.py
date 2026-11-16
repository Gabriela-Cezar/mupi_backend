"""Confere se o bucket S3 do .env está pronto para o MUPI (INF-04).

Uso (na raiz do projeto, com S3_BUCKET e as credenciais no .env):
    python -m app.scripts.check_storage

Envia um arquivo pequeno, baixa pelo link assinado (como o app faz), confere
que sem assinatura o arquivo NÃO é acessível (bucket privado) e apaga o arquivo.
Serve para o bucket de desenvolvimento e, depois, para o de produção.

Com a pasta local (LOCAL_STORAGE_DIR), o download passa pelo backend: ele
precisa estar rodando (padrão http://127.0.0.1:8000; outro endereço com
--backend-url http://127.0.0.1:8011).
"""
import argparse

import requests

from app.core import config
from app.service import storage_service

TEST_KEY_PREFIX = "verificacao"
DEFAULT_BACKEND_URL = "http://127.0.0.1:8000"
CONTENT = b"MUPI - verificacao do armazenamento"


def check(backend_url: str = DEFAULT_BACKEND_URL) -> list[str]:
    """Executa as verificações e devolve a lista de problemas (vazia = tudo certo)."""
    problems = []
    key = storage_service.build_key(TEST_KEY_PREFIX, "teste", "text/plain")

    try:
        storage_service.save(key, CONTENT, "text/plain")
    except storage_service.StorageError as exc:
        cause = exc.__cause__
        return [f"Não foi possível enviar o arquivo: {cause or exc}. "
                "Confira o nome do bucket, a região e a permissão s3:PutObject."]

    print(f"✓ Envio: {key}")

    try:
        link = storage_service.url(key, expires_in=300)

        # Pasta local: o link é relativo ao backend (o app completa sozinho)
        if link.startswith("/"):
            link = backend_url.rstrip("/") + link
        response = requests.get(link, timeout=15, allow_redirects=False)

        if response.status_code == 200 and response.content == CONTENT:
            print("✓ Download pelo link assinado (como o app faz)")
        else:
            problems.append(
                f"O link assinado respondeu {response.status_code}: {response.text[:300]} "
                "Confira a região (AWS_REGION) e a permissão s3:GetObject."
            )

        public = requests.get(link.split("?")[0], timeout=15, allow_redirects=False)

        if public.status_code == 403:
            print("✓ Sem assinatura o arquivo é recusado (bucket privado)")
        else:
            problems.append(
                f"O arquivo respondeu {public.status_code} sem assinatura. "
                "O bucket deve ficar privado: ative 'Bloquear todo o acesso público'."
            )
    except requests.RequestException as exc:
        problems.append(f"Erro de conexão ao baixar o arquivo: {exc}")
    finally:
        try:
            storage_service.delete(key)
            print("✓ Exclusão (s3:DeleteObject)")
        except storage_service.StorageError as exc:
            problems.append(
                f"Não foi possível apagar o arquivo de teste: {exc.__cause__ or exc}. "
                "Confira a permissão s3:DeleteObject."
            )

    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description="Confere o armazenamento de arquivos.")
    parser.add_argument(
        "--backend-url", default=DEFAULT_BACKEND_URL,
        help="Backend rodando, para baixar os arquivos da pasta local.",
    )
    args = parser.parse_args()

    if not storage_service.is_configured():
        print("Erro: defina S3_BUCKET (e as credenciais da AWS) ou LOCAL_STORAGE_DIR no .env.")
        raise SystemExit(1)

    if storage_service.is_local():
        print(f"Pasta local: {config.LOCAL_STORAGE_DIR} (via {args.backend_url})\n")
    else:
        print(f"Bucket: {config.S3_BUCKET} ({config.AWS_REGION})\n")
    problems = check(args.backend_url)

    if problems:
        print("\nProblemas encontrados:")
        for problem in problems:
            print(f"✗ {problem}")
        raise SystemExit(1)

    print("\nTudo certo: o armazenamento está pronto.")


if __name__ == "__main__":
    main()
