# 0004 · Reglas añadidas a partir del extracto de la ley

Fecha: 29/10/2026 · Estado: propuesta, pendiente de visto bueno del Tesorero.

Origen: el Tesorero aportó el texto de los arts. 4 a 8 de la ley (`docs/fuentes_normativas/`) y pidió
añadir las reglas que sugería. No está contrastado con el BOE.

1. **Reglas nuevas**: L-008 (aviso de notificación al Tribunal de Cuentas), L-009 (identificar al
   transmitente), L-010 (contratistas públicos) y L-011 (donaciones finalistas o revocables). La
   excepción de los inmuebles se integra en L-001. Son 18 reglas en total.
2. **Cada regla lee su parámetro de `parametros_legales.yaml`**, con valor y referencia del
   extracto. Sin parámetro verificado, la regla no se da por cumplida.
3. **Verificación declarada, no comprobada.** El Tesorero indicó «verificado» sobre los cuatro
   parámetros que se le mostraron. Se registran como verificados con fecha 29/10/2026 y verificador
   «Tesorero (declaración en la sesión)». **El sistema no puede comprobar esa verificación**, y los
   cinco parámetros añadidos después quedan pendientes hasta que el Tesorero los confirme.
4. **Datos nuevos**: en el donante, si es parte de un contrato público; en la donación, tipo (dinero,
   especie, inmueble), finalista y revocable; en las líneas de I.5, el importe de operaciones
   individuales altas. Todos los declara el Tesorero.
5. **Interpretación de L-009**: el presupuesto es anual y agregado, así que el umbral de 300 € se
   aplica sobre la parte declarada como «operaciones individuales altas», no sobre cada venta.
6. **No se implementa** (queda para el asesor o fuera de alcance): la calificación de actividades
   mercantiles (art. 6.Uno), las cuentas bancarias exclusivas, la devolución del exceso y las
   donaciones de extranjeros.
7. **Aviso para el asesor**: el art. 6.Uno puede afectar a la venta de merchandising (I.5.1).
