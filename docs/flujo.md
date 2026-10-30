# Flujo de aprobación del presupuesto

Resumen de cómo recorre el presupuesto desde el borrador hasta su ratificación (`CLAUDE.md` §5).
No hay saltos de estado: ni la aplicación ni la base de datos los permiten.

```
 BORRADOR ──proponer──▶ PROPUESTO ──votación aprobada──▶ APROBADO_CP ──Junta ratifica──▶ RATIFICADO_JG
    ▲                      │  │                              │   │
    └──── devolver ────────┘  └─ votación rechazada          │   └─ Junta rechaza
                               ▼                             ▼
                           RECHAZADO ◀───────────────────────┘      (y se abre un nuevo borrador)

 Modificación aprobada solo por la CP (no supera el umbral):  APROBADO_CP ──▶ MODIFICADO
```

## Quién hace qué

| Paso | Quién | Qué ocurre |
|---|---|---|
| **Proponer** | Tesorero | Se ejecutan las 21 reglas (incluida la memoria completa, V-008). Si hay bloqueos, no avanza. Los avisos hay que aceptarlos (queda constancia). Se **sella** con una huella (SHA-256), deja de poder editarse y se abre la votación. |
| **Devolver** | Comisión Permanente | Con motivos. La versión vuelve a borrador y la votación se anula. |
| **Votar** | Cada miembro de la CP | Voto **nominal** (a favor, en contra o abstención). Se puede cambiar mientras la votación esté abierta. |
| **Cerrar la votación** | Un miembro de la CP | Sin quórum no se puede cerrar. Con quórum y mayoría, se aprueba; con quórum sin mayoría, se rechaza y se abre un nuevo borrador. |
| **Convocatoria** | Tesorero o Junta | Registra cuándo se convocó a la Junta (regla O-004). |
| **Ratificar** | Quien permita `ratificacion_registrada_por` (por defecto, solo la Junta General) | Fecha de la sesión, resultado y referencia al **acta** (regla O-002). |
| **Modificar** | Tesorero | Crea un borrador nuevo copiando la versión vigente, con justificación. |

## Reglas de este flujo

* **Miembros de la CP** = usuarios activos con el rol «Comisión Permanente». Los de demostración
  votan solo en versiones de demostración y los reales, en las reales.
* **Quórum y mayoría** salen de `config/reglas_organicas.yaml`. **Sin valores, la votación queda
  bloqueada.** Los totales (asistentes, a favor, en contra, abstenciones) se calculan del voto
  nominal y se fijan al cerrar.
* **Quien propone** solo puede votar si `proponente_puede_votar` es `true` (regla O-003). Sin
  valor, se aplica la opción prudente: no puede.
* **Modificaciones:** si el cambio no supera `umbral_modificacion_junta`, la aprueba solo la CP y
  la versión queda como `MODIFICADO`. Sin umbral configurado, **toda modificación vuelve a la
  Junta**. Una transferencia entre partidas que no cambia los totales solo necesita a la CP si
  `transferencias_solo_cp` es `true`.
* **Prórroga:** a partir del 1 de enero, si el ejercicio no tiene presupuesto aprobado y el
  anterior sí, se ofrece una **prórroga provisional** con las líneas recurrentes del anterior (sin
  la campaña ni lo extraordinario). Sigue el ciclo normal.
* **Comentarios:** la CP y el Tesorero pueden comentar una versión (o una línea) desde que se
  propone, y marcarlos como resueltos. Los comentarios no son cifras, así que no sellan nada.

## La huella y la integridad

* La huella cubre el ejercicio, la versión, todas las líneas (con hipótesis e importes
  mensuales), las donaciones y, desde la Fase 5 (huella de tipo 2), la **memoria explicativa** y el
  **saldo inicial de tesorería**. Cualquier cambio de contenido cambia la huella. Las versiones
  selladas antes siguen verificándose con su tipo de huella (1). Ver `docs/anexos.md`.
* Cada transición se anota en la **hoja de control** encadenando la anterior: quitar o alterar una
  entrada rompe la cadena.
* La pantalla **Historial y huella** (y el comando `verificar_integridad`) recalculan todo y avisan
  si algo no cuadra. La votación, la ratificación y los certificados **se niegan** si la versión
  está alterada.

## Inmutabilidad en la base de datos

Disparadores de PostgreSQL (migración `flujo/0002`) que rechazan, incluso con SQL directo:

* cambiar el contenido de una versión que no sea borrador;
* transiciones de estado no permitidas, y cambiar la huella o el proponente de una versión sellada;
* modificar o borrar transiciones, convocatorias, ratificaciones y votaciones cerradas con sus votos;
* borrar versiones.

Única excepción: el borrado de **datos de demostración** (`borrar_demo`), que solo puede tocar filas
marcadas como demostración.

## Certificados

Desde una versión aprobada, **Certificados de aprobación** genera en HTML o **PDF** el certificado de
la Comisión Permanente o de la Junta General. Lleva los datos de quien certifica (nombre, DNI y
cargo, del panel de la organización), cifras, asistentes, huella y líneas de firma a mano. No es una
firma electrónica. Los de demostración salen marcados «sin validez». **El PDF es la única excepción
a la regla de salir solo en Excel y HTML** (petición expresa del Tesorero).

## Panel de la organización

Solo el Tesorero. Aquí se escriben: el nombre de la organización y la localidad, cómo se llama el
cargo de Tesorería (Tesorero, Gerente…), la **lista de cargos** (uno por línea) y las **personas**
(nombre, apellidos, DNI y cargo o cargos, con su cuenta de usuario si tienen).
