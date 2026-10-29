# 0003 · Decisiones de la Fase 3 (motor de validaciones)

Fecha: 29/10/2026 · Estado: propuesta, pendiente de visto bueno del Tesorero.

1. **Una regla legal sin parámetro verificado bloquea.** No se interpreta la falta de dato como
   «cumple». Cada incidencia nombra el parámetro pendiente.
2. **Configuración real y de demostración separadas.** Las versiones demo usan `config/demo/`
   (valores ficticios, incluidas las excepciones pedidas para la demo: el Tesorero vota); las
   reales, `config/`. Así la demo puede mostrar todas las reglas sin inventar datos reales.
3. **Donantes identificados** (decisión del Tesorero): nombre, NIF y tipo de persona, con
   validación del formato y la letra de control. Las donaciones de personas jurídicas se tratan con
   el parámetro `donaciones_personas_juridicas_permitidas`, pendiente de verificar con su
   referencia (el Tesorero indica que no están permitidas, pero el sistema no lo da por vigente
   hasta que figure verificado).
4. **La auditoría no guarda datos de donantes** (ni nombre ni NIF), para no entrar en conflicto con
   el derecho de supresión, ya que la auditoría es inalterable.
5. **NIF enmascarado** (`****678Z`) en los avisos que ve la Comisión Permanente y la Junta.
6. **Reglas orgánicas como funciones puras.** La votación y la ratificación (modelos y pantallas)
   llegan en la Fase 4; las reglas O-001…O-004 ya están construidas y probadas sobre datos simples.
7. **Opción prudente en O-003**: si el reglamento no está configurado, el proponente no puede votar.
8. **Campos nuevos**: en la versión, `explicacion_resultado`, `plan_financiacion` y
   `endeudamiento_previsto` (para V-006 y L-005); en la línea, `origen_ingreso` (para L-002).
9. **Interpretaciones pendientes de confirmar con el asesor**: límite por donante y por versión
   (L-001, L-003), identificación obligatoria en las aportaciones de cargos (L-003), ventana de
   vigencia de la verificación (L-007) y qué cuenta como gasto electoral (L-004). Están descritas en
   `docs/reglas_validacion.md`.
10. **Aviso (V-007) con umbral sin configurar**: avisa de que no se puede comprobar en lugar de
    inventar un umbral.
