"""Motor de validaciones: ejecuta las reglas y devuelve un resultado único."""

from datetime import date

from apps.presupuesto.configuracion import (
    ConfiguracionVersion,
    ErrorConfiguracion,
    ReglasOrganicasCfg,
)
from apps.presupuesto.models import VersionPresupuesto

from . import reglas_l, reglas_o, reglas_v
from .contexto import construir_contexto
from .tipos import Gravedad, Incidencia, Regla, ResultadoValidacion

_B, _A = Gravedad.BLOQUEANTE, Gravedad.AVISO
_LEGAL = "Parámetros en config/parametros_legales.yaml; norma por verificar contra el BOE"

CATALOGO: tuple[Regla, ...] = (
    Regla("V-001", "Los meses suman el importe anual", _B, "CLAUDE.md §8.1", reglas_v.v001),
    Regla(
        "V-002",
        "Los totales de capítulo coinciden con sus líneas",
        _B,
        "CLAUDE.md §8.1",
        reglas_v.v002,
    ),
    Regla(
        "V-003",
        "Toda línea tiene cuenta del PGC válida",
        _B,
        "CLAUDE.md §8.1 y §3.3",
        reglas_v.v003,
    ),
    Regla(
        "V-004",
        "Toda línea tiene hipótesis y responsable",
        _B,
        "CLAUDE.md §8.1 y §6.4",
        reglas_v.v004,
    ),
    Regla(
        "V-005",
        "Importes con dos decimales y sin negativos injustificados",
        _B,
        "CLAUDE.md §8.1",
        reglas_v.v005,
    ),
    Regla(
        "V-006",
        "Resultado explicado; el déficit exige plan de financiación",
        _B,
        "CLAUDE.md §8.1",
        reglas_v.v006,
    ),
    Regla(
        "V-007",
        "Variación alta respecto al ejercicio anterior, justificada",
        _A,
        "CLAUDE.md §8.1",
        reglas_v.v007,
    ),
    Regla(
        "L-001",
        "Donaciones: límite por donante, identificación y tipo de persona",
        _B,
        "LO 8/2007 (CLAUDE.md §3.1). " + _LEGAL,
        reglas_l.l001,
    ),
    Regla(
        "L-002",
        "Sin ingresos de fuentes prohibidas",
        _B,
        "LO 8/2007 (CLAUDE.md §3.1). " + _LEGAL,
        reglas_l.l002,
    ),
    Regla(
        "L-003",
        "Aportaciones de cargos identificadas y dentro del límite",
        _B,
        "LO 8/2007 (CLAUDE.md §3.1). " + _LEGAL,
        reglas_l.l003,
    ),
    Regla(
        "L-004",
        "El gasto electoral no supera el límite legal",
        _B,
        "LOREG, LO 5/1985 (CLAUDE.md §3.1). " + _LEGAL,
        reglas_l.l004,
    ),
    Regla(
        "L-005",
        "Endeudamiento compatible con las condiciones de crédito",
        _B,
        "LO 8/2007 (CLAUDE.md §3.1). " + _LEGAL,
        reglas_l.l005,
    ),
    Regla(
        "L-006",
        "Estructura conforme al cuadro de cuentas validado",
        _B,
        "PGC y adaptación sectorial (CLAUDE.md §3.1)",
        reglas_l.l006,
    ),
    Regla(
        "L-007",
        "Parámetros legales verificados y vigentes",
        _B,
        "CLAUDE.md §3 (regla de oro)",
        reglas_l.l007,
    ),
    Regla(
        "L-008",
        "Donaciones y aportaciones que hay que notificar al Tribunal de Cuentas",
        _A,
        "LO 8/2007, arts. 5.Dos y 8.Tres (extracto aportado por el Tesorero). " + _LEGAL,
        reglas_l.l008,
    ),
    Regla(
        "L-009",
        "Identificar al transmitente en operaciones de actividades propias de umbral o más",
        _B,
        "LO 8/2007, art. 6.Tres (extracto aportado por el Tesorero). " + _LEGAL,
        reglas_l.l009,
    ),
    Regla(
        "L-010",
        "Sin donaciones de contratistas públicos",
        _B,
        "LO 8/2007, art. 4.Dos.a (extracto aportado por el Tesorero). " + _LEGAL,
        reglas_l.l010,
    ),
    Regla(
        "L-011",
        "Sin donaciones finalistas ni revocables",
        _B,
        "LO 8/2007, art. 5.Uno.a (extracto aportado por el Tesorero). " + _LEGAL,
        reglas_l.l011,
    ),
)

CATALOGO_ORGANICAS: tuple[Regla, ...] = (
    Regla(
        "O-001",
        "La CP alcanza quórum y mayoría",
        _B,
        "Estatutos (config/reglas_organicas.yaml)",
        reglas_o.o001,
    ),
    Regla(
        "O-002",
        "Ratificación con fecha, resultado y acta",
        _B,
        "CLAUDE.md §4 y §8.3",
        reglas_o.o002,
    ),
    Regla(
        "O-003",
        "Quien propone no vota (si el reglamento lo impide)",
        _B,
        "Reglamento interno (config/reglas_organicas.yaml)",
        reglas_o.o003,
    ),
    Regla(
        "O-004",
        "Convocatoria de la Junta registrada antes de ratificar",
        _A,
        "CLAUDE.md §8.3",
        reglas_o.o004,
    ),
)


def validar_version(
    version: VersionPresupuesto,
    *,
    cfg: ConfiguracionVersion | None = None,
    hoy: date | None = None,
) -> ResultadoValidacion:
    """Ejecuta las reglas V y L sobre una versión."""
    resultado = ResultadoValidacion()
    try:
        ctx = construir_contexto(version, cfg=cfg, hoy=hoy)
    except ErrorConfiguracion as error:
        resultado.incidencias.append(
            Incidencia("L-007", Gravedad.BLOQUEANTE, f"La configuración no se puede leer: {error}")
        )
        return resultado
    for regla in CATALOGO:
        resultado.reglas_ejecutadas.append(regla.codigo)
        resultado.incidencias.extend(regla.funcion(ctx))
    return resultado


def validar_votacion(
    votacion: reglas_o.DatosVotacion, organicas: ReglasOrganicasCfg
) -> ResultadoValidacion:
    """Reglas O-001 y O-003 para la votación de la Comisión Permanente."""
    res = ResultadoValidacion(reglas_ejecutadas=["O-001", "O-003"])
    res.incidencias += reglas_o.o001(votacion, organicas)
    res.incidencias += reglas_o.o003(votacion, organicas)
    return res


def validar_ratificacion(datos: reglas_o.DatosRatificacion, hoy: date) -> ResultadoValidacion:
    """Reglas O-002 y O-004 para el registro de la ratificación."""
    res = ResultadoValidacion(reglas_ejecutadas=["O-002", "O-004"])
    res.incidencias += reglas_o.o002(datos, hoy)
    res.incidencias += reglas_o.o004(datos)
    return res
