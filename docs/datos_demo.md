# Datos de demostración

**Todo es ficticio.** Las cifras, los nombres y las resoluciones están inventados para probar el
sistema; no representan a ninguna organización real. Están marcados con `es_demo` y con la
etiqueta «DEMO · datos ficticios» en la interfaz, y nunca se mezclan con los reales.

## Cargar y borrar

```bash
python manage.py cargar_demo
python manage.py borrar_demo --confirmar
```

En Docker: `docker exec -it presupuesto-web-1 python manage.py cargar_demo` (ajusta el nombre del
contenedor si es otro).

* `cargar_demo` imprime las contraseñas de los usuarios de demostración **una sola vez**.
  Se generan al azar; no hay contraseñas fijas.
* `borrar_demo` elimina solo lo marcado como demo, incluido su rastro de auditoría. Lo real no se
  toca, y queda una anotación `demo.borrar` (no demo) en la auditoría.
* Con `PERMITIR_DATOS_DEMO=0` la carga se niega. Úsalo cuando empieces con datos reales.

## Qué contiene

Todo se crea **recorriendo el flujo real** (proponer, votar, cerrar, convocar y ratificar con los
usuarios de demostración), así que también sirve de prueba del flujo.

| Ejercicio | Versión | Estado | Campaña | Para qué sirve |
|---|---|---|---|---|
| 2027 | v1 | `RECHAZADO` | Sí | Aprobada por la CP y rechazada por la Junta |
| 2027 | v2 | `RATIFICADO_JG` | Sí | Presupuesto completo, ratificado (lo registra el Tesorero de la demo) |
| 2027 | v3 | `MODIFICADO` | Sí | Modificación pequeña (400 €) aprobada solo por la CP |
| 2028 | v1 | `BORRADOR` | No | Borrador correcto para editar y proponer |
| 2029 | v1 | `PROPUESTO` | No | Votación abierta con un solo voto (para probar votar y cerrar) y un comentario |
| 2030 | v1 | `APROBADO_CP` | No | Votación cerrada y convocatoria registrada; falta ratificar |
| 2031 | v1 | `BORRADOR` | Sí | **Casos que incumplen reglas** |
| 2032 | v1 | `RECHAZADO` | No | Rechazada por la CP (con un nuevo borrador v2 abierto automáticamente) |

Usuarios (contraseñas aleatorias que se muestran **una sola vez** al cargar):

| Usuario | Roles | Papel en la demo |
|---|---|---|
| `demo_tesorero` | Tesorero y Comisión Permanente | Propone y también vota |
| `demo_cp1`, `demo_cp2`, `demo_cp3` | Comisión Permanente | Votan |
| `demo_junta` | Junta General | Convoca y ratifica |

También hay personas ficticias en el panel de la organización (con DNI de prueba y cargos «(demo)»)
para poder probar los certificados.

### Memoria y tesorería de la demostración

Las versiones de demostración correctas (2027 a 2030 y 2032) llevan una memoria **ficticia**
completa (las cinco secciones escritas a mano, con texto de relleno) y un saldo inicial ficticio de
200.000,00 €. El ejercicio 2031 (el de los defectos) tiene la memoria **a medias y sin saldo
inicial, a propósito**, para ver V-008 y V-009. Los parámetros de tesorería de la demo
(`config/demo/memoria.yaml`) son inventados.

### Defectos deliberados del ejercicio 2031

Se comprueban con la configuración **ficticia** de `config/demo/` (límites inventados: 1.500 € por
donante, 2.000 € por aportante, 15.000 € de gasto electoral, 5.000 € de endeudamiento, 3.000 € de aviso
de notificación y 150 € de identificación).

| Regla | Defecto |
|---|---|
| V-001 (y V-002) | Una línea cuyos meses no suman su importe anual |
| V-003 (y L-006) | Una línea sin cuenta del PGC y otra con una cuenta que no es de su partida |
| V-004 | Una línea sin hipótesis y otra sin responsable |
| V-005 | Un importe negativo marcado como ajuste sin justificación |
| V-006 | Sin explicación del resultado y déficit sin plan de financiación |
| V-007 (aviso) | Variación enorme respecto al ejercicio anterior sin justificar |
| V-008 | Memoria a medias: solo el resumen y el contexto; faltan las demás secciones |
| V-009 (aviso) | Sin saldo inicial de tesorería |
| L-001 | Un donante que supera el límite anual, una persona jurídica que dona y un importe sin donante identificado |
| L-002 | Un ingreso con origen en la lista de fuentes prohibidas |
| L-003 | Un cargo que supera el límite de aportaciones y una aportación sin identificar |
| L-004 | Gasto de campaña de 16.000 € frente a un límite ficticio de 15.000 € |
| L-005 | Endeudamiento de 8.000 € frente a un límite ficticio de 5.000 € |
| L-008 (aviso) | Donación de un inmueble de 4.000 € (más que el umbral ficticio de aviso, 3.000 €); además **no** cuenta para el límite por donante, que demuestra la excepción |
| L-009 | Ventas individuales de 400 € declaradas como «operaciones altas» sin identificar al transmitente (umbral ficticio: 150 €) |
| L-010 | Donación de un «contratista público» ficticio |
| L-011 | Una donación finalista y otra revocable |

Las demás versiones de demostración (2027–2030) **superan todas las reglas V y L (21 reglas)** con esa
configuración. Las reglas orgánicas (O-) se demuestran en la Fase 4 con la votación y la
ratificación.

Donantes de demostración: 3 cargos (`C1`–`C3`), 8 donantes (`D1`–`D8`), un contratista público y una
empresa, todos ficticios (NIF de prueba, no pertenecen a nadie).

> Las versiones demo en estado `PROPUESTO`, `APROBADO_CP` y `RATIFICADO_JG` se han sembrado
> directamente, sin huella (hash). Se sellarán cuando exista el flujo de la Fase 4.
