"""Anexos de cada versión: memoria explicativa y plan de tesorería (CLAUDE.md §7.1 y §7.2).

* ``SeccionMemoriaCfg`` y ``ParametrosAnexosCfg``: configuración editable desde el panel (solo el
  Tesorero). Hay un juego para la organización real y otro para la demostración (``es_demo``).
* ``SeccionMemoria``: el texto de cada sección en una versión. Forma parte del contenido sellado:
  cuando la versión deja de ser borrador, un disparador de PostgreSQL impide tocarlo.
"""

from typing import Any

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.presupuesto.models import VersionPresupuesto


class ContenidoAutomatico(models.TextChoices):
    NINGUNO = "NINGUNO", "Solo texto escrito a mano"
    RESUMEN = "RESUMEN", "Cifras totales y variaciones (automático)"
    HIPOTESIS = "HIPOTESIS", "Hipótesis por capítulo (automático)"
    RIESGOS = "RIESGOS", "Líneas de confianza baja y condicionadas (automático)"
    CAMPANA = "CAMPANA", "Presupuesto de campaña: límite, gasto y financiación (automático)"
    CUMPLIMIENTO = "CUMPLIMIENTO", "Comprobaciones y parámetros (solo automático)"


class SeccionMemoriaCfg(models.Model):
    """Definición de una sección de la memoria (título, orden, ayuda, plantilla, exigencias)."""

    clave = models.SlugField(max_length=40)
    titulo = models.CharField(max_length=150)
    orden = models.PositiveSmallIntegerField(default=0)
    contenido = models.CharField(
        max_length=20, choices=ContenidoAutomatico.choices, default=ContenidoAutomatico.NINGUNO
    )
    obligatoria = models.BooleanField(default=True)
    activa = models.BooleanField(default=True)
    solo_con_proceso_electoral = models.BooleanField(default=False)
    longitud_minima = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Caracteres mínimos para dar la sección por escrita. Vacío = sin mínimo.",
    )
    ayuda = models.TextField(blank=True)
    plantilla = models.TextField(blank=True)
    es_demo = models.BooleanField(default=False)

    class Meta:
        ordering = ["orden", "clave"]
        verbose_name = "sección de la memoria (configuración)"
        verbose_name_plural = "secciones de la memoria (configuración)"
        constraints = [
            models.UniqueConstraint(fields=["clave", "es_demo"], name="una_seccion_por_clave"),
        ]

    def __str__(self) -> str:
        return self.titulo

    @property
    def solo_automatica(self) -> bool:
        return self.contenido == ContenidoAutomatico.CUMPLIMIENTO


class ParametrosAnexosCfg(models.Model):
    """Parámetros de la memoria y del plan de tesorería (un registro por juego real/demo)."""

    variaciones_destacadas = models.PositiveSmallIntegerField(default=5)
    marcas_pendiente = models.TextField(
        default="[COMPLETAR\nPENDIENTE DE REVISAR",
        help_text="Una por línea. Si alguna aparece en una sección, la memoria sigue incompleta.",
    )
    saldo_minimo_tesoreria = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True
    )
    reduccion_ingresos_alta = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    reduccion_ingresos_media = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    reduccion_ingresos_baja = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    reduccion_gastos_recurrente = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    reduccion_gastos_extraordinario = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    reduccion_gastos_condicionado = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    porcentaje_aviso_limite_campana = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="A partir de este % del límite de gasto electoral se avisa. Vacío = sin aviso.",
    )
    semaforo_ambar_pct = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    semaforo_rojo_pct = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    semaforo_importe_minimo = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True
    )
    es_demo = models.BooleanField(default=False)

    class Meta:
        verbose_name = "parámetros de los anexos"
        verbose_name_plural = "parámetros de los anexos"
        constraints = [
            models.UniqueConstraint(fields=["es_demo"], name="un_juego_de_parametros"),
        ]

    def __str__(self) -> str:
        return "Parámetros de los anexos" + (" (demostración)" if self.es_demo else "")

    @property
    def marcas(self) -> list[str]:
        return [m.strip() for m in self.marcas_pendiente.splitlines() if m.strip()]


class SeccionMemoria(models.Model):
    """Texto de una sección de la memoria en una versión (parte del contenido sellado)."""

    version = models.ForeignKey(
        VersionPresupuesto, on_delete=models.PROTECT, related_name="secciones_memoria"
    )
    clave = models.SlugField(max_length=40)
    texto = models.TextField(blank=True)
    pendiente_revision = models.BooleanField(
        default=False,
        help_text="Copiada de otra versión: el Tesorero debe revisarla antes de proponer.",
    )
    actualizada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    actualizada_en = models.DateTimeField(default=timezone.now)
    es_demo = models.BooleanField(default=False)

    class Meta:
        ordering = ["version", "clave"]
        verbose_name = "sección de la memoria"
        verbose_name_plural = "secciones de la memoria"
        constraints = [
            models.UniqueConstraint(fields=["version", "clave"], name="una_seccion_por_version"),
        ]

    def __str__(self) -> str:
        return f"{self.version} · {self.clave}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.es_demo = self.version.es_demo
        super().save(*args, **kwargs)


class ProcesoElectoral(models.Model):
    """Datos del proceso electoral de una versión (anexo de campaña, CLAUDE.md §7.3).

    Forma parte del contenido sellado: con la versión fuera de BORRADOR es de solo lectura.
    """

    version = models.OneToOneField(
        VersionPresupuesto, on_delete=models.PROTECT, related_name="proceso_electoral"
    )
    denominacion = models.CharField(
        "proceso electoral",
        max_length=200,
        blank=True,
        help_text="Por ejemplo, «Elecciones locales».",
    )
    fecha_convocatoria = models.DateField(null=True, blank=True)
    fecha_elecciones = models.DateField(null=True, blank=True)
    fecha_proclamacion = models.DateField("fecha de proclamación de electos", null=True, blank=True)
    habitantes_derecho = models.PositiveIntegerField("habitantes de derecho", null=True, blank=True)
    provincias_adicional = models.PositiveSmallIntegerField(
        "provincias con gasto adicional", default=0
    )
    subvencion_envio_aplicable = models.BooleanField(
        "se cumplen los requisitos de la subvención por envío directo", default=False
    )
    electores_envio = models.PositiveIntegerField(
        "electores del envío directo", null=True, blank=True
    )
    concejales_previstos = models.PositiveIntegerField(null=True, blank=True)
    votos_previstos = models.PositiveIntegerField(null=True, blank=True)
    observaciones = models.TextField(blank=True)
    actualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    actualizado_en = models.DateTimeField(default=timezone.now)
    es_demo = models.BooleanField(default=False)

    class Meta:
        verbose_name = "proceso electoral"
        verbose_name_plural = "procesos electorales"

    def __str__(self) -> str:
        return f"{self.version} · {self.denominacion or 'proceso electoral'}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.es_demo = self.version.es_demo
        super().save(*args, **kwargs)


class EstadoImportacion(models.TextChoices):
    ACTIVA = "ACTIVA", "Activa"
    ANULADA = "ANULADA", "Anulada"


class ImportacionEjecucion(models.Model):
    """Una carga de ejecución real. Nunca se edita ni se borra: se anula con motivo."""

    ejercicio = models.ForeignKey(
        "presupuesto.Ejercicio", on_delete=models.PROTECT, related_name="importaciones"
    )
    mes_corte = models.PositiveSmallIntegerField("mes de corte")
    nombre_fichero = models.CharField(max_length=255)
    huella_fichero = models.CharField(max_length=64)
    filas = models.PositiveIntegerField()
    importado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+"
    )
    importado_en = models.DateTimeField(default=timezone.now)
    estado = models.CharField(
        max_length=10, choices=EstadoImportacion.choices, default=EstadoImportacion.ACTIVA
    )
    motivo_anulacion = models.TextField(blank=True)
    anulada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    anulada_en = models.DateTimeField(null=True, blank=True)
    es_demo = models.BooleanField(default=False)

    class Meta:
        ordering = ["-importado_en", "-id"]
        verbose_name = "importación de ejecución real"
        verbose_name_plural = "importaciones de ejecución real"

    def __str__(self) -> str:
        return f"{self.ejercicio} · corte mes {self.mes_corte} · {self.nombre_fichero}"


class EjecucionReal(models.Model):
    """Importe real de una línea (por su código) en un mes, de una importación."""

    importacion = models.ForeignKey(
        ImportacionEjecucion, on_delete=models.PROTECT, related_name="registros"
    )
    codigo_linea = models.CharField(max_length=30)
    mes = models.PositiveSmallIntegerField()
    importe = models.DecimalField(max_digits=14, decimal_places=2)
    es_demo = models.BooleanField(default=False)

    class Meta:
        ordering = ["importacion", "codigo_linea", "mes"]
        verbose_name = "ejecución real"
        verbose_name_plural = "ejecución real"
        constraints = [
            models.UniqueConstraint(
                fields=["importacion", "codigo_linea", "mes"], name="un_dato_real_por_linea_y_mes"
            ),
            models.CheckConstraint(
                condition=models.Q(mes__gte=1, mes__lte=12), name="mes_real_entre_1_y_12"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.codigo_linea} · mes {self.mes}: {self.importe}"
