"""Inmutabilidad en la base de datos de los datos del proceso electoral y de la ejecución real.

* El proceso electoral de una versión que no es borrador es de solo lectura.
* Las importaciones de ejecución real solo admiten un cambio: ACTIVA → ANULADA con motivo.
* Los datos reales importados no se modifican ni se borran.
Excepción común: el borrado de filas de demostración con ``presupuesto.modo_demo`` activado.
"""

from django.db import migrations

CREAR = r"""
CREATE FUNCTION anexos_guardar_proceso() RETURNS trigger AS $$
DECLARE
    vid bigint;
    est text;
    demo boolean;
BEGIN
    IF TG_OP = 'DELETE' THEN vid := OLD.version_id; ELSE vid := NEW.version_id; END IF;
    SELECT estado, es_demo INTO est, demo FROM presupuesto_versionpresupuesto WHERE id = vid;
    IF est IS NULL OR est = 'BORRADOR' THEN
        IF TG_OP = 'DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
    END IF;
    IF TG_OP = 'DELETE' AND demo AND flujo_modo_demo() THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'La versión % está en estado % y su proceso electoral es de solo lectura (%)',
        vid, est, TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER anexos_procesoelectoral
    BEFORE INSERT OR UPDATE OR DELETE ON anexos_procesoelectoral
    FOR EACH ROW EXECUTE FUNCTION anexos_guardar_proceso();

CREATE FUNCTION anexos_guardar_ejecucion() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN RETURN NEW; END IF;
    IF TG_OP = 'DELETE' AND OLD.es_demo AND flujo_modo_demo() THEN RETURN OLD; END IF;
    RAISE EXCEPTION 'Los datos de ejecución real importados son inalterables (% no permitido)',
        TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER anexos_ejecucionreal
    BEFORE INSERT OR UPDATE OR DELETE ON anexos_ejecucionreal
    FOR EACH ROW EXECUTE FUNCTION anexos_guardar_ejecucion();

CREATE FUNCTION anexos_guardar_importacion() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN RETURN NEW; END IF;
    IF TG_OP = 'DELETE' THEN
        IF OLD.es_demo AND flujo_modo_demo() THEN RETURN OLD; END IF;
        RAISE EXCEPTION 'Las importaciones de ejecución real no se pueden borrar: se anulan';
    END IF;
    IF OLD.estado = 'ACTIVA' AND NEW.estado = 'ANULADA' AND btrim(NEW.motivo_anulacion) <> ''
       AND (NEW.ejercicio_id, NEW.mes_corte, NEW.nombre_fichero, NEW.huella_fichero, NEW.filas,
            NEW.importado_por_id, NEW.importado_en, NEW.es_demo)
           IS NOT DISTINCT FROM
           (OLD.ejercicio_id, OLD.mes_corte, OLD.nombre_fichero, OLD.huella_fichero, OLD.filas,
            OLD.importado_por_id, OLD.importado_en, OLD.es_demo) THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'Una importación solo puede anularse (con motivo); no se puede modificar';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER anexos_importacionejecucion
    BEFORE INSERT OR UPDATE OR DELETE ON anexos_importacionejecucion
    FOR EACH ROW EXECUTE FUNCTION anexos_guardar_importacion();
"""

QUITAR = """
DROP TRIGGER anexos_importacionejecucion ON anexos_importacionejecucion;
DROP FUNCTION anexos_guardar_importacion();
DROP TRIGGER anexos_ejecucionreal ON anexos_ejecucionreal;
DROP FUNCTION anexos_guardar_ejecucion();
DROP TRIGGER anexos_procesoelectoral ON anexos_procesoelectoral;
DROP FUNCTION anexos_guardar_proceso();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("anexos", "0003_campana_y_ejecucion"),
        ("flujo", "0002_inmutabilidad"),
    ]
    operations = [migrations.RunSQL(CREAR, QUITAR)]
