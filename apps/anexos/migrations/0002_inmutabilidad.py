"""La memoria de una versión que no es borrador es de solo lectura (también por SQL directo).

Misma regla que el contenido de las líneas (flujo 0002): solo se escribe mientras la versión
está en BORRADOR. Excepción: el borrado de filas de demostración con ``presupuesto.modo_demo``.
"""

from django.db import migrations

CREAR = r"""
CREATE FUNCTION anexos_guardar_seccion() RETURNS trigger AS $$
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
    RAISE EXCEPTION 'La versión % está en estado % y su memoria es de solo lectura (%)',
        vid, est, TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER anexos_seccionmemoria
    BEFORE INSERT OR UPDATE OR DELETE ON anexos_seccionmemoria
    FOR EACH ROW EXECUTE FUNCTION anexos_guardar_seccion();
"""

QUITAR = """
DROP TRIGGER anexos_seccionmemoria ON anexos_seccionmemoria;
DROP FUNCTION anexos_guardar_seccion();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("anexos", "0001_initial"),
        ("flujo", "0002_inmutabilidad"),
    ]
    operations = [migrations.RunSQL(CREAR, QUITAR)]
