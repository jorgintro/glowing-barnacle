"""Modelo presupuestario (CLAUDE.md §6 y §10).

Reglas que viven aquí:
* Todo el dinero es ``DecimalField`` con dos decimales.
* Solo una versión en ``BORRADOR`` admite cambios de contenido. Esta protección de la
  aplicación se refuerza en la Fase 4 con restricciones en la propia base de datos.
* Nada se borra: las líneas se anulan con motivo.
"""

from typing import Any

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from .errores import RegistroNoBorrable, VersionNoEditable
from .estados import ESTADOS_EDITABLES, EstadoVersion


class Tipo(models.TextChoices):
    INGRESO = "INGRESO", "Ingreso"
    GASTO = "GASTO", "Gasto"


class Dimension(models.TextChoices):
    ORDINARIO = "ORDINARIO", "Ordinario"
    CAMPANA = "CAMPANA", "Campaña"
    GRUPO_MUNICIPAL = "GRUPO_MUNICIPAL", "Grupo municipal"


class TipoLinea(models.TextChoices):
    RECURRENTE = "RECURRENTE", "Recurrente"
    EXTRAORDINARIO = "EXTRAORDINARIO", "Extraordinario"
    CONDICIONADO = "CONDICIONADO", "Condicionado"


class Confianza(models.TextChoices):
    ALTA = "ALTA", "Alta"
    MEDIA = "MEDIA", "Media"
    BAJA = "BAJA", "Baja"


# --------------------------------------------------------------------- catálogo


class CuentaPGC(models.Model):
    codigo = models.CharField(max_length=10, unique=True)
    denominacion = models.CharField(max_length=200)
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ["codigo"]
        verbose_name = "cuenta del PGC"
        verbose_name_plural = "cuentas del PGC"

    def __str__(self) -> str:
        return f"{self.codigo} · {self.denominacion}"


class Capitulo(models.Model):
    codigo = models.CharField(max_length=10, unique=True)
    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    denominacion = models.CharField(max_length=200)
    orden = models.PositiveSmallIntegerField()
    solo_con_proceso_electoral = models.BooleanField(default=False)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["tipo", "orden"]
        verbose_name = "capítulo"
        verbose_name_plural = "capítulos"

    def __str__(self) -> str:
        return f"{self.codigo} {self.denominacion}"


class Partida(models.Model):
    capitulo = models.ForeignKey(Capitulo, on_delete=models.PROTECT, related_name="partidas")
    codigo = models.CharField(max_length=15, unique=True)
    denominacion = models.CharField(max_length=200)
    orden = models.PositiveSmallIntegerField()
    cuentas = models.ManyToManyField(CuentaPGC, related_name="partidas")
    dimension_por_defecto = models.CharField(
        max_length=20, choices=Dimension.choices, default=Dimension.ORDINARIO
    )
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ["capitulo__tipo", "capitulo__orden", "orden"]
        verbose_name = "partida"
        verbose_name_plural = "partidas"

    def __str__(self) -> str:
        return f"{self.codigo} {self.denominacion}"


class ParametroLegal(models.Model):
    """Reflejo en base de datos de ``config/parametros_legales.yaml`` (el fichero manda)."""

    clave = models.CharField(max_length=80, unique=True)
    descripcion = models.TextField()
    unidad = models.CharField(max_length=20)
    regla = models.CharField(max_length=10, blank=True)
    norma_orientativa = models.CharField(max_length=200, blank=True)
    valor = models.JSONField(null=True, blank=True)
    referencia_normativa = models.CharField(max_length=300, blank=True)
    fecha_verificacion = models.DateField(null=True, blank=True)
    verificador = models.CharField(max_length=150, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["clave"]
        verbose_name = "parámetro legal"
        verbose_name_plural = "parámetros legales"

    def __str__(self) -> str:
        return self.clave

    @property
    def verificado(self) -> bool:
        return (
            self.valor is not None
            and bool(self.referencia_normativa.strip())
            and self.fecha_verificacion is not None
            and bool(self.verificador.strip())
        )


# ------------------------------------------------------------- ejercicio y versión


class Ejercicio(models.Model):
    anio = models.PositiveSmallIntegerField("año")
    nombre = models.CharField(max_length=120, blank=True)
    hay_proceso_electoral = models.BooleanField(
        "hay proceso electoral en el ejercicio", default=False
    )
    parametros_aplicados = models.JSONField(null=True, blank=True)
    creado = models.DateTimeField(default=timezone.now)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    es_demo = models.BooleanField(default=False)

    class Meta:
        ordering = ["-anio", "es_demo"]
        verbose_name = "ejercicio"
        verbose_name_plural = "ejercicios"
        constraints = [
            models.UniqueConstraint(fields=["anio", "es_demo"], name="un_ejercicio_por_anio"),
        ]

    def __str__(self) -> str:
        return self.nombre or f"Ejercicio {self.anio}"

    @property
    def ultima_version(self) -> "VersionPresupuesto | None":
        return self.versiones.order_by("-numero").first()


class VersionPresupuesto(models.Model):
    ejercicio = models.ForeignKey(Ejercicio, on_delete=models.PROTECT, related_name="versiones")
    numero = models.PositiveSmallIntegerField()
    estado = models.CharField(
        max_length=20, choices=EstadoVersion.choices, default=EstadoVersion.BORRADOR
    )
    hash = models.CharField(max_length=64, blank=True)
    autor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    fecha = models.DateTimeField(default=timezone.now)
    motivo = models.TextField(blank=True)
    version_origen = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="derivadas"
    )
    es_prorroga = models.BooleanField(default=False)
    explicacion_resultado = models.TextField(
        blank=True, help_text="Explica el resultado presupuestario (regla V-006)."
    )
    plan_financiacion = models.TextField(
        blank=True, help_text="Obligatorio si el resultado es un déficit (regla V-006)."
    )
    endeudamiento_previsto = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        help_text="Endeudamiento nuevo previsto en el ejercicio (regla L-005).",
    )
    es_demo = models.BooleanField(default=False)

    class Meta:
        ordering = ["ejercicio", "numero"]
        verbose_name = "versión del presupuesto"
        verbose_name_plural = "versiones del presupuesto"
        constraints = [
            models.UniqueConstraint(fields=["ejercicio", "numero"], name="un_numero_por_ejercicio"),
            models.CheckConstraint(
                condition=Q(endeudamiento_previsto__gte=0), name="endeudamiento_no_negativo"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.ejercicio} · v{self.numero}"

    @property
    def editable(self) -> bool:
        return self.estado in ESTADOS_EDITABLES


# ------------------------------------------------------------------------ líneas


def _exigir_editable(version: VersionPresupuesto) -> None:
    if not version.editable:
        raise VersionNoEditable(
            f"La versión {version} está en estado {version.get_estado_display()} y es de solo "
            "lectura. Los cambios exigen una nueva versión (modificación presupuestaria)."
        )


class _SinBorrado(models.Model):
    class Meta:
        abstract = True

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise RegistroNoBorrable(
            "Los registros del presupuesto no se borran: se anulan con motivo."
        )


class Linea(_SinBorrado):
    version = models.ForeignKey(VersionPresupuesto, on_delete=models.PROTECT, related_name="lineas")
    partida = models.ForeignKey(Partida, on_delete=models.PROTECT, related_name="lineas")
    codigo = models.CharField(max_length=25)
    denominacion = models.CharField(max_length=200)
    cuenta_pgc = models.ForeignKey(
        CuentaPGC, null=True, blank=True, on_delete=models.PROTECT, related_name="lineas"
    )
    importe_anual = models.DecimalField(max_digits=14, decimal_places=2)
    tipo = models.CharField(max_length=20, choices=TipoLinea.choices, default=TipoLinea.RECURRENTE)
    dimension = models.CharField(
        max_length=20, choices=Dimension.choices, default=Dimension.ORDINARIO
    )
    importe_ejercicio_anterior = models.DecimalField(
        null=True, blank=True, max_digits=14, decimal_places=2
    )
    justificacion_variacion = models.TextField(blank=True)
    responsable = models.CharField(max_length=120, blank=True)
    origen_ingreso = models.CharField(
        max_length=80,
        blank=True,
        help_text="Tipo de fuente del ingreso; se contrasta con las fuentes prohibidas (L-002).",
    )
    es_ajuste = models.BooleanField(default=False)
    justificacion_ajuste = models.TextField(blank=True)
    anulada = models.BooleanField(default=False)
    motivo_anulacion = models.TextField(blank=True)
    anulada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    fecha_anulacion = models.DateTimeField(null=True, blank=True)
    creada = models.DateTimeField(default=timezone.now)
    modificada = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["version", "codigo"]
        verbose_name = "línea presupuestaria"
        verbose_name_plural = "líneas presupuestarias"
        constraints = [
            models.UniqueConstraint(fields=["version", "codigo"], name="un_codigo_por_version"),
            models.CheckConstraint(
                condition=Q(importe_anual__gte=0) | Q(es_ajuste=True),
                name="importe_no_negativo_salvo_ajuste",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.codigo} {self.denominacion}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        _exigir_editable(self.version)
        super().save(*args, **kwargs)


class ImporteMensual(_SinBorrado):
    linea = models.ForeignKey(Linea, on_delete=models.PROTECT, related_name="importes_mensuales")
    mes = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(12)])
    importe = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        ordering = ["linea", "mes"]
        verbose_name = "importe mensual"
        verbose_name_plural = "importes mensuales"
        constraints = [
            models.UniqueConstraint(fields=["linea", "mes"], name="un_importe_por_mes"),
            models.CheckConstraint(
                condition=Q(mes__gte=1) & Q(mes__lte=12), name="mes_entre_1_y_12"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.linea.codigo} · mes {self.mes}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        _exigir_editable(self.linea.version)
        super().save(*args, **kwargs)


class Hipotesis(_SinBorrado):
    linea = models.OneToOneField(Linea, on_delete=models.PROTECT, related_name="hipotesis")
    texto = models.TextField()
    fuente = models.CharField(max_length=300)
    confianza = models.CharField(max_length=10, choices=Confianza.choices, blank=True)

    class Meta:
        verbose_name = "hipótesis"
        verbose_name_plural = "hipótesis"

    def __str__(self) -> str:
        return f"Hipótesis de {self.linea.codigo}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        _exigir_editable(self.linea.version)
        super().save(*args, **kwargs)


class Comentario(models.Model):
    """Los comentarios no son cifras: se admiten también en versiones no editables."""

    version = models.ForeignKey(
        VersionPresupuesto, on_delete=models.PROTECT, related_name="comentarios"
    )
    linea = models.ForeignKey(
        Linea, null=True, blank=True, on_delete=models.PROTECT, related_name="comentarios"
    )
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    rol_autor = models.CharField(max_length=30, blank=True)
    texto = models.TextField()
    fecha = models.DateTimeField(default=timezone.now)
    resuelto = models.BooleanField(default=False)
    resuelto_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    fecha_resuelto = models.DateTimeField(null=True, blank=True)
    es_demo = models.BooleanField(default=False)

    class Meta:
        ordering = ["fecha"]
        verbose_name = "comentario"
        verbose_name_plural = "comentarios"

    def __str__(self) -> str:
        return f"Comentario de {self.autor} en {self.version}"


# ------------------------------------------------------------ donantes y aportaciones


class TipoPersona(models.TextChoices):
    FISICA = "FISICA", "Persona física"
    JURIDICA = "JURIDICA", "Persona jurídica"


class Donante(models.Model):
    """Persona identificada que dona o aporta. Datos mínimos: nombre, NIF y tipo de persona.

    Se identifica a los donantes por decisión del Tesorero (CLAUDE.md §13.3 pide datos mínimos).
    No se borra: se da de baja con motivo. Ver ``docs/proteccion_datos.md``.
    """

    nombre = models.CharField(max_length=200)
    nif = models.CharField("NIF/NIE/CIF", max_length=15)
    tipo_persona = models.CharField(
        max_length=10, choices=TipoPersona.choices, default=TipoPersona.FISICA
    )
    activo = models.BooleanField(default=True)
    motivo_baja = models.TextField(blank=True)
    creado = models.DateTimeField(default=timezone.now)
    es_demo = models.BooleanField(default=False)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "donante"
        verbose_name_plural = "donantes"
        constraints = [
            models.UniqueConstraint(fields=["nif", "es_demo"], name="un_donante_por_nif"),
        ]

    def __str__(self) -> str:
        return f"{self.nombre} ({self.nif})"


class Donacion(_SinBorrado):
    """Donación o aportación prevista de un donante, imputada a una línea de ingresos."""

    version = models.ForeignKey(
        VersionPresupuesto, on_delete=models.PROTECT, related_name="donaciones"
    )
    linea = models.ForeignKey(Linea, on_delete=models.PROTECT, related_name="donaciones")
    donante = models.ForeignKey(Donante, on_delete=models.PROTECT, related_name="donaciones")
    importe = models.DecimalField(max_digits=14, decimal_places=2)
    anulada = models.BooleanField(default=False)
    motivo_anulacion = models.TextField(blank=True)
    creada = models.DateTimeField(default=timezone.now)
    es_demo = models.BooleanField(default=False)

    class Meta:
        ordering = ["version", "linea", "donante"]
        verbose_name = "donación prevista"
        verbose_name_plural = "donaciones previstas"
        constraints = [
            models.CheckConstraint(condition=Q(importe__gt=0), name="donacion_importe_positivo"),
        ]

    def __str__(self) -> str:
        return f"{self.donante} → {self.linea.codigo}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        _exigir_editable(self.version)
        super().save(*args, **kwargs)
