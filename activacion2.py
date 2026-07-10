"""
activar_sim.py
==============
Activa un chip (SIM) en la red Internet para el Bienestar (Altan/Qvantel).

Campos obligatorios:
  - Offer ID  → ID del plan/oferta (se ingresa manualmente)
  - Nombre    → Nombre del titular
  - Apellido  → Apellido del titular
  - ICCID     → Número impreso en la SIM (18-22 dígitos)
  - Email     → Correo del titular

Uso:
    pip install requests
    python activar_sim.py
"""
import sys
import json
import requests
from datetime import datetime, timezone

# ══════════════════════════════════════════════════════════════════════════
# CONFIGURACIÓN 
# ══════════════════════════════════════════════════════════════════════════

# URLs
AUTH_URL       = "https://auth-prod.internetparaelbienestar.mx/auth/realms/qvantel/protocol/openid-connect/token"
ACTIVATION_URL = "https://private-api-prod.internetparaelbienestar.mx/v1/onboarding/customer"

# Credenciales del cliente 
CLIENT_ID     = "iaa"
CLIENT_SECRET = "VDqnkV9Phwe9c268zwNLbSxU7qVQvzJE"

# Datos de la bodega / vendedor
DEALER_ID       = "BODEGA-PRINCIPAL-272"
SALES_PERSON_ID = "venta_online"

# Marca (x-brand). Según la documentación, 252 = BE (Bienestar).
X_BRAND = "272"

# ══════════════════════════════════════════════════════════════════════════

# ── Colores para la terminal ──────────────────────────────────────────────────
VERDE  = "\033[92m"
ROJO   = "\033[91m"
AZUL   = "\033[94m"
AMARILLO = "\033[93m"
RESET  = "\033[0m"
BOLD   = "\033[1m"


# ── Utilidades ────────────────────────────────────────────────────────────────
def banner():
    print(f"""
{AZUL}{BOLD}╔══════════════════════════════════════════════╗
║   Activación de SIM - Internet p/ Bienestar  ║
╚══════════════════════════════════════════════╝{RESET}
""")


def pedir_dato(etiqueta: str, ejemplo: str = "", obligatorio: bool = True) -> str:
    hint = f"  (ej: {ejemplo})" if ejemplo else ""
    while True:
        valor = input(f"  {BOLD}{etiqueta}{RESET}{hint}: ").strip()
        if valor:
            return valor
        if not obligatorio:
            return ""
        print(f"  {ROJO}⚠  Este campo es obligatorio.{RESET}")


def validar_iccid(iccid: str) -> bool:
    return iccid.isdigit() and 18 <= len(iccid) <= 22


def validar_email(email: str) -> bool:
    return "@" in email and "." in email.split("@")[-1]


def validar_offer_id(offer_id: str) -> bool:
    return len(offer_id) > 0


# ── PASO 1: Obtener Token ─────────────────────────────────────────────────────
def obtener_token() -> str:
    print(f"\n{AZUL}[1/2] Obteniendo token de autenticación...{RESET}")

    if not CLIENT_ID or CLIENT_ID == "TU_CLIENT_ID_AQUI" or not CLIENT_SECRET or CLIENT_SECRET == "TU_CLIENT_SECRET_AQUI":
        print(f"{ROJO}✗ ERROR: Debes escribir tu CLIENT_ID y CLIENT_SECRET reales en el bloque de configuración.{RESET}")
        sys.exit(1)

    payload = {
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type":    "client_credentials",
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    try:
        resp = requests.post(AUTH_URL, data=payload, headers=headers, timeout=15)
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"{ROJO}✗ Error de conexión al obtener token: {e}{RESET}")
        sys.exit(1)

    data  = resp.json()
    token = data.get("access_token")
    if not token:
        print(f"{ROJO}✗ No se recibió access_token. Respuesta: {resp.text}{RESET}")
        sys.exit(1)

    print(f"  {VERDE}✓ Token obtenido (expira en {data.get('expires_in', '?')} s){RESET}")
    return token


# ── PASO 2: Activar SIM ───────────────────────────────────────────────────────
def activar_sim(token: str, datos: dict) -> dict:
    print(f"\n{AZUL}[2/2] Enviando solicitud de activación...{RESET}")

    ahora_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    body = {
        "basket": {
            "salesPersonId": SALES_PERSON_ID,
            "dealerId":      DEALER_ID,
            "paymentMethod": {
                "paymentMethodId":   "generic-payment-method",
                "paymentMethodType": "cash"
            },
            "basketItems": [
                {
                    "quantity": 1,
                    "characteristics": [
                        {
                            "key":   "CH_ServiceActivationType",
                            "value": "Activation"
                        }
                    ],
                    "offerId": datos["offer_id"],
                    "CH_ICC":  datos["iccid"],
                    "useICC":  True
                }
            ]
        },
        "customer": {
            "individual": {
                "nationality": "MX",
                "gender":      "male",
                "givenName":   datos["nombre"],
                "familyName":  datos["apellido"]
            },
            "contactMedia": [
                {
                    "role": "primary",
                    "validFor": {
                        "startDatetime": ahora_iso
                    },
                    "medium": {
                        "emailAddress": {
                            "email": datos["email"]
                        }
                    }
                }
            ]
        }
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
        "x-brand":       X_BRAND
    }

    try:
        resp = requests.post(ACTIVATION_URL, json=body, headers=headers, timeout=30)
    except requests.exceptions.RequestException as e:
        print(f"{ROJO}✗ Error de conexión: {e}{RESET}")
        sys.exit(1)

    return {"status_code": resp.status_code, "raw_response": resp.text}


# ── Captura de datos del chip ─────────────────────────────────────────────────
def capturar_datos() -> dict:
    print(f"\n{BOLD}── Ingresa los datos del chip a activar ──{RESET}\n")

    # Offer ID manual
    while True:
        offer_id = pedir_dato("Offer ID del plan", "1709902044")
        if validar_offer_id(offer_id):
            break
        print(f"  {ROJO}⚠  El Offer ID no puede estar vacío.{RESET}")

    nombre   = pedir_dato("Nombre del titular",   "Juan")
    apellido = pedir_dato("Apellido del titular",  "Pérez")

    while True:
        iccid = pedir_dato("ICCID de la SIM (número del chip)", "8952140063037397790")
        if validar_iccid(iccid):
            break
        print(f"  {ROJO}⚠  ICCID inválido. Debe contener entre 18 y 22 dígitos numéricos.{RESET}")

    while True:
        email = pedir_dato("Correo electrónico", "cliente@ejemplo.com")
        if validar_email(email):
            break
        print(f"  {ROJO}⚠  Formato de correo inválido.{RESET}")

    return {
        "offer_id": offer_id,
        "nombre":   nombre,
        "apellido": apellido,
        "iccid":    iccid,
        "email":    email,
    }


# ── Mostrar resultado ─────────────────────────────────────────────────────────
def mostrar_resultado(resultado: dict, datos: dict):
    status = resultado["status_code"]
    raw_body = resultado["raw_response"]

    print(f"\n{BOLD}{'═'*50}{RESET}")
    print(f"  HTTP Status : {status}")

    if status in (200, 201):
        print(f"\n  {VERDE}{BOLD}✓ ¡Activación exitosa!{RESET}")
        print(f"  Titular  : {datos['nombre']} {datos['apellido']}")
        print(f"  ICCID    : {datos['iccid']}")
        print(f"  Offer ID : {datos['offer_id']}")
    else:
        print(f"\n  {ROJO}{BOLD}✗ Error en la activación{RESET}")

    print(f"\n  Respuesta completa:\n{raw_body}")

    guardar_log(resultado, datos)


def guardar_log(resultado: dict, datos: dict):
    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"activacion_{ts}.json"

    log = {
        "timestamp": ts,
        "offer_id":  datos["offer_id"],
        "titular":   {"nombre": datos["nombre"], "apellido": datos["apellido"], "email": datos["email"]},
        "iccid":     datos["iccid"],
        "http_status": resultado["status_code"],
        "respuesta_cruda": resultado["raw_response"]
    }

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=4, ensure_ascii=False)

    print(f"\n  {AZUL}ℹ  Log guardado en: {filename}{RESET}")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    banner()

    datos = capturar_datos()

    print(f"""
{BOLD}── Confirma los datos antes de activar ──{RESET}
  Offer ID : {VERDE}{datos['offer_id']}{RESET}
  Titular  : {datos['nombre']} {datos['apellido']}
  ICCID    : {datos['iccid']}
  Email    : {datos['email']}
""")

    confirmacion = input(f"  ¿Proceder con la activación? {BOLD}[s/N]{RESET}: ").strip().lower()
    if confirmacion != "s":
        print(f"\n  {ROJO}Activación cancelada.{RESET}\n")
        sys.exit(0)

    token     = obtener_token()
    resultado = activar_sim(token, datos)
    mostrar_resultado(resultado, datos)


if __name__ == "__main__":
    main()