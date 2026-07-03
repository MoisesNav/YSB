"""
Cliente para:
  1) Obtener un token OAuth (client_credentials) contra Altán (solo producción).
  2) Usar ese token para activar una SIM (alta de cliente nuevo / PORT-IN)
     vía POST /v1/onboarding/customer.

Uso rápido (ver también el bloque `if __name__ == "__main__":` al final):

    from altan_client import AltanClient

    client = AltanClient()
    resultado = client.activar_sim(
        offer_id="1709902044",
        icc="8952140063037397790",
        nombre="Ragde",
        apellido="Flores",
        telefono="5522720325",
        email="test@gmail.com",
        direccion={
            "city": "Roma",
            "apartment": "13B",
            "country": "MX",
            "building": "54",
            "postalCode": "06700",
            "street": "Yucatan",
            "stateOrProvince": "Ciudad de México",
            "county": "Cuauhtemoc",
        },
    )
    print(resultado)
"""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()  # lee el archivo .env en el directorio actual


# ---------------------------------------------------------------------------
# Planes disponibles (offer_id que se manda en el "basketItems.offerId")
# ---------------------------------------------------------------------------
PLANES = [
    {"costo": "$150.00", "gb": "4 GB",  "sku": "YSB150_30D_4GB",  "offer_id": "1709902044"},
    {"costo": "$190.00", "gb": "12 GB", "sku": "YSB190_30D_12GB", "offer_id": "1709902045"},
    {"costo": "$250.00", "gb": "24 GB", "sku": "YSB250_30D_24GB", "offer_id": "1709902046"},
    {"costo": "$300.00", "gb": "35 GB", "sku": "YSB300_30D_35GB", "offer_id": "1709902047"},
    {"costo": "$500.00", "gb": "50 GB", "sku": "YSB500_30D_50GB", "offer_id": "1709902048"},
]


def buscar_plan_por_sku(sku: str) -> Optional[dict]:
    """Utilidad para obtener el offer_id a partir del SKU."""
    return next((p for p in PLANES if p["sku"] == sku), None)


# ---------------------------------------------------------------------------
# Excepciones propias
# ---------------------------------------------------------------------------
class AltanAuthError(Exception):
    """Error al obtener el token."""


class AltanAPIError(Exception):
    """Error devuelto por la API de activación. Incluye código y detalle."""

    def __init__(self, status_code: int, error_code: str, message: str, raw: dict):
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        self.raw = raw
        super().__init__(f"[{status_code}] ({error_code}) {message}")


# Tabla de códigos de error documentados en el manual (API PORT-IN)
CODIGOS_ERROR = {
    "30": "Campo obligatorio faltante",
    "31": "Error de formato en el campo",
    "32": "Conflicto de valor de entrada",
    "40": "MSISDN no encontrado",
    "41": "Estado de MSISDN inválido",
    "42": "MSISDN no disponible",
    "50": "Portabilidad no permitida",
    "51": "NIP inválido",
    "52": "Solicitud de portabilidad existente",
    "60": "Error del sistema",
    "61": "Tiempo de espera del servicio externo",
    "70": "Violación de regla de negocio",
}


# ---------------------------------------------------------------------------
# Cliente principal
# ---------------------------------------------------------------------------
@dataclass
class AltanClient:
    auth_url: str = field(default_factory=lambda: os.getenv("ALTAN_AUTH_URL", ""))
    client_id: str = field(default_factory=lambda: os.getenv("ALTAN_CLIENT_ID", ""))
    client_secret: str = field(default_factory=lambda: os.getenv("ALTAN_CLIENT_SECRET", ""))
    onboarding_url: str = field(default_factory=lambda: os.getenv("ALTAN_ONBOARDING_URL", ""))
    sales_person_id: str = field(default_factory=lambda: os.getenv("ALTAN_SALES_PERSON_ID", "venta_online"))
    dealer_id: str = field(default_factory=lambda: os.getenv("ALTAN_DEALER_ID", "DEFAULT-STOCK-252"))

    _token: Optional[str] = field(default=None, init=False, repr=False)
    _token_expira_en: float = field(default=0.0, init=False, repr=False)

    # ------------------------------------------------------------------
    # 1) Token
    # ------------------------------------------------------------------
    def obtener_token(self, forzar_renovacion: bool = False) -> str:
        """
        Obtiene (o reutiliza si sigue vigente) el access_token.
        Los tokens duran 300s (5 min) según la documentación, así que
        se renuevan automáticamente con un pequeño margen de seguridad.
        """
        ahora = time.time()
        if not forzar_renovacion and self._token and ahora < self._token_expira_en:
            return self._token

        if not self.client_id or not self.client_secret:
            raise AltanAuthError(
                "Faltan ALTAN_CLIENT_ID / ALTAN_CLIENT_SECRET. Revisa tu archivo .env"
            )

        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials",
        }

        resp = requests.post(self.auth_url, headers=headers, data=data, timeout=30)

        if resp.status_code != 200:
            raise AltanAuthError(
                f"No se pudo obtener el token (status={resp.status_code}): {resp.text}"
            )

        payload = resp.json()
        token = payload.get("access_token")
        expires_in = payload.get("expires_in", 300)

        if not token:
            raise AltanAuthError(f"Respuesta sin access_token: {payload}")

        # Margen de 20s para evitar usar un token a punto de expirar
        self._token = token
        self._token_expira_en = ahora + max(expires_in - 20, 0)
        return self._token

    # ------------------------------------------------------------------
    # 2) Activación de SIM (usuario nuevo) -> /v1/onboarding/customer
    # ------------------------------------------------------------------
    def activar_sim(
        self,
        offer_id: str,
        icc: str,
        nombre: str,
        apellido: str,
        telefono: str,
        email: str,
        direccion: dict,
        genero: str = "male",
        nacionalidad: str = "MX",
        # Solo si el número YA existe en otro operador y se va a portar:
        port_in_number: Optional[str] = None,
        nip: Optional[str] = None,
        use_icc: bool = True,
        payment_method_id: str = "generic-payment-method",
        payment_method_type: str = "cash",
    ) -> dict:
        """
        Activa una SIM para un cliente nuevo.

        Parámetros clave:
          offer_id       -> viene de PLANES (ej. "1709902044")
          icc            -> ICCID de la SIM física a activar
          port_in_number -> si el cliente quiere portar un número existente
          nip            -> NIP de portabilidad (obligatorio si hay port_in_number)

        Devuelve el JSON de respuesta si todo sale bien.
        Lanza AltanAPIError si la API responde con un error documentado.
        """
        token = self.obtener_token()

        characteristics = [
            {"value": "Activation", "key": "CH_ServiceActivationType"}
        ]

        basket_item = {
            "quantity": 1,
            "characteristics": characteristics,
            "offerId": offer_id,
            "CH_ICC": icc,
            "useICC": use_icc,
        }

        if port_in_number:
            basket_item["CH_PortInNumberResource"] = port_in_number
            basket_item["CH_NIP"] = nip or ""

        body = {
            "basket": {
                "salesPersonId": self.sales_person_id,
                "dealerId": self.dealer_id,
                "paymentMethod": {
                    "paymentMethodId": payment_method_id,
                    "paymentMethodType": payment_method_type,
                },
                "basketItems": [basket_item],
            },
            "customer": {
                "individual": {
                    "nationality": nacionalidad,
                    "gender": genero,
                    "familyName": apellido,
                    "givenName": nombre,
                },
                "contactMedia": [
                    {
                        "role": "primary",
                        "validFor": {
                            "startDatetime": _iso_now()
                        },
                        "medium": {
                            "telephoneNumber": {
                                "number": telefono,
                                "numberType": "mobile",
                            },
                            "emailAddress": {"email": email},
                            "postalAddress": direccion,
                        },
                    }
                ],
            },
        }

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        resp = requests.post(self.onboarding_url, headers=headers, json=body, timeout=60)
        return self._procesar_respuesta(resp)

    # ------------------------------------------------------------------
    @staticmethod
    def _procesar_respuesta(resp: requests.Response) -> dict:
        try:
            payload = resp.json()
        except ValueError:
            payload = {"raw_text": resp.text}

        if resp.ok and payload.get("status") != "error":
            return payload

        # La API puede devolver 200 con status "error" en el body,
        # o un status HTTP de error directamente. Cubrimos ambos casos.
        error_code = str(payload.get("errorCode", resp.status_code))
        message = payload.get("errorMessage") or payload.get("message") or resp.text
        descripcion = CODIGOS_ERROR.get(error_code, "Error no documentado")

        raise AltanAPIError(
            status_code=resp.status_code,
            error_code=error_code,
            message=f"{message} ({descripcion})",
            raw=payload,
        )


def _iso_now() -> str:
    import datetime

    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")


# ---------------------------------------------------------------------------
# Ejemplo de uso por línea de comandos
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    cliente = AltanClient()

    # 1) Elige un plan de la lista PLANES
    plan = buscar_plan_por_sku("YSB190_30D_12GB")
    print("Plan seleccionado:", plan)

    try:
        resultado = cliente.activar_sim(
            offer_id=plan["offer_id"],
            icc="8952140063037397790",   # ICCID real de la SIM a activar
            nombre="Ragde",
            apellido="Flores",
            telefono="5522720325",
            email="test@gmail.com",
            direccion={
                "city": "Roma",
                "apartment": "13B",
                "country": "MX",
                "building": "54",
                "postalCode": "06700",
                "street": "Yucatan",
                "stateOrProvince": "Ciudad de México",
                "county": "Cuauhtemoc",
            },
            # Descomenta si es portabilidad de un número existente:
            # port_in_number="525587654321",
            # nip="1234",
        )
        print("Activación exitosa:", resultado)

    except AltanAPIError as e:
        print(f"Error de la API [{e.error_code}]: {e.message}")
    except AltanAuthError as e:
        print(f"Error de autenticación: {e}")
