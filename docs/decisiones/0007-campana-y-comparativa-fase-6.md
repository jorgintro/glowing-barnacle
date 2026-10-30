# 0007 · Decisiones de la Fase 6 (campaña y comparativa)

Fecha: 30/10/2026 · Estado: propuesta, pendiente de visto bueno del Tesorero.

1. **Parámetros electorales sin verificar.** Los importes del extracto aportado el 30/10/2026
   (límite 0,11 €/habitante y 150.301,11 € por provincia, máximo de aportación de 10.000 €,
   subvenciones, plazos) se cargan en `config/parametros_legales.yaml` con su origen, pero **sin
   fecha ni verificador**: el Tesorero no los ha declarado verificados. Son los de las elecciones
   locales de 2023. Mientras tanto, L-004 y L-012 bloquean en ejercicios con campaña.
2. **`ambito` e `informativo`.** L-007 exigía verificar todos los parámetros; con 16 más habría
   bloqueado todo presupuesto sin campaña. Los `ELECTORAL` solo se exigen con proceso electoral y
   los `informativo` (subvenciones y plazos, que solo estiman y calendarizan) no bloquean.
3. **L-004 por habitantes.** Se sustituye el parámetro `limite_gasto_electoral` (un importe fijo
   que no existe en la norma) por habitantes × tarifa + adicional por provincia. Los habitantes son
   un dato del proceso electoral de cada versión (sellado con ella).
4. **Envío directo fuera del límite.** Solo el **menor** entre el gasto de envío y su subvención
   estimada, y solo si el Tesorero declara que se cumplen los requisitos y hay electores. Ante la
   duda no se descuenta. Las partidas de envío (G.7.11 a G.7.14) llevan la marca `envio_electoral`.
5. **Cuadro de cuentas electoral.** G.7 se divide según el modelo aportado (G.7.1 a G.7.15) y se
   añaden I.3.4, I.3.5 e I.4.3. **No se toca la parte ordinaria**, cuyas cuentas orientativas
   (§3.3) difieren de las del modelo aportado: queda como tarea pendiente a decidir.
6. **Reglas nuevas.** L-012 (bloqueante) y L-013, L-014, L-015 y V-011 (avisos), anotadas en
   `CLAUDE.md` §8. Las que dependen de parámetros no verificados lo dicen en lugar de callar.
7. **Huella de tipo 3** (añade el proceso electoral). Las ya selladas se verifican con su tipo.
8. **Ejecución real por CSV** (`codigo;mes;importe`): sin dependencias nuevas. Excel queda para
   cuando se pida. Todo o nada, con la huella del fichero, inalterable y anulable con motivo
   (disparadores). No forma parte de la versión sellada: es información externa que cambia.
9. **La comparativa usa la última importación activa** del ejercicio y los códigos de línea de la
   versión que se mira. Una línea ausente en el fichero es «sin datos», no cero.
10. **Semáforo configurable en el panel** y sin valores propuestos; mide la desviación adversa
    (ingresos por debajo, gastos por encima) y exige además un importe mínimo opcional.
