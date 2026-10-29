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

* **Ningún valor está verificado** y el fichero no afirma que ninguna norma esté vigente.
* Para dar un parámetro por válido hay que rellenar **valor, `referencia_normativa`,
  `fecha_verificacion` (AAAA-MM-DD) y `verificador`** tras comprobarlo contra el BOE.
  Con cualquier campo vacío sigue «pendiente de verificación».
* Los importes se escriben **como texto**: `valor: "1234.56"`. Un número decimal sin comillas se
  rechaza para evitar errores de coma flotante.
* `norma_orientativa` solo apunta a las normas citadas en CLAUDE.md §3.1; no es una referencia
  verificada.

## `config/reglas_organicas.yaml` (Fase 4)

Quórum, mayorías y umbrales estatutarios. Aún no existe: sin valores, la votación queda bloqueada.
Para la demostración se preparará una configuración propia, separada de la real, con las
excepciones pedidas (el Tesorero vota y registra la ratificación).

## Variables de entorno relacionadas

| Variable | Efecto |
|---|---|
| `CONFIG_DIR` | Carpeta de los ficheros de configuración (por defecto `config/`). |
| `PERMITIR_DATOS_DEMO` | `0` impide cargar datos de demostración (poner a `0` con datos reales). |
