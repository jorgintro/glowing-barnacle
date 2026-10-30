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
| V-008 | La memoria explicativa está completa (secciones obligatorias escritas, mínimos, sin marcas de pendiente ni secciones por revisar) | Bloqueante |
| V-009 | Está indicado el saldo inicial de tesorería | Aviso |
| V-010 | Ningún mes del plan de tesorería base tiene saldo negativo o por debajo del mínimo | Aviso |
| V-011 | El gasto electoral no llega al % del límite fijado en el panel «Anexos» | Aviso |

V-007 usa `umbral_variacion_porcentaje` de `config/parametros_internos.yaml`. Mientras esté vacío
avisa de que no se puede comprobar.

V-008 a V-010 (Fase 5) usan la configuración del panel «Anexos» (ver `docs/anexos.md`): secciones y
mínimos de la memoria, marcas de «pendiente» y saldo mínimo de tesorería. Fuente: CLAUDE.md §5.1,
§7.1 y §7.2. Si el saldo mínimo no está configurado, V-010 avisa de que solo puede comprobar que el
saldo no sea negativo.

## Reglas legales (L)

| Código | Qué comprueba | Parámetros que usa |
|---|---|---|
| L-001 | Donaciones: límite anual por donante, todo el importe con donante identificado y tipo de persona permitido. Las donaciones en especie de **inmuebles** no cuentan para el límite | `limite_donacion_anual_por_donante`, `donaciones_anonimas_permitidas`, `donaciones_personas_juridicas_permitidas`, `donaciones_inmuebles_exentas_de_limite` |
| L-002 | Ningún ingreso procede de una fuente prohibida (campo «origen» de la línea) | `fuentes_ingreso_prohibidas` |
| L-003 | Aportaciones de cargos identificadas y dentro del límite | `limite_aportaciones_cargos_anual` |
| L-004 | El gasto electoral que cuenta no supera el límite (habitantes × tarifa + adicional por provincia) y solo existe si hay proceso electoral | `gasto_electoral_euros_por_habitante`, `gasto_electoral_adicional_por_provincia` |
| L-005 | El endeudamiento previsto no supera el límite | `limite_endeudamiento` |
| L-006 | Todas las líneas siguen el cuadro de cuentas, y este está validado por el Tesorero | `cuadro_cuentas.yaml` |
| L-007 | Todos los parámetros legales están verificados y su fecha de verificación es vigente | Todos |
| L-008 | **Aviso**: donaciones y aportaciones que hay que notificar al Tribunal de Cuentas | `umbral_notificacion_tribunal_cuentas` |
| L-009 | Los ingresos de actividades propias (I.5) a partir del umbral exigen identificar al transmitente | `umbral_identificacion_actividades_propias` |
| L-010 | Sin donaciones de personas físicas que sean parte de un contrato público vigente | `donaciones_contratistas_publicos_permitidas` |
| L-011 | Sin donaciones finalistas ni revocables | `donaciones_finalistas_o_revocables_permitidas` |
| L-012 | Nadie aporta a las cuentas electorales más del máximo por persona (LOREG art. 129) | `limite_aportacion_electoral_por_persona` |
| L-013 | La subvención electoral presupuestada no supera el gasto electoral (art. 127.1) — aviso | — |
| L-014 | La subvención electoral presupuestada no supera la estimada con las previsiones — aviso | `subvencion_electoral_por_concejal`, `subvencion_electoral_por_voto`, `subvencion_envio_por_elector` |
| L-015 | El gasto de campaña cae dentro del periodo electoral (art. 130) — aviso | — |

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
* **L-008** avisa de las donaciones **individuales** superiores al umbral (art. 5.Dos), de **todas** las
  de inmuebles, y de las aportaciones de un mismo aportante que, **acumuladas**, superen el umbral
  (art. 8.Tres). Es un aviso: recuerda la obligación de notificar; no comprueba que se haga.
* **L-009**: como el presupuesto trabaja con importes anuales, el Tesorero declara en cada línea de
  I.5 qué parte procede de operaciones individuales que alcanzan el umbral, y esa parte debe estar
  cubierta por transmitentes identificados. Una línea inferior al umbral no puede contener ninguna.
  Dejar la declaración vacía en una línea que alcanza el umbral **bloquea**.
* **L-010** y **L-011** se aplican a las donaciones del capítulo I.4. Que un donante sea contratista
  público, y que una donación sea finalista o revocable, **lo declara el Tesorero**: el sistema no
  puede comprobarlo.
* **L-001, excepción de inmuebles**: solo se aplica si la donación está marcada «en especie (bien
  inmueble)» y el parámetro de exención está verificado. El extracto añade que deben cumplirse los
  requisitos del art. 4.Dos.e (certificación y documento que acredite la entrega); el sistema
  **no** los comprueba.
* L-004 suma como gasto electoral el capítulo G.7 y toda línea de gasto con dimensión «Campaña».

### Lo que el extracto menciona y NO está en el sistema

| Artículo del extracto | Motivo |
|---|---|
| 6.Uno: los partidos no pueden desarrollar actividades de carácter mercantil | Es una decisión de calificación para el asesor. El sistema solo ofrece la etiqueta de origen `ACTIVIDAD_MERCANTIL` (L-002). **Conviene que el asesor revise partidas como la venta de merchandising (I.5.1)**, que también aparece en los datos de demostración |
| 4.Dos.b-d y 8.Uno-Dos: cuentas bancarias exclusivas y constancia de ingresos | Fuera del alcance del sistema (no hay conciliación bancaria, `CLAUDE.md` §16.1) |
| 4.Dos.f-g: devolución del exceso y plazo de tres meses para devolver o ingresar en el Tesoro | Obligaciones posteriores a la ejecución; no son parte del presupuesto |
| 7.Uno: donaciones de personas físicas extranjeras y control de cambios | No modelado; el donante no lleva nacionalidad |

## Reglas orgánicas (O)

Son funciones puras que el flujo (`apps/flujo`) conecta a la votación y a la ratificación: ya se
aplican al cerrar la votación (O-001, O-003) y al registrar el acuerdo de la Junta (O-002, O-004).
O-001 y O-003 se comprueban también al votar. Ver `docs/flujo.md`.

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

## Fase 6: campaña

L-004 y L-012 a L-015 y V-011 se explican en `docs/campana_y_comparativa.md`. L-007 solo exige verificar
los parámetros `ELECTORAL` en ejercicios con proceso electoral y no exige los `informativo`.
