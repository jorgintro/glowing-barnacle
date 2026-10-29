from django.db import models


class EstadoVersion(models.TextChoices):
    """Estados del flujo de aprobación (CLAUDE.md §5.1)."""

    BORRADOR = "BORRADOR", "Borrador"
    PROPUESTO = "PROPUESTO", "Propuesto"
    APROBADO_CP = "APROBADO_CP", "Aprobado por la Comisión Permanente"
    RATIFICADO_JG = "RATIFICADO_JG", "Ratificado por la Junta General"
    RECHAZADO = "RECHAZADO", "Rechazado"
    MODIFICADO = "MODIFICADO", "Modificación presupuestaria"


ESTADOS_EDITABLES = frozenset({EstadoVersion.BORRADOR})
