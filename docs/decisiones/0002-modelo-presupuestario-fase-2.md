# 0002 · Decisiones de la Fase 2 (modelo presupuestario)

Fecha: 29/10/2026 · Estado: propuesta, pendiente de visto bueno del Tesorero.

1. **Jerarquía.** Capítulo → partida → línea (con 12 importes mensuales). CLAUDE.md §6 menciona
   también «subpartida», pero §10 solo define Capítulo/Partida/Línea; se sigue §10.
2. **Hipótesis y responsable.** El responsable es un atributo de la línea (§6.4) y la hipótesis
   (texto, fuente, confianza) es una entidad aparte (§10). El responsable **no** se duplica en la
   hipótesis, como sugería la lista de §10.
3. **Cuenta del PGC como relación.** `Linea.cuenta_pgc` apunta a `CuentaPGC` y cada partida admite
   solo ciertas cuentas. Las cuentas del cuadro son las de §3.3 y son orientativas.
4. **Dinero.** `Decimal` con dos decimales; redondeo `ROUND_HALF_UP`; los reparto mensuales se
   hacen en céntimos enteros y suman exactamente el importe. Una prueba vigila que no aparezca
   `float` en el código.
5. **Entrada de importes estricta.** Solo se admite `1.234,56` o `1234,56`. Un importe como
   `12.50` se rechaza (podría leerse como 1.250 en silencio).
6. **Nada se borra.** Las líneas se anulan con motivo y dejan de sumar. Los registros no tienen
   operación de borrado.
7. **Versiones no editables.** Hoy lo garantiza la aplicación (modelo y servicios). El refuerzo a
   nivel de base de datos queda para la Fase 4, junto al flujo de estados, porque necesita saber
   qué transiciones son legítimas.
8. **Parámetros legales.** El fichero YAML es la fuente; la base de datos es un reflejo para las
   validaciones. Todos están sin verificar y sin valores.
9. **Datos de demostración.** Cada fila lleva `es_demo`. La auditoría demo se puede borrar solo
   con el modo demo activado en la propia transacción y nunca la real. Las contraseñas demo son
   aleatorias. Se puede impedir la carga con `PERMITIR_DATOS_DEMO=0`.
10. **Donantes.** Se identificarán (decisión del Tesorero, a diferencia del criterio de datos
    mínimos de §13.3 y de la propuesta de tramos). El modelo de donantes y la regla L-001 se
    construyen en la Fase 3; antes se necesita decidir qué datos se guardan.
