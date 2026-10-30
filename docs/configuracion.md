# Ficheros de configuración

Todo lo que depende de la normativa o de los estatutos vive en `config/`, **fuera del código**
(CLAUDE.md §3 y §9.4). Se cargan en la base de datos con `python manage.py sincronizar_configuracion`
(el arranque de Docker lo hace solo). La sincronización es idempotente y no borra nada: lo que
desaparece de un fichero se marca como inactivo. Cada cambio queda en la auditoría.

## `config/cuadro_cuentas.yaml`

Estructura del presupuesto (13 capítulos, partidas) y mapeo de cada partida a cuentas del PGC.

* **Estado: orientativo.** Procede del apartado 3.3 de CLAUDE.md. Hasta que el Tesorero o su
  asesor lo valide, rellenando `validado_por` y `fecha_validacion`, la aplicación lo muestra como
  «pendiente de validación».
* Las cuentas acabadas en «x» (por ejemplo `62x`) son grupos que hay que concretar.
* La partida `G.8.1` (imprevistos) usa `65x` provisionalmente: CLAUDE.md §3.3 no le asigna cuenta.
* Una línea solo admite cuentas de su partida; si no, se rechaza (regla V-003).

## `config/parametros_legales.yaml`

Límites y prohibiciones legales (donaciones, gasto electoral, endeudamiento…).

* **Ningún parámetro está verificado** y el fichero no afirma que ninguna norma esté vigente.
* **Estado actual de la verificación (honesto):**
  * Los 4 primeros parámetros (50.000 € por donante, anónimas, personas jurídicas, fuentes
    prohibidas) figuran **verificados** porque el Tesorero lo **declaró** en la sesión del
    29/10/2026. El sistema no puede comprobarlo. El campo «verificador» dice «Tesorero de
    Iniciativa Complutense (declaración…)»: **sustitúyelo por tu nombre**.
  * Otros 5 parámetros del mismo extracto (umbral de notificación 25.000 €, umbral de
    identificación 300 €, contratistas públicos, finalistas o revocables, exención de inmuebles)
    se verificaron después, también por **declaración del Tesorero** (29/10/2026).
  * Aportaciones de cargos, gasto electoral y endeudamiento siguen **sin valor**, y por tanto
    pendientes: mientras sigan así, L-007 bloquea toda versión real.
* Cuatro parámetros llevan ya **valor y referencia** tomados del extracto de la ley que aportó el
  Tesorero (`docs/fuentes_normativas/`): 50.000 € por donante y año (art. 5.Uno.b), donaciones
  anónimas no permitidas (art. 5.Uno.a), donaciones de personas jurídicas no permitidas (art.
  5.Uno.c y 4.Dos.a) y una lista de fuentes prohibidas. **Siguen «pendientes»** porque faltan la
  fecha de verificación y el verificador, que solo puede poner el Tesorero o su asesor tras
  contrastarlos con el BOE consolidado. Aportaciones de cargos, gasto electoral y endeudamiento
  no figuran en el extracto y siguen sin valor.
* La lista `fuentes_ingreso_prohibidas` usa **etiquetas elegidas por el sistema** a partir del
  extracto (`DONACION_ANONIMA`, `ACTIVIDAD_MERCANTIL`…). Se escriben en el campo «Origen del
  ingreso» de cada línea. Confírmalas o corrígelas al verificarlas.
* Para dar un parámetro por válido hay que rellenar **valor, `referencia_normativa`,
  `fecha_verificacion` (AAAA-MM-DD) y `verificador`** tras comprobarlo contra el BOE.
  Con cualquier campo vacío sigue «pendiente de verificación».
* Los importes se escriben **como texto**: `valor: "1234.56"`. Un número decimal sin comillas se
  rechaza para evitar errores de coma flotante.
* `norma_orientativa` solo apunta a las normas citadas en CLAUDE.md §3.1; no es una referencia
  verificada.

### Marcas `ambito` e `informativo` de los parámetros legales

* `ambito: ELECTORAL`: el parámetro solo se exige verificado (L-007) en ejercicios con proceso
  electoral. Sin esta marca es `GENERAL`.
* `informativo: true`: el parámetro solo alimenta estimaciones y calendarios (importes de
  subvención y plazos); L-007 no lo exige, pero la pantalla muestra «sin verificar» si lo está.
* Unidad `DIAS`: número entero de días (texto, p. ej. `"100"`).
* Los parámetros electorales de `config/parametros_legales.yaml` proceden del extracto del
  30/10/2026 y son los de las elecciones locales de 2023; **figuran sin verificar**.

## `config/parametros_internos.yaml`

Ajustes del sistema que no son normativa legal. **Sin valores a propósito**:

* `umbral_variacion_porcentaje` (V-007): variación máxima, en %, respecto al ejercicio anterior sin
  justificar. Se escribe como texto, p. ej. `"20"`.
* `exigir_ventana_verificacion` (L-007): verificación en el año del ejercicio o el anterior.

## `config/memoria.yaml`

Valores **propuestos** de la memoria explicativa (secciones, ayudas, plantillas, mínimos) y del plan
de tesorería. No es normativa: solo **siembra** la base de datos la primera vez y, a partir de ahí,
todo se edita desde el panel **Anexos** (los cambios no se pisan al reiniciar). Detalle en
`docs/anexos.md`. `config/demo/memoria.yaml` trae los parámetros ficticios de la demostración.

## `config/reglas_organicas.yaml`

Quórum, mayorías y funciones (CLAUDE.md §16.2). **Sin valores a propósito**: salen de los
estatutos. Mientras estén vacíos, **la votación de la Comisión Permanente queda bloqueada** (O-001).
El fichero incluye ejemplos comentados con la forma de cada dato. Claves:

| Clave | Para qué | Si está vacía |
|---|---|---|
| `quorum` y `mayoria` | Votación de la CP (regla O-001) | La votación queda bloqueada |
| `proponente_puede_votar` | Regla O-003 | Quien propone no puede votar |
| `ratificacion_registrada_por` | Quién registra la ratificación (`JUNTA_GENERAL`, `TESORERO`) | Solo la Junta General |
| `umbral_modificacion_junta` | A partir de cuánto una modificación vuelve a la Junta (`IMPORTE` o `PORCENTAJE`) | Toda modificación vuelve a la Junta |
| `transferencias_solo_cp` | Si las transferencias entre partidas bastan con la CP | No: también van a la Junta |

## Carpeta `config/demo/` (FICTICIA)

Contiene una configuración inventada (límites, quórum, etc.) que solo usan las versiones de
demostración. **Ningún valor de esa carpeta es legal ni estatutario.** Las versiones reales usan
siempre `config/`. Las excepciones pedidas para la demostración (el Tesorero vota y registra la
ratificación) viven solo ahí. Una prueba comprueba que la estructura del cuadro demo coincide con
la del real.

## Cómo verificar un parámetro legal (paso a paso)

Ejemplo: que no se admiten donaciones de personas jurídicas.

1. Comprueba la norma vigente en el BOE (o con tu asesor) y anota **la referencia exacta**.
2. En `config/parametros_legales.yaml`, rellena **los cuatro campos** del parámetro:

   ```yaml
   - clave: donaciones_personas_juridicas_permitidas
     ...
     valor: false
     referencia_normativa: "Cita exacta de la norma y el artículo"
     fecha_verificacion: 2026-10-29
     verificador: "Nombre de quien lo ha comprobado"
   ```
3. Reinicia o redespliega para que la aplicación lea el fichero. Con cualquier campo vacío el
   parámetro sigue «pendiente» y las reglas que dependen de él no se dan por cumplidas.
4. Los importes van como texto entre comillas: `valor: "1234.56"`.

## Variables de entorno relacionadas

| Variable | Efecto |
|---|---|
| `CONFIG_DIR` | Carpeta de los ficheros de configuración (por defecto `config/`). |
| `PERMITIR_DATOS_DEMO` | `0` impide cargar datos de demostración (poner a `0` con datos reales). |
