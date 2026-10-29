from decimal import Decimal

from django import template

from apps.presupuesto.dinero import formatear_euros

register = template.Library()

_CLASES_ESTADO = {
    "BORRADOR": "aviso",
    "PROPUESTO": "marca",
    "APROBADO_CP": "ok",
    "RATIFICADO_JG": "ok",
    "RECHAZADO": "error",
    "MODIFICADO": "marca",
}


@register.filter
def euros(valor: Decimal | None) -> str:
    return formatear_euros(valor)


@register.filter
def clase_estado(estado: str) -> str:
    return _CLASES_ESTADO.get(estado, "marca")
