from django.db import migrations

CREAR = """
CREATE FUNCTION auditoria_proteger() RETURNS trigger AS $$
BEGIN
    -- Única excepción: borrado de filas de demostración con el modo demo activado.
    IF TG_OP = 'DELETE'
       AND OLD.es_demo
       AND COALESCE(current_setting('presupuesto.modo_demo', true), '') = 'on' THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'El registro de auditoría es inalterable (operación % no permitida)', TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER auditoria_inalterable_filas
    BEFORE UPDATE OR DELETE ON auditoria_registroauditoria
    FOR EACH ROW EXECUTE FUNCTION auditoria_proteger();

CREATE TRIGGER auditoria_inalterable_truncate
    BEFORE TRUNCATE ON auditoria_registroauditoria
    FOR EACH STATEMENT EXECUTE FUNCTION auditoria_proteger();
"""

QUITAR = """
DROP TRIGGER auditoria_inalterable_truncate ON auditoria_registroauditoria;
DROP TRIGGER auditoria_inalterable_filas ON auditoria_registroauditoria;
DROP FUNCTION auditoria_proteger();
"""


class Migration(migrations.Migration):
    dependencies = [("auditoria", "0001_initial")]
    operations = [migrations.RunSQL(CREAR, QUITAR)]
