"""
get_token.py
------------
Obtiene un access_token (Bearer) del endpoint OAuth2 de IPB/Altán Redes
(Solo ambiente de producción, según documentación "APIs CRM para MVNOs").

Requiere un archivo .env con:
    IPB_CLIENT_ID
    IPB_CLIENT_SECRET
    IPB_TOKEN_URL

Uso:
    python get_token.py
    # o importarlo:
    from get_token import obtener_token
    token = obtener_token()
"""

import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN_URL = os.getenv("IPB_TOKEN_URL")
CLIENT_ID = os.getenv("IPB_CLIENT_ID")
CLIENT_SECRET = os.getenv("IPB_CLIENT_SECRET")


def obtener_token() -> str:
    """
    Solicita un access_token usando client_credentials.
    Retorna únicamente el string del token (sin 'Bearer ').
    """
    if not all([TOKEN_URL, CLIENT_ID, CLIENT_SECRET]):
        raise RuntimeError(
            "Faltan variables de entorno. Verifica IPB_TOKEN_URL, "
            "IPB_CLIENT_ID e IPB_CLIENT_SECRET en tu archivo .env"
        )

    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "client_id": 'iaa',
        "client_secret": 'VDqnkV9Phwe9c268zwNLbSxU7qVQvzJE',
        "grant_type": "client_credentials",
    }

    resp = requests.post('https://auth-prod.internetparaelbienestar.mx/auth/realms/qvantel/protocol/openid-connect/token', headers=headers, data=data, timeout=15)

    if resp.status_code != 200:
        raise RuntimeError(
            f"Error al obtener token ({resp.status_code}): {resp.text}"
        )

    body = resp.json()
    access_token = body.get("access_token")
    expires_in = body.get("expires_in")

    if not access_token:
        raise RuntimeError(f"Respuesta inesperada, no hay access_token: {body}")

    print(f"[OK] Token obtenido. Expira en {expires_in} segundos.", file=sys.stderr)
    return access_token


if __name__ == "__main__":
    try:
        token = obtener_token()
        print(token)
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)