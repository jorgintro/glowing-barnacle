"""Registros del flujo de aprobación (CLAUDE.md §5 y §10).

Todos son inalterables una vez cerrados; lo garantizan disparadores de PostgreSQL (migración 0002).
"""

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.presupuesto.estados import EstadoVersion
from apps.presupuesto.models import VersionPresupuesto


class TransicionEstado(models.Model):
    """Hoja de control de versiones: cada cambio de estado, con quién, cuándo y su huella."""

    version = models.ForeignKey(
        VersionPresupuesto, on_delete=models.PROTECT, related_name="transiciones"
    )
    de_estado = models.CharField(max_length=20, choices=EstadoVersion.choices)
    a_estado = models.CharField(max_length=20, choices=EstadoVersion.choices)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    rol = models.CharField(max_length=30, blank=True)
    fecha = models.DateTimeField(default=timezone.now)
    motivo = models.TextField(blank=True)
    hash_version = models.CharField(max_length=64, blank=True)
    hash_previo = models.CharField(max_length=64, blank=True)
    hash_encadenado = models.CharField(max_length=64)
    validacion = models.JSONField(null=True, blank=True)
    avisos_aceptados = models.JSONField(default=list, blank=True)
    es_demo = models.BooleanField(default=False)

    class Meta:
        ordering = ["version", "id"]
        verbose_name = "transición de estado"
        verbose_name_plural = "transiciones de estado"

    def __str__(self) -> str:
        return f"{self.version}: {self.de_estado} → {self.a_estado}"


class EstadoVotacion(models.TextChoices):
    ABIERTA = "ABIERTA", "Abierta"
    CERRADA = "CERRADA", "Cerrada"


class ResultadoVotacion(models.TextChoices):
    APROBADA = "APROBADA", "Aprobada"
    RECHAZADA = "RECHAZADA", "Rechazada"
    ANULADA = "ANULADA", "Anulada (la propuesta se devolvió al Tesorero)"


class Voto(models.TextChoices):
    A_FAVOR = "A_FAVOR", "A favor"
    EN_CONTRA = "EN_CONTRA", "En contra"
    ABSTENCION = "ABSTENCION", "Abstención"


class Votacion(models.Model):
    version = models.ForeignKey(
        VersionPresupuesto, on_delete=models.PROTECT, related_name="votaciones"
    )
    estado = models.CharField(
        max_length=10, choices=EstadoVotacion.choices, default=EstadoVotacion.ABIERTA
    )
    resultado = models.CharField(max_length=10, choices=ResultadoVotacion.choices, blank=True)
    abierta_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    abierta_en = models.DateTimeField(default=timezone.now)
    cerrada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    cerrada_en = models.DateTimeField(null=True, blank=True)
    observaciones = models.TextField(blank=True)
    # Totales fijados al cerrar (el detalle nominal está en VotoNominal).
    miembros = models.PositiveSmallIntegerField(null=True, blank=True)
    asistentes = models.PositiveSmallIntegerField(null=True, blank=True)
    a_favor = models.PositiveSmallIntegerField(null=True, blank=True)
    en_contra = models.PositiveSmallIntegerField(null=True, blank=True)
    abstenciones = models.PositiveSmallIntegerField(null=True, blank=True)
    evaluacion = models.JSONField(null=True, blank=True)
    es_demo = models.BooleanField(default=False)

    class Meta:
        ordering = ["version", "id"]
        verbose_name = "votación"
        verbose_name_plural = "votaciones"
        constraints = [
            models.UniqueConstraint(
                fields=["version"],
                condition=Q(estado="ABIERTA"),
                name="una_votacion_abierta_por_version",
            ),
        ]

    def __str__(self) -> str:
        return f"Votación de {self.version} ({self.get_estado_display()})"


class VotoNominal(models.Model):
    """El voto de cada miembro de la Comisión Permanente (queda constancia nominal)."""

    votacion = models.ForeignKey(Votacion, on_delete=models.PROTECT, related_name="votos")
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    voto = models.CharField(max_length=10, choices=Voto.choices)
    emitido_en = models.DateTimeField(default=timezone.now)
    es_demo = models.BooleanField(default=False)

    class Meta:
        ordering = ["votacion", "emitido_en"]
        verbose_name = "voto nominal"
        verbose_name_plural = "votos nominales"
        constraints = [
            models.UniqueConstraint(fields=["votacion", "usuario"], name="un_voto_por_miembro"),
        ]

    def __str__(self) -> str:
        return f"{self.usuario}: {self.get_voto_display()}"


class Convocatoria(models.Model):
    """Convocatoria de la Junta General (regla O-004)."""

    version = models.ForeignKey(
        VersionPresupuesto, on_delete=models.PROTECT, related_name="convocatorias"
    )
    fecha_convocatoria = models.DateField()
    fecha_sesion = models.DateField()
    referencia = models.CharField(max_length=200, blank=True)
    registrada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    registrada_en = models.DateTimeField(default=timezone.now)
    es_demo = models.BooleanField(default=False)

    class Meta:
        ordering = ["version", "id"]
        verbose_name = "convocatoria de la Junta"
        verbose_name_plural = "convocatorias de la Junta"

    def __str__(self) -> str:
        return f"Convocatoria del {self.fecha_convocatoria:%d/%m/%Y} para {self.version}"


class ResultadoRatificacion(models.TextChoices):
    RATIFICADO = "RATIFICADO", "Ratificado"
    RECHAZADO = "RECHAZADO", "Rechazado"


class Ratificacion(models.Model):
    version = models.OneToOneField(
        VersionPresupuesto, on_delete=models.PROTECT, related_name="ratificacion"
    )
    fecha_sesion = models.DateField()
    resultado = models.CharField(max_length=10, choices=ResultadoRatificacion.choices)
    referencia_acta = models.CharField(max_length=300)
    observaciones = models.TextField(blank=True)
    convocatoria = models.ForeignKey(
        Convocatoria, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    registrada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    rol = models.CharField(max_length=30, blank=True)
    registrada_en = models.DateTimeField(default=timezone.now)
    es_demo = models.BooleanField(default=False)

    class Meta:
        verbose_name = "ratificación"
        verbose_name_plural = "ratificaciones"

    def __str__(self) -> str:
        return f"{self.get_resultado_display()} el {self.fecha_sesion:%d/%m/%Y}"
