"""Importación de la ejecución real desde CSV (CLAUDE.md §7.4).

El sistema no sustituye a la contabilidad: solo la consume. El fichero tiene tres columnas
separadas por «;»: ``codigo;mes;importe`` (importe con coma decimal: 1.234,56). Se valida todo
antes de guardar y es todo o nada: si alguna fila falla, no se guarda nada y se listan los errores.
Una importación nunca se edita ni se borra: se anula con motivo (y hay un disparador que lo exige).
"""

import csv
import hashlib
import io
from dataclasses import dataclass
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.auditoria.servicios import Contexto, registrar
from apps.presupuesto.dinero import parsear_importe_es
from apps.presupuesto.models import Ejercicio, Linea
from apps.presupuesto.servicios import exigir_tesorero

from .models import EjecucionReal, EstadoImportacion, ImportacionEjecucion

CABECERA = ["codigo", "mes", "importe"]
MAX_BYTES = 2_000_000
MAX_FILAS = 20_000
MAX_ERRORES_MOSTRADOS = 30


@dataclass(frozen=True)
class FilaReal:
    codigo: str
    mes: int
    importe: Decimal


def codigos_de_lineas(ejercicio: Ejercicio) -> set[str]:
    """Códigos de línea que existen en alguna versión del ejercicio (no anuladas)."""
    return set(
        Linea.objects.filter(version__ejercicio=ejercicio, anulada=False).values_list(
            "codigo", flat=True
        )
    )


def _decodificar(contenido: bytes) -> str:
    try:
        return contenido.decode("utf-8-sig")
    except UnicodeDecodeError:
        return contenido.decode("latin-1")


def leer_csv(
    contenido: bytes, codigos_validos: set[str], mes_corte: int
) -> tuple[list[FilaReal], list[str]]:
    """Valida el CSV. Devuelve las filas correctas y la lista de errores (vacía si todo va bien)."""
    errores: list[str] = []
    if len(contenido) > MAX_BYTES:
        return [], [f"El fichero pesa más de {MAX_BYTES // 1_000_000} MB."]
    texto = _decodificar(contenido)
    lector = csv.reader(io.StringIO(texto), delimiter=";")
    filas: list[FilaReal] = []
    vistas: dict[tuple[str, int], int] = {}
    cabecera_vista = False
    for n, fila in enumerate(lector, start=1):
        if not any(c.strip() for c in fila):
            continue
        if not cabecera_vista:
            cabecera_vista = True
            if [c.strip().lower() for c in fila] != CABECERA:
                return [], [
                    "La primera fila debe ser la cabecera «codigo;mes;importe» "
                    "(descarga la plantilla)."
                ]
            continue
        if len(filas) + len(errores) >= MAX_FILAS:
            errores.append(f"Demasiadas filas (máximo {MAX_FILAS}).")
            break
        if len(fila) != 3:
            errores.append(
                f"Fila {n}: debe tener 3 columnas separadas por «;» y tiene {len(fila)}."
            )
            continue
        codigo, mes_txt, importe_txt = (c.strip() for c in fila)
        fila_ok = True
        if codigo not in codigos_validos:
            errores.append(f"Fila {n}: el código de línea «{codigo}» no existe en este ejercicio.")
            fila_ok = False
        try:
            mes = int(mes_txt)
        except ValueError:
            errores.append(f"Fila {n}: el mes «{mes_txt}» no es un número.")
            continue
        if not 1 <= mes <= 12:
            errores.append(f"Fila {n}: el mes debe estar entre 1 y 12 y es {mes}.")
            fila_ok = False
        elif mes > mes_corte:
            errores.append(f"Fila {n}: el mes {mes} es posterior al mes de corte ({mes_corte}).")
            fila_ok = False
        try:
            importe = parsear_importe_es(importe_txt)
        except ValueError as error:
            errores.append(f"Fila {n}: {error}.")
            continue
        if (codigo, mes) in vistas:
            errores.append(
                f"Fila {n}: «{codigo}» del mes {mes} ya aparece en la fila {vistas[(codigo, mes)]}."
            )
            fila_ok = False
        vistas.setdefault((codigo, mes), n)
        if fila_ok:
            filas.append(FilaReal(codigo, mes, importe))
    if not cabecera_vista:
        return [], ["El fichero está vacío."]
    if not filas and not errores:
        errores.append("El fichero no tiene ninguna fila de datos.")
    return filas, errores


@transaction.atomic
def importar_ejecucion(
    contexto: Contexto,
    ejercicio: Ejercicio,
    *,
    nombre_fichero: str,
    contenido: bytes,
    mes_corte: int,
) -> ImportacionEjecucion:
    exigir_tesorero(contexto)
    if not 1 <= mes_corte <= 12:
        raise ValidationError("El mes de corte debe estar entre 1 y 12.")
    filas, errores = leer_csv(contenido, codigos_de_lineas(ejercicio), mes_corte)
    if errores:
        mostrados = errores[:MAX_ERRORES_MOSTRADOS]
        if len(errores) > MAX_ERRORES_MOSTRADOS:
            mostrados.append(f"… y {len(errores) - MAX_ERRORES_MOSTRADOS} errores más.")
        raise ValidationError(["No se ha importado nada: el fichero tiene errores.", *mostrados])
    huella = hashlib.sha256(contenido).hexdigest()
    imp = ImportacionEjecucion.objects.create(
        ejercicio=ejercicio,
        mes_corte=mes_corte,
        nombre_fichero=nombre_fichero[:255],
        huella_fichero=huella,
        filas=len(filas),
        importado_por=contexto.usuario,
        es_demo=ejercicio.es_demo,
    )
    EjecucionReal.objects.bulk_create(
        EjecucionReal(
            importacion=imp,
            codigo_linea=f.codigo,
            mes=f.mes,
            importe=f.importe,
            es_demo=ejercicio.es_demo,
        )
        for f in filas
    )
    registrar(
        contexto,
        accion="ejecucion.importar",
        entidad="ImportacionEjecucion",
        entidad_id=imp.pk,
        despues={
            "ejercicio": ejercicio.pk,
            "mes_corte": mes_corte,
            "fichero": imp.nombre_fichero,
            "huella": huella,
            "filas": len(filas),
        },
        es_demo=ejercicio.es_demo,
    )
    return imp


@transaction.atomic
def anular_importacion(
    contexto: Contexto, importacion: ImportacionEjecucion, motivo: str
) -> ImportacionEjecucion:
    exigir_tesorero(contexto)
    importacion.refresh_from_db()
    if importacion.estado != EstadoImportacion.ACTIVA:
        raise ValidationError("Esta importación ya está anulada.")
    if not motivo.strip():
        raise ValidationError("Anular una importación exige un motivo.")
    importacion.estado = EstadoImportacion.ANULADA
    importacion.motivo_anulacion = motivo.strip()
    importacion.anulada_por = contexto.usuario
    importacion.anulada_en = timezone.now()
    importacion.save(update_fields=["estado", "motivo_anulacion", "anulada_por", "anulada_en"])
    registrar(
        contexto,
        accion="ejecucion.anular",
        entidad="ImportacionEjecucion",
        entidad_id=importacion.pk,
        antes={"estado": "ACTIVA"},
        despues={"estado": "ANULADA"},
        motivo=importacion.motivo_anulacion,
        es_demo=importacion.es_demo,
    )
    return importacion


def importacion_vigente(ejercicio: Ejercicio) -> ImportacionEjecucion | None:
    """La última importación activa: la que usa la comparativa."""
    return (
        ImportacionEjecucion.objects.filter(ejercicio=ejercicio, estado=EstadoImportacion.ACTIVA)
        .order_by("-importado_en", "-id")
        .first()
    )


def plantilla_csv(ejercicio: Ejercicio) -> str:
    """CSV de ejemplo con una fila por línea del ejercicio (mes 1, importe 0,00)."""
    salida = io.StringIO()
    escritor = csv.writer(salida, delimiter=";", lineterminator="\r\n")
    escritor.writerow(CABECERA)
    for codigo in sorted(codigos_de_lineas(ejercicio)):
        escritor.writerow([codigo, 1, "0,00"])
    return salida.getvalue()
