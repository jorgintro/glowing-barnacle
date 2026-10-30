"""El ámbito (ordinario o electoral) de una versión sellada tampoco se puede cambiar."""

from django.db import migrations

NUEVA = r"""
CREATE OR REPLACE FUNCTION flujo_guardar_version() RETURNS trigger AS $$
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
            NEW.endeudamiento_previsto, NEW.autor_id, NEW.fecha, NEW.es_demo,
            NEW.saldo_inicial_tesoreria, NEW.version_huella, NEW.ambito)
           IS DISTINCT FROM
           (OLD.ejercicio_id, OLD.numero, OLD.motivo, OLD.version_origen_id, OLD.es_prorroga,
            OLD.tipo_origen, OLD.explicacion_resultado, OLD.plan_financiacion,
            OLD.endeudamiento_previsto, OLD.autor_id, OLD.fecha, OLD.es_demo,
            OLD.saldo_inicial_tesoreria, OLD.version_huella, OLD.ambito) THEN
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
"""

ANTERIOR = r"""
CREATE OR REPLACE FUNCTION flujo_guardar_version() RETURNS trigger AS $$
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
            NEW.endeudamiento_previsto, NEW.autor_id, NEW.fecha, NEW.es_demo,
            NEW.saldo_inicial_tesoreria, NEW.version_huella)
           IS DISTINCT FROM
           (OLD.ejercicio_id, OLD.numero, OLD.motivo, OLD.version_origen_id, OLD.es_prorroga,
            OLD.tipo_origen, OLD.explicacion_resultado, OLD.plan_financiacion,
            OLD.endeudamiento_previsto, OLD.autor_id, OLD.fecha, OLD.es_demo,
            OLD.saldo_inicial_tesoreria, OLD.version_huella) THEN
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
"""


class Migration(migrations.Migration):
    dependencies = [
        ("flujo", "0003_inmutabilidad_anexos"),
        ("presupuesto", "0008_presupuesto_electoral_separado"),
    ]
    operations = [migrations.RunSQL(NUEVA, ANTERIOR)]
