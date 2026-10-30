"""¿Está completa la memoria? (regla V-008). No depende del motor de validaciones."""

from dataclasses import dataclass, field

from apps.presupuesto.models import VersionPresupuesto

from .configuracion import ParametrosAnexos, SeccionCfg, parametros_de_version
from .models import SeccionMemoria


@dataclass
class EstadoSeccion:
    cfg: SeccionCfg
    texto: str
    pendiente_revision: bool
    problemas: list[str] = field(default_factory=list)

    @property
    def completa(self) -> bool:
        return not self.problemas


def textos_de(version: VersionPresupuesto) -> dict[str, SeccionMemoria]:
    return {s.clave: s for s in SeccionMemoria.objects.filter(version=version)}


def estado_secciones(
    version: VersionPresupuesto, params: ParametrosAnexos | None = None
) -> list[EstadoSeccion]:
    """Estado de cada sección aplicable a la versión, con los motivos si no está terminada."""
    params = params or parametros_de_version(version)
    guardadas = textos_de(version)
    salida = []
    for cfg in params.aplicables(version.ejercicio.hay_proceso_electoral):
        g = guardadas.get(cfg.clave)
        texto = g.texto.strip() if g else ""
        estado = EstadoSeccion(cfg, texto, bool(g and g.pendiente_revision))
        salida.append(estado)
        if cfg.solo_automatica:
            continue
        if not texto:
            if cfg.obligatoria:
                estado.problemas.append(f"Falta escribir la sección «{cfg.titulo}».")
            continue
        if cfg.longitud_minima and len(texto) < cfg.longitud_minima:
            estado.problemas.append(
                f"La sección «{cfg.titulo}» tiene {len(texto)} caracteres y debe tener "
                f"al menos {cfg.longitud_minima}."
            )
        marcas = [m for m in params.marcas_pendiente if m in texto]
        if marcas:
            estado.problemas.append(
                f"La sección «{cfg.titulo}» aún contiene «{marcas[0]}»: queda algo por completar."
            )
        if estado.pendiente_revision:
            estado.problemas.append(
                f"La sección «{cfg.titulo}» viene de otra versión y está pendiente de revisar."
            )
    return salida


def problemas_memoria(
    version: VersionPresupuesto, params: ParametrosAnexos | None = None
) -> list[str]:
    return [p for e in estado_secciones(version, params) for p in e.problemas]
