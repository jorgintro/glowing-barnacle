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

| Ejercicio | Versión | Estado | Campaña | Para qué sirve |
|---|---|---|---|---|
| 2027 | v1 | `RECHAZADO` | Sí | Rechazo de la Junta; origen de la v2 |
| 2027 | v2 | `RATIFICADO_JG` | Sí | Presupuesto completo con los 13 capítulos |
| 2027 | v3 | `MODIFICADO` | Sí | Modificación derivada de la ratificada |
| 2028 | v1 | `BORRADOR` | No | Borrador correcto para editar |
| 2029 | v1 | `PROPUESTO` | No | Pendiente de votación de la CP |
| 2030 | v1 | `APROBADO_CP` | No | Pendiente de ratificación |
| 2031 | v1 | `BORRADOR` | Sí | **Casos que incumplen reglas** |

Usuarios: `demo_cp1`, `demo_cp2`, `demo_cp3` (Comisión Permanente) y `demo_junta` (Junta General).

### Defectos deliberados del ejercicio 2031

| Regla | Defecto |
|---|---|
| V-001 | Una línea cuyos meses no suman su importe anual |
| V-003 | Una línea sin cuenta del PGC y otra con una cuenta que no es de su partida |
| V-004 | Una línea sin hipótesis y otra sin responsable |
| V-005 | Un importe negativo marcado como ajuste sin justificación |
| V-006 | Déficit sin plan de financiación |
| V-007 | Variación enorme respecto al ejercicio anterior sin justificar |

Los casos de las reglas legales (L-) y orgánicas (O-) se añaden en las fases 3 y 4, cuando existan
los donantes y la votación.

> Las versiones demo en estado `PROPUESTO`, `APROBADO_CP` y `RATIFICADO_JG` se han sembrado
> directamente, sin huella (hash). Se sellarán cuando exista el flujo de la Fase 4.
