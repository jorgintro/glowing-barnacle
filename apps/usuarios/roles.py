from django.db import models


class Rol(models.TextChoices):
    """Los tres roles del sistema, alineados con los órganos del partido (§4)."""

    TESORERO = "TESORERO", "Tesorero"
    COMISION_PERMANENTE = "COMISION_PERMANENTE", "Comisión Permanente"
    JUNTA_GENERAL = "JUNTA_GENERAL", "Junta General"


DESCRIPCION_ROL: dict[str, dict[str, str]] = {
    Rol.TESORERO: {
        "puede": "Elaborar borradores, gestionar partidas y anexos, proponer a la Comisión "
        "Permanente, generar salidas y gestionar usuarios.",
        "no_puede": "Aprobar su propia propuesta o modificar versiones aprobadas.",
    },
    Rol.COMISION_PERMANENTE: {
        "puede": "Consultar, comentar, solicitar cambios y votar la aprobación.",
        "no_puede": "Editar cifras directamente o ratificar.",
    },
    Rol.JUNTA_GENERAL: {
        "puede": "Consultar la versión aprobada y registrar la ratificación o el rechazo.",
        "no_puede": "Editar el presupuesto.",
    },
}
