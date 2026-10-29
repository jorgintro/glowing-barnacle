# Catálogo de reglas de validación

Las reglas se ejecutan antes de cada cambio de estado y se pueden consultar en cualquier momento
en la pantalla **Validaciones** de cada versión. Una regla **bloqueante** impide avanzar; un
**aviso** se muestra y exige constancia. Cada regla tiene al menos una prueba que la cumple y otra
que la rompe (`tests/test_validaciones_v.py`, `_l.py` y `_o.py`).

> **Principio de prudencia.** Una regla legal que necesita un parámetro sin verificar **no se da
> por cumplida**: bloquea e indica qué parámetro falta. Ningún límite está escrito en el código.
> El sistema ayuda a cumplir; no sustituye a un asesor jurídico ni fiscal.

## Reglas aritméticas y de coherencia (V)

| Código | Qué comprueba | Tipo |
|---|---|---|
| V-001 | Los 12 meses de cada línea suman exactamente su importe anual | Bloqueante |
| V-002 | El total de cada capítulo (por importes anuales) coincide con la suma de sus meses | Bloqueante |
| V-003 | Cada línea tiene una cuenta del PGC activa y propia de su partida | Bloqueante |
| V-004 | Cada línea tiene hipótesis con fuente y responsable; los ingresos, su confianza | Bloqueante |
| V-005 | Importes con dos decimales y sin negativos, salvo ajustes con justificación | Bloqueante |
| V-006 | El resultado está explicado; un déficit exige plan de financiación | Bloqueante |
| V-007 | Una variación mayor que el umbral respecto al ejercicio anterior está justificada | Aviso |

V-007 usa `umbral_variacion_porcentaje` de `config/parametros_internos.yaml`. Mientras esté vacío
avisa de que no se puede comprobar.

## Reglas legales (L)

| Código | Qué comprueba | Parámetros que usa |
|---|---|---|
| L-001 | Donaciones: límite anual por donante, todo el importe con donante identificado y tipo de persona permitido | `limite_donacion_anual_por_donante`, `donaciones_anonimas_permitidas`, `donaciones_personas_juridicas_permitidas` |
| L-002 | Ningún ingreso procede de una fuente prohibida (campo «origen» de la línea) | `fuentes_ingreso_prohibidas` |
| L-003 | Aportaciones de cargos identificadas y dentro del límite | `limite_aportaciones_cargos_anual` |
| L-004 | El gasto electoral no supera el límite y solo existe si hay proceso electoral | `limite_gasto_electoral` |
| L-005 | El endeudamiento previsto no supera el límite | `limite_endeudamiento` |
| L-006 | Todas las líneas siguen el cuadro de cuentas, y este está validado por el Tesorero | `cuadro_cuentas.yaml` |
| L-007 | Todos los parámetros legales están verificados y su fecha de verificación es vigente | Todos |

**Valores del extracto.** `config/parametros_legales.yaml` lleva ya valor y referencia de cuatro
parámetros, tomados del extracto de los arts. 4 a 8 que aportó el Tesorero
(`docs/fuentes_normativas/`). Siguen pendientes hasta que se firmen (fecha y verificador).

**Fuente normativa.** Las normas de referencia son las que cita `CLAUDE.md` §3.1 (LO 8/2007, LOREG,
PGC…). **Los artículos concretos y los valores están pendientes de verificar contra el BOE**; no
se citan de memoria. El sistema solo aplica lo que figure verificado en `parametros_legales.yaml`.

**Interpretaciones que conviene confirmar con el asesor:**

* L-001 y L-003 aplican el límite **por donante y por versión** (año del ejercicio). El acumulado
  de L-001 suma las donaciones de todas las líneas de I.4 del mismo donante. El de L-003, las de I.2.
* L-003 exige identificar al aportante de todas las aportaciones de cargos.
* L-007 considera vigente una verificación hecha **en el año del ejercicio o en el anterior** (la
  verificación se hace en octubre para el ejercicio siguiente, `CLAUDE.md` §14), y rechaza fechas
  futuras. Se puede desactivar la ventana con `exigir_ventana_verificacion: false` (solo en demo).
* L-004 suma como gasto electoral el capítulo G.7 y toda línea de gasto con dimensión «Campaña».

### Lo que el extracto sugiere y todavía NO está implementado

Pendiente de que el Tesorero decida si se añade (cada una llevaría su regla y sus pruebas):

| Artículo del extracto | Posible regla | Qué haría falta |
|---|---|---|
| 5.Dos y 8.Tres | **Aviso** si una donación o aportación supera 25.000 €: hay que notificarla al Tribunal de Cuentas | Parámetro nuevo con el umbral |
| 6.Tres | Los ingresos de actividades propias de 300 € o más exigen identificar al transmitente | Parámetro nuevo y donantes también en I.5 |
| 4.Dos.a | No se admiten donaciones de personas físicas que sean parte de un contrato público vigente | Un dato más del donante |
| 5.Uno.b (excepción) | El límite de 50.000 € no se aplica a donaciones en especie de inmuebles | Distinguir tipo de bien en la donación |
| 5.Uno.a | También son inadmisibles las donaciones **finalistas o revocables** | Un dato más de la donación |
| 6.Uno | **Los partidos no pueden desarrollar actividades mercantiles**: conviene que el asesor revise partidas como la venta de merchandising (I.5.1) y los datos de demostración | Decisión del asesor |
| 4.Dos.b, 8.Uno-Dos | Cuentas bancarias exclusivas para donaciones y cuotas | Fuera del alcance del sistema (no hay conciliación bancaria) |

## Reglas orgánicas (O)

Son funciones puras: la votación y la ratificación (Fase 4) les pasarán sus datos.

| Código | Qué comprueba | Tipo |
|---|---|---|
| O-001 | La Comisión Permanente alcanza quórum y mayoría según `reglas_organicas.yaml` | Bloqueante |
| O-002 | La ratificación se registra con fecha (no futura ni anterior a la aprobación de la CP), resultado y referencia al acta | Bloqueante |
| O-003 | Quien propone no vota en la misma versión, si el reglamento lo impide | Bloqueante |
| O-004 | La convocatoria de la Junta está registrada y es anterior a la sesión | Aviso |

* **Sin quórum ni mayoría configurados, la votación está bloqueada** (O-001).
* Si `proponente_puede_votar` está vacío se aplica la opción prudente: **no puede votar**.
* La aritmética de quórum y mayorías es entera (fracciones `n/d`), sin decimales.
* Bases de mayoría admitidas: `MIEMBROS`, `ASISTENTES`, `EMITIDOS` (a favor + en contra +
  abstenciones) y `EMITIDOS_SIN_ABSTENCIONES`.

## Cómo añadir una regla nueva

1. Escribe la función en `apps/validaciones/reglas_*.py` y regístrala en `motor.py` con su fuente.
2. Añade al menos una prueba que la cumpla y otra que la rompa.
3. Documéntala aquí y referencia su fuente normativa (pendiente de verificar si es legal).
