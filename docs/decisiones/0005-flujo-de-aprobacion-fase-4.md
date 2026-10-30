# 0005 · Decisiones de la Fase 4 (flujo de aprobación)

Fecha: 30/10/2026 · Estado: propuesta, pendiente de visto bueno del Tesorero.

1. **Inmutabilidad en la base de datos.** Disparadores de PostgreSQL rechazan cambios del contenido
   de versiones que no son borrador, transiciones no permitidas, cambios de huella o proponente y
   cualquier modificación de transiciones, convocatorias, ratificaciones y votaciones cerradas. No
   dependen de la aplicación: se prueban con SQL directo. Única excepción: el borrado de filas de
   demostración con el modo demo activado en la misma transacción.
2. **Huella y cadena.** SHA-256 del contenido canónico (claves ordenadas, importes como texto) y una
   hoja de control en la que cada transición encadena la anterior. La votación, la ratificación y
   los certificados comprueban la integridad y se niegan si falla.
3. **Voto nominal.** Se guarda el voto de cada miembro (decisión del Tesorero: «que conste el voto
   nominal») y los totales se calculan de ahí y se fijan al cerrar. La Comisión Permanente son los
   usuarios activos con ese rol (los de demostración, con los de demostración).
4. **Cierre de la votación.** Cualquier miembro de la CP la cierra. Sin quórum no se puede cerrar
   (sigue abierta). Con quórum y mayoría aprueba; con quórum sin mayoría rechaza y abre un nuevo
   borrador copiando la versión.
5. **`MODIFICADO`.** Estado final de una modificación aprobada solo por la Comisión Permanente
   (no supera el umbral o es una transferencia que el reglamento deja a la CP). Una modificación
   que supera el umbral, o sin umbral configurado, sigue hasta `RATIFICADO_JG`. `CLAUDE.md` §5.1
   no precisa este punto; es una interpretación a confirmar.
6. **Prórroga.** Copia solo las líneas recurrentes y deja fuera la campaña y lo extraordinario o
   condicionado, porque una campaña electoral es un gasto puntual.
7. **Quién registra la ratificación.** Por defecto solo la Junta General (`CLAUDE.md` §4). Que
   también pueda el Tesorero es una excepción pedida para la demostración y vive solo en
   `config/demo/reglas_organicas.yaml`.
8. **Panel de la organización.** Datos de la organización, lista de cargos y personas con nombre,
   apellidos, DNI y cargo(s), a petición del Tesorero. La auditoría no guarda DNI ni nombres.
9. **Certificados en PDF.** El Tesorero pidió HTML y PDF para los certificados. Es la **única**
   excepción a «solo Excel y HTML» (`CLAUDE.md` §11). Librería: `reportlab` (Python puro, unos
   16 MB con Pillow, sin dependencias del sistema). Se descartó WeasyPrint por exigir Pango y
   otras bibliotecas del sistema, demasiado pesado para el servidor doméstico. El certificado no es
   una firma electrónica (§16.1): lleva líneas de firma a mano.
10. **La memoria explicativa no se exige todavía** al proponer; se añadirá en la Fase 5 (confirmado
    por el Tesorero).
11. **Con la configuración real, ninguna versión puede aprobarse todavía:** faltan los tres
    parámetros legales sin valor (aportaciones de cargos, gasto electoral y endeudamiento), la
    validación del cuadro de cuentas y el quórum y la mayoría de la CP. Es a propósito.
12. **Pruebas más lentas.** La demostración se carga recorriendo el flujo real, por lo que cada
    prueba que la usa tarda unos segundos más.
