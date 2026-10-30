"""Inmutabilidad real en la base de datos (CLAUDE.md §10: «a nivel de base de datos»).

Disparadores de PostgreSQL que:
* rechazan cualquier cambio del contenido de una versión que no esté en BORRADOR;
* solo admiten las transiciones de estado válidas;
* hacen inalterables las transiciones, convocatorias, ratificaciones y votaciones cerradas.

Única excepción: el borrado de filas de demostración (``es_demo``) mientras el comando
``borrar_demo`` activa ``presupuesto.modo_demo`` en su propia transacción.
"""

from django.db import migrations

CREAR = r"""
CREATE FUNCTION flujo_modo_demo() RETURNS boolean AS $$
    SELECT COALESCE(current_setting('presupuesto.modo_demo', true), '') = 'on';
$$ LANGUAGE sql STABLE;

-- 1) Contenido de las versiones (líneas, importes mensuales, hipótesis, donaciones)
CREATE FUNCTION flujo_guardar_contenido() RETURNS trigger AS $$
DECLARE
    vid bigint;
    est text;
    demo boolean;
BEGIN
    IF TG_TABLE_NAME IN ('presupuesto_linea', 'presupuesto_donacion') THEN
        IF TG_OP = 'DELETE' THEN vid := OLD.version_id; ELSE vid := NEW.version_id; END IF;
    ELSE
        IF TG_OP = 'DELETE' THEN
            SELECT version_id INTO vid FROM presupuesto_linea WHERE id = OLD.linea_id;
        ELSE
            SELECT version_id INTO vid FROM presupuesto_linea WHERE id = NEW.linea_id;
        END IF;
    END IF;
    SELECT estado, es_demo INTO est, demo FROM presupuesto_versionpresupuesto WHERE id = vid;
    IF est IS NULL OR est = 'BORRADOR' THEN
        IF TG_OP = 'DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
    END IF;
    IF TG_OP = 'DELETE' AND demo AND flujo_modo_demo() THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'La versión % está en estado % y su contenido es de solo lectura (%)',
        vid, est, TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER flujo_contenido_linea
    BEFORE INSERT OR UPDATE OR DELETE ON presupuesto_linea
    FOR EACH ROW EXECUTE FUNCTION flujo_guardar_contenido();
CREATE TRIGGER flujo_contenido_importemensual
    BEFORE INSERT OR UPDATE OR DELETE ON presupuesto_importemensual
    FOR EACH ROW EXECUTE FUNCTION flujo_guardar_contenido();
CREATE TRIGGER flujo_contenido_hipotesis
    BEFORE INSERT OR UPDATE OR DELETE ON presupuesto_hipotesis
    FOR EACH ROW EXECUTE FUNCTION flujo_guardar_contenido();
CREATE TRIGGER flujo_contenido_donacion
    BEFORE INSERT OR UPDATE OR DELETE ON presupuesto_donacion
    FOR EACH ROW EXECUTE FUNCTION flujo_guardar_contenido();

-- 2) La propia versión: transiciones válidas y contenido inmutable
CREATE FUNCTION flujo_guardar_version() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.estado <> 'BORRADOR' THEN
            RAISE EXCEPTION 'Una versión nueva solo puede crearse en estado BORRADOR';
        END IF;
        RETURN NEW;
    END IF;
    IF TG_OP = 'DELETE' THEN
        IF OLD.es_demo AND flujo_modo_demo() THEN RETURN OLD; END IF;
        RAISE EXCEPTION 'Las versiones del presupuesto no se pueden borrar';
    END IF;

    IF NEW.estado <> OLD.estado THEN
        IF NOT (
            (OLD.estado, NEW.estado) IN (
                ('BORRADOR', 'PROPUESTO'), ('PROPUESTO', 'BORRADOR'),
                ('PROPUESTO', 'APROBADO_CP'), ('PROPUESTO', 'RECHAZADO'),
                ('APROBADO_CP', 'RATIFICADO_JG'), ('APROBADO_CP', 'RECHAZADO')
            )
            OR (OLD.estado = 'APROBADO_CP' AND NEW.estado = 'MODIFICADO'
                AND NEW.tipo_origen = 'MODIFICACION')
        ) THEN
            RAISE EXCEPTION 'Transición de estado no permitida: % -> %', OLD.estado, NEW.estado;
        END IF;
    END IF;

    IF OLD.estado <> 'BORRADOR' THEN
        IF (NEW.ejercicio_id, NEW.numero, NEW.motivo, NEW.version_origen_id, NEW.es_prorroga,
            NEW.tipo_origen, NEW.explicacion_resultado, NEW.plan_financiacion,
            NEW.endeudamiento_previsto, NEW.autor_id, NEW.fecha, NEW.es_demo)
           IS DISTINCT FROM
           (OLD.ejercicio_id, OLD.numero, OLD.motivo, OLD.version_origen_id, OLD.es_prorroga,
            OLD.tipo_origen, OLD.explicacion_resultado, OLD.plan_financiacion,
            OLD.endeudamiento_previsto, OLD.autor_id, OLD.fecha, OLD.es_demo) THEN
            RAISE EXCEPTION 'El contenido de una versión que no es borrador es de solo lectura';
        END IF;
        IF NEW.hash IS DISTINCT FROM OLD.hash AND NOT (NEW.estado = 'BORRADOR' AND NEW.hash = '') THEN
            RAISE EXCEPTION 'La huella de una versión sellada no se puede cambiar';
        END IF;
        IF NEW.proponente_id IS DISTINCT FROM OLD.proponente_id AND NEW.estado <> 'BORRADOR' THEN
            RAISE EXCEPTION 'El proponente de una versión sellada no se puede cambiar';
        END IF;
        IF NEW.requiere_junta IS DISTINCT FROM OLD.requiere_junta
           AND NOT (OLD.estado = 'PROPUESTO' AND NEW.estado = 'APROBADO_CP') THEN
            RAISE EXCEPTION 'Solo se decide si hace falta la Junta al aprobar la Comisión Permanente';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER flujo_version
    BEFORE INSERT OR UPDATE OR DELETE ON presupuesto_versionpresupuesto
    FOR EACH ROW EXECUTE FUNCTION flujo_guardar_version();

-- 3) Registros del flujo: solo se añaden
CREATE FUNCTION flujo_solo_anadir() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' AND OLD.es_demo AND flujo_modo_demo() THEN RETURN OLD; END IF;
    RAISE EXCEPTION 'Los registros de % son inalterables (% no permitido)', TG_TABLE_NAME, TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER flujo_inalterable_transicion
    BEFORE UPDATE OR DELETE ON flujo_transicionestado
    FOR EACH ROW EXECUTE FUNCTION flujo_solo_anadir();
CREATE TRIGGER flujo_inalterable_convocatoria
    BEFORE UPDATE OR DELETE ON flujo_convocatoria
    FOR EACH ROW EXECUTE FUNCTION flujo_solo_anadir();
CREATE TRIGGER flujo_inalterable_ratificacion
    BEFORE UPDATE OR DELETE ON flujo_ratificacion
    FOR EACH ROW EXECUTE FUNCTION flujo_solo_anadir();

-- 4) Votaciones: se pueden modificar mientras estén abiertas; cerradas, nunca
CREATE FUNCTION flujo_guardar_votacion() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND OLD.estado = 'ABIERTA' THEN RETURN NEW; END IF;
    IF TG_OP = 'DELETE' AND OLD.es_demo AND flujo_modo_demo() THEN RETURN OLD; END IF;
    RAISE EXCEPTION 'Una votación cerrada es inalterable (% no permitido)', TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER flujo_votacion
    BEFORE UPDATE OR DELETE ON flujo_votacion
    FOR EACH ROW EXECUTE FUNCTION flujo_guardar_votacion();

CREATE FUNCTION flujo_guardar_voto() RETURNS trigger AS $$
DECLARE
    est text;
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.es_demo AND flujo_modo_demo() THEN RETURN OLD; END IF;
        RAISE EXCEPTION 'Los votos nominales no se pueden borrar';
    END IF;
    SELECT estado INTO est FROM flujo_votacion WHERE id = NEW.votacion_id;
    IF est <> 'ABIERTA' THEN
        RAISE EXCEPTION 'La votación está cerrada: sus votos son inalterables';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER flujo_voto
    BEFORE INSERT OR UPDATE OR DELETE ON flujo_votonominal
    FOR EACH ROW EXECUTE FUNCTION flujo_guardar_voto();
"""

QUITAR = """
DROP TRIGGER flujo_voto ON flujo_votonominal;
DROP FUNCTION flujo_guardar_voto();
DROP TRIGGER flujo_votacion ON flujo_votacion;
DROP FUNCTION flujo_guardar_votacion();
DROP TRIGGER flujo_inalterable_ratificacion ON flujo_ratificacion;
DROP TRIGGER flujo_inalterable_convocatoria ON flujo_convocatoria;
DROP TRIGGER flujo_inalterable_transicion ON flujo_transicionestado;
DROP FUNCTION flujo_solo_anadir();
DROP TRIGGER flujo_version ON presupuesto_versionpresupuesto;
DROP FUNCTION flujo_guardar_version();
DROP TRIGGER flujo_contenido_donacion ON presupuesto_donacion;
DROP TRIGGER flujo_contenido_hipotesis ON presupuesto_hipotesis;
DROP TRIGGER flujo_contenido_importemensual ON presupuesto_importemensual;
DROP TRIGGER flujo_contenido_linea ON presupuesto_linea;
DROP FUNCTION flujo_guardar_contenido();
DROP FUNCTION flujo_modo_demo();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("flujo", "0001_initial"),
        ("presupuesto", "0004_flujo_de_versiones"),
    ]
    operations = [migrations.RunSQL(CREAR, QUITAR)]
