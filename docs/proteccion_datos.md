# Protección de datos (RGPD / LOPDGDD)

## Qué datos personales trata el sistema

| Dato | Para qué | Quién lo ve |
|---|---|---|
| Nombre y NIF/NIE/CIF del donante, y tipo de persona | Comprobar el límite anual por donante y la identificación (L-001, L-003) | Tesorero (completo). Los demás roles solo ven el NIF enmascarado (`****678Z`) en los avisos |
| Si el donante es parte de un contrato público vigente (sí/no, declarado por el Tesorero) | Aplicar la regla L-010 | Tesorero |
| Nombre, apellidos, DNI y cargo de las personas del panel de la organización | Los certificados necesitan identificar a quien certifica | Tesorero (el panel); salen en los certificados |
| Voto nominal de cada miembro de la CP, con su nombre | Dejar constancia de la votación | Tesorero y CP; en el certificado solo si se pide |
| Nombre de usuario y nombre de los miembros | Acceso nominal y auditoría | Tesorero |

**Decisión del Tesorero:** los donantes se identifican (esto prima sobre la recomendación de datos
mínimos de `CLAUDE.md` §13.3). Se guarda solo lo indicado: no hay dirección, teléfono ni correo.

## Medidas ya aplicadas

* **Minimización**: nombre, NIF, tipo de persona y la marca de contratista público; nada más.
* **La auditoría no guarda nombre ni NIF** de los donantes (solo su identificador interno), porque
  la auditoría no se puede borrar y así no impide atender un derecho de supresión.
* **Nada se borra**: un donante se da de baja con motivo y deja de poder recibir donaciones.
* **Acceso restringido**: solo el Tesorero ve y gestiona los donantes.
* **Auditoría sin DNI ni nombres** de personas del panel: solo identificadores internos.
* **Sin envío a terceros**: el sistema no envía datos a servicios externos.

## Pendiente de definir por la organización (no lo decide el sistema)

1. **Base jurídica** del tratamiento de los datos de los donantes.
2. **Plazo de conservación** de los datos tras la baja.
3. **Registro de actividades de tratamiento** y atención de derechos (acceso, rectificación,
   supresión, oposición).
4. Si procede, **evaluación de impacto** o delegado de protección de datos.

Hasta que se definan, los datos de donantes de **demostración** son ficticios (NIF de prueba y
nombres inventados) y se borran con `borrar_demo`. No introduzcas datos reales de personas hasta
tener resueltos los puntos anteriores. Este documento no es asesoramiento jurídico.
