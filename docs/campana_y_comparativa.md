# Presupuesto de campaña y comparativa con la ejecución real

> **Fase 6b · presupuesto electoral separado** (decisión 0008). La campaña ya no es un capítulo
> dentro del presupuesto ordinario: es un **presupuesto electoral propio**, con su cadena de
> versiones y su flujo (propuesta, Comisión Permanente, Junta General, modificaciones). Sus
> capítulos son I.6 (ingresos electorales públicos), I.7 (privados, con donantes) y G.7 (gastos).
> Se crea desde la lista de presupuestos del ejercicio, solo si hay proceso electoral. Las reglas
> L-004, L-012 a L-015 y V-011 y la sección «Presupuesto de campaña» de la memoria se aplican
> únicamente a la versión electoral. Donde abajo se lea «la versión», en campaña es la electoral.


Fase 6 (CLAUDE.md §7.3 y §7.4). No hay PDF ni Word: todo se ve en pantalla.

> Los importes legales de esta fase proceden del texto que aportó el Tesorero el 30/10/2026
> (`docs/fuentes_normativas/LOREG_gastos_electorales_aportado_por_el_tesorero.md`). **No están
> contrastados con el BOE** y los de subvención y límite son los de **las elecciones locales de
> 28/05/2023**: pueden ser otros para el proceso que corresponda. Figuran como **sin verificar**
> hasta que el Tesorero o su asesor los verifique. El sistema ayuda a cumplir; no es asesoramiento
> jurídico.

## Presupuesto de campaña (solo si el ejercicio tiene proceso electoral)

Pantalla **Presupuesto de campaña** de cada versión. Los gastos electorales se imputan **de forma
separada** (capítulo G.7 y líneas de dimensión «campaña»), como exige el plan de contabilidad.

### Datos del proceso electoral
Los escribe el Tesorero en el borrador y forman parte de lo que se sella (huella de tipo 3):

| Dato | Para qué |
|---|---|
| Denominación y fechas (convocatoria, elecciones, proclamación de electos) | Periodo de gasto y calendario |
| Habitantes de derecho | Calcular el límite de gasto |
| Provincias con gasto adicional | Ampliar el límite (concurrir al menos al 50 % de sus municipios) |
| ¿Se cumplen los requisitos del envío directo? y electores | Sacar el envío subvencionado del límite |
| Concejales y votos previstos | Estimar la subvención |

### Cómo se calcula
* **Límite** = habitantes × euros por habitante (+ euros adicionales × provincias). Los euros salen
  de los parámetros `gasto_electoral_euros_por_habitante` y
  `gasto_electoral_adicional_por_provincia`; si no están verificados, **el límite no se calcula** y
  L-004 bloquea diciendo qué falta.
* **Gasto que cuenta** = gasto electoral − envío directo subvencionado. Solo se descuenta si el
  Tesorero declara que se cumplen los requisitos y hay electores indicados, y es el **menor** entre
  el gasto de envío (partidas G.7.11 a G.7.14) y su subvención estimada. Ante la duda no se
  descuenta nada (criterio prudente).
* **Financiación**: subvenciones electorales, donaciones y aportaciones a la campaña (líneas de
  campaña), endeudamiento previsto y **lo que quedaría a cubrir con fondos ordinarios**.
* **Calendario legal orientativo** (con la marca «sin verificar» si el parámetro lo está):
  periodo de gasto, solicitud y disponibilidad del adelanto, y plazo de presentación de la
  contabilidad al Tribunal de Cuentas. Recordatorio de la obligación de las empresas que
  facturen más del umbral.

### Estructura contable
El cuadro de cuentas incorpora el modelo electoral aportado (721, 722, 731, 650/651, 6521 a 65272,
6529, 6530 a 6539, 6630 a 6632): partidas I.3.4, I.3.5, I.4.3 y G.7.1 a G.7.15. Sigue pendiente de
validar por el Tesorero o su asesor.

> **Aviso sobre las cuentas ordinarias.** El modelo del plan de contabilidad aportado usa para la
> actividad ordinaria cuentas distintas de las orientativas del apartado 3.3 de `CLAUDE.md`
> (710/711 para cuotas y aportaciones de afiliados, 714/715 para donaciones, 700 a 704 para
> ingresos públicos). Esa parte del cuadro **no se ha tocado** en esta fase y debe revisarse.

### Reglas nuevas y modificadas
| Regla | Qué comprueba | Tipo |
|---|---|---|
| L-004 *(modificada)* | El gasto electoral que cuenta no supera el límite calculado (habitantes × tarifa) | Bloqueante |
| L-012 | Nadie aporta a las cuentas electorales más del máximo por persona (LOREG art. 129) | Bloqueante |
| L-013 | La subvención electoral presupuestada no supera el gasto electoral (art. 127.1) | Aviso |
| L-014 | La subvención presupuestada no supera la estimada con las previsiones | Aviso |
| L-015 | El gasto de campaña cae dentro del periodo electoral (art. 130), por meses | Aviso |
| V-011 | El gasto electoral llega al % del límite fijado en el panel «Anexos» | Aviso |

**L-007 (parámetros verificados)** ahora distingue ámbitos: los parámetros `ELECTORAL` solo se
exigen en ejercicios con proceso electoral, y los `informativo` (importes de subvención y plazos,
que solo alimentan estimaciones y calendario) no condicionan ninguna regla.

### Memoria
Si hay proceso electoral, la memoria incorpora la sección **Presupuesto de campaña** (obligatoria,
con ayuda y plantilla editables en el panel) y, debajo, el bloque automático con límite, gasto y
financiación.

## Comparativa y desviaciones

Pantalla **Comparativa** de cada versión.

### Frente al ejercicio anterior
Variación absoluta y porcentual por línea y capítulo, con el importe del ejercicio anterior que el
Tesorero escribió en cada línea. Si una línea no lo tiene, sale un guion.

### Frente a la ejecución real
Se importan los datos reales desde un **CSV** (Excel llegará si se pide; así no se añade ninguna
librería). Pantalla **Importar ejecución real** (solo el Tesorero), accesible desde la comparativa.

**Formato:** tres columnas separadas por «;» → `codigo;mes;importe`, con el importe en `1.234,56`.
La plantilla descargable trae una fila por línea del presupuesto.

* **Todo o nada:** el fichero se valida entero (cabecera, código de línea existente, mes 1-12 y no
  posterior al mes de corte, importe estricto, filas repetidas). Si algo falla, no se guarda nada y
  se listan los errores por fila (hasta 30). El punto decimal («12.50») se rechaza por ambiguo.
* **Mes de corte:** el último mes con datos; la comparativa acumula hasta él.
* **Inalterable:** cada importación guarda la huella SHA-256 del fichero y nada se edita ni se
  borra (disparadores de PostgreSQL). Una importación solo se **anula con motivo**.
* **Cuál se usa:** la última importación **activa** del ejercicio. Para corregir, importa otra o
  anula la errónea (vuelve la anterior).
* La ejecución real **no forma parte de la versión sellada**: es información externa que cambia
  con el tiempo. Las altas y anulaciones quedan en la auditoría.

### Semáforo
Se mide la **desviación adversa**: en ingresos, quedarse por debajo de lo presupuestado; en gastos,
pasarse. Se compara el real acumulado con el presupuesto acumulado hasta el mes de corte.

| Color | Cuándo |
|---|---|
| Verde | Sin desviación adversa, o menor que el importe mínimo |
| Ámbar | Desviación adversa ≥ umbral ámbar (%) |
| Rojo | Desviación adversa ≥ umbral rojo (%), o con presupuesto 0 y desviación sobre el mínimo |
| Sin datos | La línea no aparece en el fichero (no se supone cero) |
| Sin configurar | No hay umbrales: se muestran las desviaciones sin color |

Los umbrales se fijan en el panel **Anexos** (ámbar %, rojo %, importe mínimo) y no traen valor.
Siempre hay texto además de color (accesibilidad). Un capítulo solo tiene semáforo si todas sus
líneas tienen datos.

## Panel «Anexos»: parámetros añadidos en esta fase
| Parámetro | Valor propuesto |
|---|---|
| % del límite de gasto electoral a partir del cual se avisa (V-011) | **Sin valor** |
| Semáforo: % ámbar, % rojo e importe mínimo | **Sin valor** |
