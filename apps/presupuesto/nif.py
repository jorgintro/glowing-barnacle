"""Comprobación del formato del NIF/NIE/CIF.

Solo valida la forma y, en personas físicas, la letra de control. No comprueba que el documento
exista ni que pertenezca a quien dice.
"""

import re

from django.core.exceptions import ValidationError

_LETRAS = "TRWAGMYFPDXBNJZSQVHLCKE"
_DNI = re.compile(r"^(\d{8})([A-Z])$")
_NIE = re.compile(r"^([XYZ])(\d{7})([A-Z])$")
_CIF = re.compile(r"^[A-HJNPQRSUVW]\d{7}[0-9A-J]$")


def normalizar_nif(nif: str) -> str:
    return re.sub(r"[\s.\-]", "", nif).upper()


def validar_nif(nif: str, tipo_persona: str) -> str:
    """Devuelve el NIF normalizado o lanza ``ValidationError`` explicando el problema."""
    n = normalizar_nif(nif)
    if tipo_persona == "JURIDICA":
        if not _CIF.match(n):
            raise ValidationError("El CIF no tiene un formato válido.")
        return n
    dni, nie = _DNI.match(n), _NIE.match(n)
    if dni:
        numero, letra = int(dni.group(1)), dni.group(2)
    elif nie:
        numero = int("XYZ".index(nie.group(1)) * 10_000_000 + int(nie.group(2)))
        letra = nie.group(3)
    else:
        raise ValidationError("El NIF/NIE no tiene un formato válido.")
    if _LETRAS[numero % 23] != letra:
        raise ValidationError("La letra de control del NIF/NIE no es correcta.")
    return n


def enmascarar_nif(nif: str) -> str:
    """Muestra solo los 4 últimos caracteres: «****678Z» (minimización de datos)."""
    return "*" * max(len(nif) - 4, 0) + nif[-4:]
