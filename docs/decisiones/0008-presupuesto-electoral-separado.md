# 0008 · Presupuesto electoral separado del ordinario (Fase 6b)

Fecha: 30/10/2026 · Estado: aprobado el principio por el Tesorero («el presupuesto de campaña es
separado del ordinario, con su propio flujo, como si fuera un presupuesto extraordinario»);
detalles técnicos pendientes de visto bueno.

Sustituye a la decisión de la Fase 6 de integrar la campaña como capítulo G.7 dentro del
presupuesto ordinario.

1. **Dos cadenas por ejercicio.** `VersionPresupuesto.ambito` es `ORDINARIO` o `ELECTORAL`. Cada
   cadena tiene su propia numeración (única por ejercicio y ámbito), sus estados, votación de la
   Comisión Permanente, ratificación de la Junta, modificaciones, memoria, plan de tesorería,
   huella y certificados. Una no arrastra a la otra.
2. **Capítulos por ámbito.** Ordinario: I.1 a I.5, G.1 a G.6 y G.8. Electoral: I.6 (ingresos
   electorales de origen público), I.7 (de origen privado) y G.7 (gastos electorales). Una línea
   solo puede colgar de una partida del ámbito de su versión.
3. **Creación.** El presupuesto electoral solo se crea si el ejercicio declara proceso electoral,
   y una sola vez (`crear_presupuesto_electoral`). La prórroga es solo del ordinario.
4. **Reglas por ámbito.** L-004, L-012, L-013, L-014, L-015 y V-011 se evalúan solo en la versión
   electoral; el resto de reglas, en ambas. L-007 exige únicamente los parámetros del ámbito de la
   versión (más los `AMBOS`).
5. **Donantes.** El capítulo I.7 admite donantes; L-012 comprueba el máximo por persona,
   la identificación y la prohibición de personas jurídicas.
6. **Huella.** Las versiones electorales añaden `"ambito": "ELECTORAL"` al contenido canónico. Las
   ordinarias no cambian, de modo que los sellos existentes siguen verificando.
7. **Memoria.** Cada sección de la memoria tiene un ámbito (`TODOS`, `ORDINARIO`, `ELECTORAL`);
   «Presupuesto de campaña» es solo electoral. Los datos del proceso electoral pertenecen a la
   versión electoral.
8. **Cuadro de cuentas.** Se toma como fuente el plan contable de formaciones políticas aportado
   (`config/plan_cuentas_formaciones.yaml`, grupos 6 y 7). El cuadro solo puede usar cuentas de ese
   plan con su denominación exacta (prueba automática). El mapeo de la parte ordinaria es una
   propuesta a validar por el Tesorero; I.5.2 → 769 y G.8.1 → 678/6299 son provisionales.
9. **Migración.** Los capítulos que eran «solo con proceso electoral» pasan a ser electorales. Las
   versiones existentes quedan como ordinarias (los datos reales de campaña, si los hubiera, deben
   recrearse en el presupuesto electoral).
10. **Pendiente.** Los grupos 1 a 5 del plan contable no están cargados; la financiación del
    presupuesto electoral con fondos ordinarios (cuentas 554/581) solo se muestra en el plan
    electoral, no en el ordinario.
