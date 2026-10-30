# Anexos: memoria explicativa y plan de tesorería

Fase 5 (CLAUDE.md §7.1 y §7.2). La campaña (§7.3) y la comparativa (§7.4) están en
`docs/campana_y_comparativa.md` (Fase 6).
No hay PDF ni Word: todo se ve en pantalla.

## Memoria explicativa

La memoria es parte de la versión: se redacta en el **borrador**, se **sella** con él (entra en la
huella) y, una vez propuesto, es de **solo lectura** (también para SQL directo, con un disparador de
PostgreSQL). **No se puede proponer una versión con la memoria incompleta** (regla V-008).

Cada sección mezcla tres tipos de contenido:

| Tipo | Quién lo pone | Ejemplo |
|---|---|---|
| Escrito a mano | El Tesorero | Contexto del ejercicio, propuesta de acuerdo |
| Automático | El sistema, desde los datos de la versión (no se puede escribir) | Totales, variaciones, hipótesis por capítulo, líneas de confianza baja |
| Mixto | Ambos | El resumen ejecutivo: tu valoración + las cifras calculadas solas |

### Las seis secciones propuestas

| Sección | Escribes tú | Lo añade el sistema |
|---|---|---|
| 1 · Resumen ejecutivo | Tu valoración (mín. 150 caracteres) | Ingresos, gastos, resultado, explicación del resultado, plan de financiación y las mayores variaciones frente al ejercicio anterior |
| 2 · Contexto del ejercicio | Actividad, hitos, elecciones (mín. 150) | — |
| 3 · Criterios e hipótesis | Criterio general de estimación (mín. 150) | Por capítulo: cada línea con su hipótesis, fuente, confianza y responsable |
| 4 · Riesgos e incertidumbres | Riesgos y medidas (mín. 100) | Ingresos de confianza baja (importe y % del total) y líneas condicionadas |
| 5 · Cumplimiento normativo | **Nada** | Comprobaciones superadas, incidencias, avisos aceptados y parámetros legales usados (valor, referencia, fecha y quién los verificó). En una versión propuesta es el resultado **del momento de proponer** |
| 6 · Propuesta de acuerdo | El texto que se vota (mín. 100) | — |

Los mínimos de caracteres son **valores propuestos**; se cambian en el panel.

### Ayuda para redactar

* Cada sección tiene un **texto de ayuda** que explica qué debe contar.
* Al redactar una sección vacía, el cuadro de texto arranca con la **plantilla**, ya con las cifras
  de la versión puestas. Cada `[COMPLETAR: …]` marca algo que debes escribir: mientras quede
  alguna, la sección sigue incompleta. Botón «Volver a la plantilla» si quieres empezar de nuevo.
* Marcadores que se rellenan solos: `{organizacion}` `{ejercicio}` `{version}` `{total_ingresos}`
  `{total_gastos}` `{resultado}` `{tipo_resultado}` `{proceso_electoral}`.
* Las plantillas y ayudas son **guías neutras**: no contienen contenido jurídico ni datos de la
  organización. El texto del acuerdo y a quién se eleva lo decide el Tesorero según los estatutos.

### Cuándo está «completa» (V-008)

Para cada sección activa y aplicable que no sea automática:

1. Si es obligatoria, tiene texto.
2. Si tiene mínimo de caracteres, lo alcanza.
3. No contiene ninguna **marca de pendiente** (por defecto `[COMPLETAR` y `PENDIENTE DE REVISAR`).
4. No está **pendiente de revisar** (viene copiada de otra versión: ver abajo).

El mensaje dice exactamente qué sección falta y por qué.

### Versiones derivadas

Al crear un borrador tras un rechazo, una modificación o una prórroga, la memoria se **copia como
punto de partida** pero queda **pendiente de revisar**: guardar de nuevo cada sección la da por
revisada. Así no pasa nada sin que alguien lo lea. El saldo inicial de tesorería se copia en
rechazos y modificaciones, pero **no en una prórroga** (es el de otro año).

## Plan de tesorería

Cobros y pagos **mes a mes** a partir de la distribución mensual de las líneas. Hipótesis (se
muestra en pantalla): **cada importe se cobra o se paga en el mes presupuestado**.

* **Saldo inicial**: lo escribe el Tesorero en la propia pantalla del plan (caja y bancos a 1 de
  enero). El sistema no lleva contabilidad y no puede conocerlo.
* Para cada mes: cobros, pagos, flujo neto, saldo final y estado.
* **Escenarios**:
  * **base**: tal cual está presupuestado;
  * **prudente**: descuenta un % a los ingresos según la confianza de cada línea;
  * **ajustado**: descuenta un % a los gastos según el tipo de cada línea (recurrente,
    extraordinario, condicionado).
  Un escenario sin ningún porcentaje **no se calcula** y se indica.
* **Alertas** (avisos, no bloquean; se aceptan al proponer y queda constancia):
  * `V-009`: falta el saldo inicial.
  * `V-010`: en el escenario base, algún mes con saldo negativo o por debajo del mínimo. Si el
    mínimo no está configurado, avisa de que solo se comprueba que no sea negativo.
  La pantalla del plan señala además los meses en tensión de cada escenario.
* Redondeo: `ROUND_HALF_UP` a céntimos, línea a línea y mes a mes, como en el resto del sistema.

## Panel «Anexos» (solo el Tesorero)

Entrada «Anexos» en el menú. Todo cambio queda en la auditoría (para la memoria, sin el texto:
solo la sección, su longitud y una huella).

1. **Secciones**: título, orden, obligatoria o no, activa o no, solo si hay proceso electoral,
   caracteres mínimos, texto de ayuda y plantilla. Se pueden **añadir secciones propias**
   (solo texto escrito a mano) y **volver a los valores propuestos** de cada sección.
2. **Parámetros**:

| Parámetro | Para qué | Valor propuesto |
|---|---|---|
| Variaciones destacadas | Cuántas diferencias con el año anterior salen en el resumen | 5 |
| Marcas de «pendiente» | Textos que indican que una sección no está terminada | `[COMPLETAR`, `PENDIENTE DE REVISAR` |
| Saldo mínimo de tesorería | Umbral de la alerta V-010 | **Sin valor** |
| Descuento a ingresos (confianza alta, media, baja) | Escenario prudente | **Sin valor** |
| Descuento a gastos (recurrente, extraordinario, condicionado) | Escenario ajustado | **Sin valor** |

Los de tesorería no llevan valor propuesto: dependen de la situación de la organización. Los
porcentajes se escriben con coma decimal (por ejemplo `12,5`).

### De dónde salen los valores y cómo se guardan

* `config/memoria.yaml` solo **siembra** los valores propuestos la primera vez (el arranque del
  contenedor lo hace con `sincronizar_configuracion`). **Lo que edites en el panel no se pisa
  nunca** al reiniciar.
* La **demostración** tiene su propio juego (`config/demo/memoria.yaml`, ficticio). Un usuario de
  demostración ve y edita el de la demo; el real no se toca. `borrar_demo` borra el de la demo.
* Al **proponer**, se guarda una copia de los parámetros usados (y de los parámetros legales).
  Una versión propuesta se muestra siempre con esa copia, aunque después cambies el panel.

## Huella

Desde esta fase hay dos tipos de huella (campo `version_huella`):

* **1**: líneas, hipótesis, importes mensuales y donaciones (versiones selladas hasta la Fase 4).
* **2**: lo anterior **más la memoria y el saldo inicial de tesorería**.
* **3**: lo anterior **más los datos del proceso electoral** (Fase 6).

Toda versión que se propone se sella con la 3 (la actual). Las ya selladas con la 1 se siguen verificando
con su método, así que nada se invalida. `version_huella` y el saldo inicial son inmutables en las
versiones que no son borrador.

## Permisos

| Rol | Memoria y plan | Panel Anexos |
|---|---|---|
| Tesorero | Ve todo; escribe en borradores | Sí |
| Comisión Permanente | Ve lo propuesto o posterior | No |
| Junta General | Ve lo aprobado por la CP o posterior | No |
