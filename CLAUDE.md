<div align="center">

# 🏛️ DOCUMENTO DE GOBIERNO
## Sistema de Elaboración y Aprobación del Presupuesto Anual
### **Iniciativa Complutense** · Partido local · Alcalá de Henares

`CLAUDE.md` · Versión **1.0** · Octubre de 2026
*Documento rector para Claude Code*

</div>

---

## 📑 Índice

1. [Propósito y alcance](#1-propósito-y-alcance)
2. [Principios rectores](#2-principios-rectores)
3. [Marco normativo y contable](#3-marco-normativo-y-contable)
4. [Actores, roles y permisos](#4-actores-roles-y-permisos)
5. [Flujo de aprobación](#5-flujo-de-aprobación)
6. [Estructura del presupuesto](#6-estructura-del-presupuesto)
7. [Anexos anuales](#7-anexos-anuales)
8. [Reglas de negocio y validaciones](#8-reglas-de-negocio-y-validaciones)
9. [Arquitectura técnica](#9-arquitectura-técnica)
10. [Modelo de datos esencial](#10-modelo-de-datos-esencial)
11. [Salidas: Excel e informe HTML](#11-salidas-excel-e-informe-html)
12. [Diseño visual](#12-diseño-visual)
13. [Auditoría, trazabilidad y seguridad](#13-auditoría-trazabilidad-y-seguridad)
14. [Calendario anual](#14-calendario-anual)
15. [Normas de trabajo para Claude Code](#15-normas-de-trabajo-para-claude-code)
16. [Fuera de alcance y decisiones abiertas](#16-fuera-de-alcance-y-decisiones-abiertas)
17. [Glosario](#17-glosario)

---

## 1. Propósito y alcance

Este documento define **qué es, qué debe hacer y cómo debe construirse** el sistema que permite a Iniciativa Complutense **elaborar, aprobar y ratificar su presupuesto anual**, con el máximo nivel de detalle y los anexos anuales que correspondan.

**El sistema debe:**

- Permitir al **Tesorero** elaborar el presupuesto, partida a partida, junto con la **Comisión Permanente**.
- Gestionar la **aprobación por la Comisión Permanente** y la posterior **ratificación por la Junta General ordinaria de noviembre**.
- Trabajar bajo el **marco normativo español** de financiación de partidos y bajo el **Plan General de Contabilidad (PGC)** y su adaptación sectorial.
- Generar el presupuesto completo y sus **anexos** en **Excel (.xlsx)** y en **informe HTML visual**.
- Conservar un **histórico inmutable** de versiones, decisiones y aprobaciones.

**El sistema NO es** un programa de contabilidad general ni de ejecución de pagos. Prepara y gobierna el presupuesto; la comparación con la ejecución real se alimenta con datos importados (véase §7.4).

---

## 2. Principios rectores

| # | Principio | Qué implica para Claude Code |
|---|-----------|------------------------------|
| 1 | **Exactitud ante todo** | Nunca usar `float` para dinero. Usar `Decimal` o enteros en céntimos. Redondeo explícito y documentado. |
| 2 | **Legalidad por diseño** | Los límites y prohibiciones legales son **reglas del sistema**, no recomendaciones. Un presupuesto que las incumpla no puede avanzar de estado. |
| 3 | **Trazabilidad total** | Todo cambio queda registrado: quién, cuándo, qué, antes y después. Nada se borra; se anula con motivo. |
| 4 | **Inmutabilidad tras aprobar** | Una versión aprobada o ratificada es de solo lectura. Los cambios generan una nueva versión (modificación presupuestaria). |
| 5 | **Transparencia** | Cualquier cifra debe poder explicarse: hipótesis, fuente y responsable. |
| 6 | **Claridad para no técnicos** | Los usuarios son voluntarios y cargos orgánicos, no contables. Lenguaje llano, avisos comprensibles. |
| 7 | **Prudencia** | Ingresos estimados con criterio conservador; gastos con previsión de contingencias. |
| 8 | **Separación de funciones** | Quien elabora no aprueba; quien aprueba no ratifica. |
| 9 | **Datos personales mínimos** | Solo se tratan los datos estrictamente necesarios (RGPD / LOPDGDD). |
| 10 | **Belleza funcional** | El resultado visual es sobrio, legible e impecable. La estética sirve a la comprensión. |

---

## 3. Marco normativo y contable

> ⚠️ **Regla de oro:** Claude Code **no debe dar por vigente de memoria** ningún artículo, umbral o plazo. Cada parámetro legal vive en un fichero de configuración (`config/parametros_legales.yaml`) con su **referencia, fecha de verificación y responsable**. Antes de cada ejercicio, el Tesorero (o su asesor) valida ese fichero contra el BOE.

### 3.1 Normas de referencia

| Ámbito | Norma | Uso en el sistema |
|--------|-------|-------------------|
| Financiación de partidos | **Ley Orgánica 8/2007**, de financiación de los partidos políticos, y sus modificaciones | Fuentes de ingreso permitidas y prohibidas, límites de donaciones, régimen de aportaciones, reglas sobre gastos. |
| Control económico-financiero | **Ley Orgánica 3/2015**, de control de la actividad económico-financiera de los partidos políticos | Obligaciones contables, rendición de cuentas, control interno. |
| Tribunal de Cuentas | **Ley Orgánica 2/1982** y normativa de fiscalización de partidos | Estructura de cuentas anuales y plazos de rendición. |
| Partidos políticos | **Ley Orgánica 6/2002**, de partidos políticos | Régimen general y principios de funcionamiento democrático. |
| Contabilidad | **Plan General de Contabilidad** (RD 1514/2007) y **adaptación sectorial para formaciones políticas** | Cuadro de cuentas, criterios de registro y valoración, estructura de cuentas anuales. |
| Procesos electorales | **LOREG** (LO 5/1985) | Límites y reglas de gastos de campaña (anexo 7.3). |
| Protección de datos | **RGPD** y **LOPDGDD** | Tratamiento de datos de afiliados y donantes. |
| Normativa interna | **Estatutos** y reglamentos de Iniciativa Complutense | Competencias de Tesorero, Comisión Permanente y Junta General. |

### 3.2 Criterios contables

- Cada partida presupuestaria se **mapea a una o varias cuentas del PGC** (grupos 6 y 7 principalmente). El mapeo vive en `config/cuadro_cuentas.yaml`.
- El presupuesto se presenta en **estructura compatible con la cuenta de resultados** de las cuentas anuales, para que la comparativa con la ejecución sea directa.
- Principios contables aplicables: **empresa en funcionamiento, devengo, uniformidad, prudencia, no compensación, importancia relativa**.
- Moneda: **euro**, con dos decimales. Periodo: **ejercicio natural** (1 de enero a 31 de diciembre), salvo disposición estatutaria distinta.

### 3.3 Mapeo orientativo a cuentas del PGC

> Orientativo. El Tesorero lo valida y fija en `config/cuadro_cuentas.yaml`.

| Partida del presupuesto | Cuentas PGC orientativas |
|-------------------------|--------------------------|
| Cuotas de afiliados | 720 |
| Aportaciones de cargos públicos | 72x / 74x (según criterio sectorial) |
| Subvenciones públicas (funcionamiento y grupos municipales) | 740 / 747 |
| Donaciones | 74x / 72x (según criterio sectorial) |
| Otros ingresos (actos, merchandising) | 70x / 75x |
| Gastos de personal | 640, 642 |
| Servicios exteriores (alquileres, suministros, asesoría) | 621, 622, 623, 628 |
| Publicidad y propaganda | 627 |
| Gastos de actividades y órganos | 62x / 65x |
| Gastos financieros | 66x |
| Amortizaciones | 68x |
| Gastos electorales | 62x / 65x con dimensión «campaña» |

---

## 4. Actores, roles y permisos

El sistema define **tres roles**, alineados con los órganos del partido.

| Rol | Quién | Puede | No puede |
|-----|-------|-------|----------|
| ✏️ **Tesorero** | Tesorero/a de Iniciativa Complutense | Crear y editar borradores; gestionar partidas, hipótesis y anexos; proponer a la Comisión Permanente; generar salidas; importar ejecución real. | Aprobar su propia propuesta. Modificar versiones aprobadas. |
| 🗳️ **Comisión Permanente** | Miembros de la Comisión Permanente | Consultar, comentar, solicitar cambios, **votar** la aprobación; devolver al Tesorero con motivos. | Editar cifras directamente. Ratificar. |
| 📜 **Junta General** | Asamblea ordinaria (acceso para consulta y registro del acuerdo) | Consultar la versión aprobada y sus anexos; **registrar la ratificación** o el rechazo (por el Secretario o persona designada en acta). | Editar el presupuesto. |

**Reglas de permisos**

- Autenticación nominal; un usuario, un rol activo por sesión.
- Toda acción sensible (proponer, votar, ratificar, anular) exige **confirmación explícita** y deja registro.
- El registro de la **ratificación de la Junta** requiere indicar: fecha de la sesión, resultado, y referencia al acta.
- Los cambios de rol los realiza únicamente el Tesorero y quedan registrados.

---

## 5. Flujo de aprobación

El presupuesto avanza por **estados bloqueantes**. Cada transición congela una versión y exige superar las validaciones del §8.

```
   ┌────────────┐   Proponer    ┌────────────┐   Aprobar (votación)   ┌───────────────┐   Ratificar    ┌────────────────┐
   │  BORRADOR  │ ────────────▶ │  PROPUESTO │ ─────────────────────▶ │ APROBADO (CP) │ ─────────────▶ │ RATIFICADO (JG)│
   │ Tesorero   │               │ Comisión   │                        │ Comisión      │                │ Junta General  │
   └────────────┘               └────────────┘                        └───────────────┘                └────────────────┘
         ▲                            │                                      │                                  │
         │        Devolver con        │                  Rechazo             │            Rechazo               │
         └──────── motivos ◀──────────┘                  ▼                   │               ▼                  ▼
                                                    vuelve a BORRADOR        └──────▶ vuelve a BORRADOR   VIGENTE EN EL EJERCICIO
                                                                                                                │
                                                                                          Modificaciones ──▶ nueva versión
```

### 5.1 Estados

| Estado | Responsable | Editable | Condición para entrar |
|--------|-------------|:--------:|------------------------|
| `BORRADOR` | Tesorero | ✅ | Creación o devolución. |
| `PROPUESTO` | Tesorero → CP | ❌ | Validaciones superadas + memoria explicativa completa. |
| `APROBADO_CP` | Comisión Permanente | ❌ | Votación registrada con quórum y mayoría según estatutos. |
| `RATIFICADO_JG` | Junta General | ❌ | Acuerdo de la Junta registrado con referencia al acta. |
| `RECHAZADO` | CP o JG | ❌ | Registro del motivo; origina un nuevo `BORRADOR`. |
| `MODIFICADO` | Procedimiento de modificación (§5.3) | ❌ | Nueva versión derivada de una ratificada. |

### 5.2 Reglas de transición

1. **No hay saltos de estado.** Solo se avanza o se devuelve a `BORRADOR`.
2. Cada transición genera una **versión sellada** con huella digital (hash) de su contenido.
3. La **votación de la Comisión Permanente** registra: asistentes, quórum, votos a favor, en contra y abstenciones, y observaciones. Los umbrales de quórum y mayoría se leen de `config/reglas_organicas.yaml`, conforme a los estatutos.
4. Si la Junta General no ratifica, el sistema abre un nuevo borrador a partir de la última versión y conserva el rechazo en el histórico.
5. **Prórroga:** si a 1 de enero no hubiera presupuesto ratificado, el sistema ofrece al Tesorero generar un **presupuesto prorrogado** del ejercicio anterior, marcado de forma visible como provisional y sujeto a ratificación en la siguiente Junta.

### 5.3 Modificaciones durante el ejercicio

- Todo cambio sobre un presupuesto ratificado crea una **modificación presupuestaria** con justificación y repite el ciclo CP → (JG si supera el umbral que fijen los estatutos o el reglamento interno).
- El umbral que obliga a nueva ratificación de la Junta es un parámetro configurable: `umbral_modificacion_junta` (importe o porcentaje).
- Las **transferencias entre partidas** que no alteren el total pueden aprobarse solo por la CP si así lo prevé el reglamento interno.

---

## 6. Estructura del presupuesto

El presupuesto se elabora con **detalle completo**: capítulo → partida → subpartida → línea, con distribución mensual.

### 6.1 Jerarquía

```
Presupuesto del ejercicio
 ├── INGRESOS
 │    ├── I.1  Cuotas de afiliados
 │    ├── I.2  Aportaciones de cargos públicos
 │    ├── I.3  Subvenciones públicas
 │    ├── I.4  Donaciones
 │    └── I.5  Otros ingresos
 ├── GASTOS
 │    ├── G.1  Gastos de personal
 │    ├── G.2  Servicios exteriores y funcionamiento
 │    ├── G.3  Actividades y órganos del partido
 │    ├── G.4  Comunicación, publicidad y propaganda
 │    ├── G.5  Gastos financieros
 │    ├── G.6  Amortizaciones
 │    ├── G.7  Gastos electorales (solo si hay proceso electoral)
 │    └── G.8  Imprevistos y contingencias
 └── RESULTADO PRESUPUESTARIO (superávit / déficit) y financiación
```

### 6.2 Detalle por capítulo de ingresos

| Capítulo | Detalle mínimo | Método de estimación | Controles específicos |
|----------|----------------|----------------------|-----------------------|
| **I.1 Cuotas de afiliados** | Nº de afiliados × cuota × meses; altas y bajas previstas; morosidad estimada | Base de afiliados al cierre del ejercicio anterior + tendencia | Previsión de impagos prudente. |
| **I.2 Aportaciones de cargos** | Por cargo o grupo de cargos; importe y periodicidad | Según compromisos o reglamento interno | Coherencia con retribuciones y normativa de aportaciones. |
| **I.3 Subvenciones públicas** | Subvención por representación municipal; aportaciones a grupos municipales; otras | Resoluciones y normativa de concesión | Distinguir subvención al **partido** de la asignación a **grupos municipales**. Solo ingresos con base cierta. |
| **I.4 Donaciones** | Donaciones dinerarias y en especie; número y tramos de donantes | Histórico y campañas previstas | **Límites legales por donante y prohibiciones** (§8.2). |
| **I.5 Otros ingresos** | Actos, merchandising, rendimientos financieros, otros | Histórico y plan de actividades | Ingresos ligados a actividad propia, no a financiación prohibida. |

### 6.3 Detalle por capítulo de gastos

| Capítulo | Detalle mínimo |
|----------|----------------|
| **G.1 Personal** | Puesto, tipo de contrato, bruto, cotización a cargo de la empresa, periodo. |
| **G.2 Servicios exteriores** | Sede y alquileres, suministros, asesoría y gestoría, seguros, material, mantenimiento, TIC. |
| **G.3 Actividades y órganos** | Juntas y asambleas, Comisión Permanente, formación, actos y jornadas, desplazamientos. |
| **G.4 Comunicación** | Web y redes, imprenta, cartelería, publicidad, material divulgativo. |
| **G.5 Financieros** | Comisiones bancarias, intereses de préstamos. |
| **G.6 Amortizaciones** | Inventario de inmovilizado y cuota anual. |
| **G.7 Electorales** | Ver anexo 7.3. Imputación separada y límites legales. |
| **G.8 Imprevistos** | Reserva de contingencia con límite porcentual configurable. |

### 6.4 Atributos de cada línea presupuestaria

Cada línea incluye siempre:

- **Código** (jerárquico, ej. `G.2.1.03`) y **denominación**.
- **Cuenta PGC** asociada.
- **Importe anual** y **distribución mensual** (para el plan de tesorería).
- **Hipótesis y fuente** (texto obligatorio, no vacío).
- **Responsable** (persona o área).
- **Tipo**: recurrente, extraordinario, condicionado.
- **Dimensión**: ordinario / campaña / grupo municipal.
- **Importe ejercicio anterior** y **ejecución real** (si hay datos) para comparar.
- **Estado de confianza** (alta / media / baja) para ingresos.

---

## 7. Anexos anuales

El sistema genera los siguientes anexos, vinculados a cada versión del presupuesto y sellados con ella.

### 7.1 📝 Memoria explicativa

Documento narrativo que acompaña al presupuesto. Estructura obligatoria:

1. Resumen ejecutivo: totales, resultado y principales variaciones.
2. Contexto del ejercicio (actividad prevista, hitos, elecciones).
3. Criterios de elaboración e hipótesis por capítulo.
4. Riesgos e incertidumbres (subvenciones, afiliación, campaña).
5. Cumplimiento normativo: lista de comprobaciones superadas.
6. Propuesta de acuerdo para la Comisión Permanente y la Junta General.

El sistema **bloquea la propuesta** si la memoria no está completa.

### 7.2 📅 Plan de tesorería mensual

- Previsión de **cobros y pagos mes a mes**, derivada de la distribución mensual de las líneas.
- Saldo inicial, flujo neto y **saldo final por mes**.
- **Alerta** de tensión de tesorería si el saldo previsto es negativo o inferior a un mínimo configurable (`saldo_minimo_tesoreria`).
- Escenarios: **base**, **prudente** (menos ingresos) y **ajustado** (menos gastos).

### 7.3 🗳️ Presupuesto de campaña

Aplicable solo cuando existe proceso electoral previsto en el ejercicio.

- Gastos electorales desglosados por concepto, con **límite legal aplicable** como parámetro verificado.
- Fuentes de financiación de la campaña (subvención electoral prevista, aportaciones, donaciones, endeudamiento).
- Calendario de campaña y distribución temporal.
- Control específico: el gasto electoral se **imputa de forma separada** y no se mezcla con el ordinario.
- Alerta si se acerca o supera el límite.

### 7.4 📊 Comparativa y desviaciones

- **Presupuesto vs. ejercicio anterior** (variación absoluta y porcentual).
- **Presupuesto vs. ejecución real** a una fecha de corte.
- Semáforo por partida (verde / ámbar / rojo) según umbrales configurables.
- Entrada de datos reales mediante **importación de Excel/CSV** con plantilla validada. El sistema no sustituye a la contabilidad: solo la consume.

### 7.5 Otros elementos que acompañan a cada versión

- **Hoja de control de versiones** (quién, cuándo, estado, hash).
- **Acta-resumen de votación** de la Comisión Permanente.
- **Registro de ratificación** de la Junta General.
- **Checklist de cumplimiento normativo** firmado por el Tesorero.

---

## 8. Reglas de negocio y validaciones

Las validaciones se ejecutan **antes de cada transición de estado** y también en tiempo real durante la edición. Se clasifican en **bloqueantes** (impiden avanzar) y **avisos** (se muestran y requieren constancia).

### 8.1 Validaciones aritméticas y de coherencia

| Código | Regla | Tipo |
|--------|-------|------|
| `V-001` | La suma de los meses de cada línea es igual al importe anual. | 🔴 Bloqueante |
| `V-002` | Los totales de capítulo coinciden con la suma de sus líneas. | 🔴 Bloqueante |
| `V-003` | Toda línea tiene cuenta PGC válida. | 🔴 Bloqueante |
| `V-004` | Toda línea tiene hipótesis y responsable. | 🔴 Bloqueante |
| `V-005` | Importes con dos decimales; sin valores negativos salvo ajustes justificados. | 🔴 Bloqueante |
| `V-006` | Resultado presupuestario calculado y explicado. Un déficit exige plan de financiación. | 🔴 Bloqueante |
| `V-007` | Variación superior al umbral configurado respecto al ejercicio anterior exige justificación. | 🟡 Aviso |
| `V-008` | La memoria explicativa está completa (§7.1). | 🔴 Bloqueante |
| `V-009` | Está indicado el saldo inicial de tesorería (§7.2). | 🟡 Aviso |
| `V-010` | Sin tensión de tesorería (saldo negativo o bajo el mínimo) en el escenario base (§7.2). | 🟡 Aviso |

### 8.2 Validaciones legales

| Código | Regla | Tipo |
|--------|-------|------|
| `L-001` | Las donaciones respetan el **límite anual por donante** y las **prohibiciones** previstas en la normativa de financiación (donantes no identificados, personas jurídicas no permitidas, etc.), según `parametros_legales.yaml`. | 🔴 Bloqueante |
| `L-002` | No hay ingresos de fuentes prohibidas. | 🔴 Bloqueante |
| `L-003` | Las aportaciones de cargos públicos respetan los criterios de identificación y límites aplicables. | 🔴 Bloqueante |
| `L-004` | El gasto electoral no supera el límite legal del proceso correspondiente. | 🔴 Bloqueante |
| `L-005` | El endeudamiento previsto es compatible con las condiciones legales de crédito a partidos. | 🔴 Bloqueante |
| `L-006` | El presupuesto sigue la estructura exigida por el cuadro de cuentas adaptado. | 🔴 Bloqueante |
| `L-007` | Parámetros legales verificados en el ejercicio en curso (fecha de verificación vigente). | 🔴 Bloqueante |

### 8.3 Validaciones orgánicas

| Código | Regla | Tipo |
|--------|-------|------|
| `O-001` | La Comisión Permanente alcanza quórum y mayoría según estatutos. | 🔴 Bloqueante |
| `O-002` | La ratificación se registra con fecha, resultado y referencia al acta. | 🔴 Bloqueante |
| `O-003` | Quien propone no puede votar como miembro de la CP en la misma versión si el reglamento lo impide. | 🔴 Bloqueante |
| `O-004` | La convocatoria de la Junta se ha registrado antes de la ratificación. | 🟡 Aviso |

> Al añadir una regla nueva, Claude Code debe **documentarla aquí**, **añadir pruebas automáticas** y **referenciar su fuente normativa**.

---

## 9. Arquitectura técnica

### 9.1 Tipo de solución

**Aplicación web** con usuarios, roles, base de datos y generación de documentos.

### 9.2 Stack por defecto

> Es una propuesta razonada. Claude Code puede proponer otro, pero debe **justificarlo por escrito** en `docs/decisiones/` antes de cambiarlo.

| Capa | Elección por defecto | Motivo |
|------|----------------------|--------|
| Lenguaje | **Python 3.12+** | Manejo robusto de `Decimal`, ecosistema de informes y hojas de cálculo. |
| Framework web | **Django** | Autenticación, permisos, administración y migraciones incluidas; ideal para sistemas de registro y auditoría. |
| Base de datos | **PostgreSQL** | Integridad transaccional, restricciones y tipos numéricos exactos. |
| Excel | **openpyxl** o **XlsxWriter** | Libros con fórmulas vivas, formatos y varias pestañas. |
| Informe HTML | **Plantillas Jinja/Django** + CSS propio, gráficos **SVG/JS ligeros** | Documento autónomo, imprimible y bonito. |
| Pruebas | **pytest** + **pytest-django** | Cobertura de reglas de negocio. |
| Calidad | **ruff**, **mypy**, **pre-commit** | Código limpio y tipado. |
| Contenedores | **Docker Compose** | Entorno reproducible. |

### 9.3 Estructura de carpetas sugerida

```
iniciativa-presupuesto/
├── CLAUDE.md                     ← este documento
├── config/
│   ├── parametros_legales.yaml   ← límites, referencias, fecha de verificación
│   ├── cuadro_cuentas.yaml       ← mapeo de partidas a cuentas PGC
│   └── reglas_organicas.yaml     ← quórum, mayorías, umbrales estatutarios
├── apps/
│   ├── presupuesto/              ← partidas, versiones, estados
│   ├── flujo/                    ← transiciones, votaciones, ratificación
│   ├── validaciones/             ← reglas V-, L-, O-
│   ├── anexos/                   ← memoria, tesorería, campaña, comparativa
│   ├── salidas/                  ← generadores Excel y HTML
│   └── auditoria/                ← registro inmutable
├── templates/                    ← plantillas HTML del informe
├── static/                       ← estilos, tipografías, iconos
├── tests/
├── docs/
│   ├── decisiones/               ← registros de decisiones técnicas
│   └── manual_tesorero.md
└── docker-compose.yml
```

### 9.4 Reglas técnicas obligatorias

- **Dinero**: `Decimal` con precisión fija o enteros en céntimos. Prohibido `float`.
- **Configuración legal fuera del código**: ningún límite legal «a fuego» en Python.
- **Migraciones** versionadas; nunca editar a mano la base de producción.
- **Idioma**: interfaz, documentación y mensajes en **español de España**. Nombres de código en español claro o inglés, pero **coherentes** en todo el proyecto.
- **Zona horaria**: `Europe/Madrid`. Fechas almacenadas con zona.
- **Formatos**: importes como `1.234,56 €`; fechas `dd/mm/aaaa`.
- **Accesibilidad**: contraste suficiente, navegación por teclado, etiquetas en formularios.

---

## 10. Modelo de datos esencial

| Entidad | Contenido clave |
|---------|-----------------|
| `Ejercicio` | Año, estado general, parámetros aplicados. |
| `VersionPresupuesto` | Ejercicio, número de versión, estado, hash, autor, fecha, motivo. |
| `Capitulo` / `Partida` / `Linea` | Jerarquía con código, denominación, cuenta PGC, dimensión, tipo. |
| `ImporteMensual` | Línea, mes, importe (`Decimal`). |
| `Hipotesis` | Línea, texto, fuente, confianza, responsable. |
| `Anexo` | Tipo, versión de presupuesto asociada, contenido, estado. |
| `Votacion` | Versión, fecha, asistentes, quórum, votos, resultado, observaciones. |
| `Ratificacion` | Versión, fecha de Junta, resultado, referencia de acta. |
| `Comentario` | Versión, línea (opcional), autor, texto, resuelto sí/no. |
| `ParametroLegal` | Clave, valor, referencia normativa, fecha de verificación, verificador. |
| `RegistroAuditoria` | Usuario, acción, entidad, antes, después, fecha, IP. |
| `EjecucionReal` | Línea, mes, importe real, fuente de importación. |
| `Usuario` | Identidad, rol, estado, fecha de alta/baja. |

**Reglas de integridad**: las versiones `APROBADO_CP` y `RATIFICADO_JG` son de solo lectura a nivel de base de datos (restricciones o permisos), no solo en la interfaz.

---

## 11. Salidas: Excel e informe HTML

> 🚫 **Formatos no permitidos:** este sistema **no genera PDF ni Word (.docx)** salvo petición expresa de la organización. Si alguien necesita otro formato, debe solicitarlo de forma explícita.

### 11.1 📗 Libro Excel (.xlsx)

Un único libro por versión, con **fórmulas vivas** (no solo valores), para que el Tesorero pueda auditarlas.

| Pestaña | Contenido |
|---------|-----------|
| `Portada` | Partido, ejercicio, versión, estado, fecha, hash, firma de aprobaciones. |
| `Resumen` | Totales de ingresos y gastos, resultado y gráficos. |
| `Ingresos` | Detalle por capítulo y línea con distribución mensual. |
| `Gastos` | Íd. para gastos. |
| `Tesorería` | Plan mensual y escenarios. |
| `Campaña` | Presupuesto de campaña (si aplica). |
| `Comparativa` | Ejercicio anterior y ejecución real. |
| `Hipótesis` | Texto de hipótesis por línea. |
| `Cuentas PGC` | Mapeo de partidas a cuentas. |
| `Control` | Resultado de las validaciones y versiones. |

**Estilo del Excel**: cabeceras con color corporativo, celdas de entrada diferenciadas de celdas calculadas, filas de total resaltadas, congelación de paneles, formato de moneda español, impresión configurada en apaisado y ajustada a página.

### 11.2 🌐 Informe HTML visual

Documento **autónomo** (un solo archivo con estilos y gráficos incrustados) pensado para presentarse ante la Comisión Permanente y la Junta General.

**Secciones**

1. Portada con identidad del partido, ejercicio y estado.
2. Resumen ejecutivo con cifras clave destacadas.
3. Gráficos: composición de ingresos, composición de gastos, evolución mensual, saldo de tesorería.
4. Detalle por capítulo, plegable.
5. Memoria explicativa.
6. Anexos (tesorería, campaña, comparativa).
7. Cumplimiento normativo y validaciones superadas.
8. Historial de versiones y aprobaciones.

Debe verse bien en pantalla y proyector, y **imprimirse con limpieza desde el navegador** mediante estilos de impresión.

---

## 12. Diseño visual

**Dirección estética: sobrio institucional.** Serio, limpio y elegante; que transmita rigor y confianza ante una Junta.

| Elemento | Criterio |
|----------|----------|
| **Paleta** | Base neutra clara; un color de marca profundo (azul marino o similar) para cabeceras y acentos; un acento cálido discreto para destacados. Semáforo reservado a estados y alertas. *La paleta definitiva se adaptará a la identidad gráfica de Iniciativa Complutense cuando se facilite.* |
| **Tipografía** | Serif cuidada para títulos y cifras destacadas; sans legible para el cuerpo. Cifras con **números tabulares** para alinear importes. |
| **Espaciado** | Márgenes generosos, jerarquía clara, rejilla consistente. |
| **Gráficos** | Pocos, claros, con etiquetas directas; nunca decorativos. |
| **Tablas** | Filas con cebra suave, totales en negrita, importes alineados a la derecha. |
| **Iconografía** | Mínima y coherente. |
| **Estados** | Etiquetas con color y texto (no solo color) para accesibilidad. |
| **Tono de los textos** | Claro, preciso y sin jerga innecesaria. |

> Claude Code debe consultar la skill `frontend-design` al construir la interfaz y el informe, evitando resultados genéricos.

---

## 13. Auditoría, trazabilidad y seguridad

### 13.1 Auditoría

- **Registro inmutable** de toda acción: creación, edición, comentario, propuesta, voto, ratificación, anulación, importación, exportación.
- Cada versión sellada incluye **hash** de su contenido para detectar manipulación.
- Los archivos generados (Excel y HTML) incorporan en su portada el **hash y el estado** de la versión de origen.
- Consulta del histórico: filtros por usuario, fecha, entidad y acción.

### 13.2 Seguridad

- Contraseñas con algoritmo moderno; **doble factor** recomendado para el Tesorero.
- Sesiones con caducidad. Registro de accesos.
- **Copias de seguridad** automáticas y cifradas, con prueba periódica de restauración.
- Acceso mínimo necesario por rol.
- Sin secretos en el repositorio; variables de entorno.

### 13.3 Protección de datos

- Principio de **minimización**: el sistema trabaja con cifras agregadas; los datos personales de afiliados o donantes se evitan salvo necesidad estricta.
- Si se almacenan donantes (para comprobar límites), solo los datos imprescindibles, con base jurídica y plazo de conservación definidos.
- Registro de tratamientos y atención a derechos (acceso, rectificación, supresión) según RGPD.

---

## 14. Calendario anual

> Calendario orientativo. Las fechas concretas se fijan cada año en el sistema.

| Cuándo | Hito | Responsable |
|--------|------|-------------|
| **Septiembre** | Cierre provisional del ejercicio en curso y revisión de la ejecución. | Tesorero |
| **Septiembre – octubre** | Elaboración del borrador del presupuesto del año siguiente; reuniones de trabajo con la Comisión Permanente. | Tesorero + CP |
| **Octubre** | Verificación de parámetros legales del nuevo ejercicio. Memoria explicativa. | Tesorero |
| **Antes de la Junta** | **Aprobación por la Comisión Permanente.** Convocatoria de la Junta con el presupuesto a disposición de los miembros. | CP |
| **Noviembre** | **Junta General ordinaria: ratificación.** Registro del acuerdo y del acta. | Junta General |
| **Diciembre** | Publicación interna de la versión ratificada y carga en el sistema para el seguimiento. | Tesorero |
| **1 de enero** | Presupuesto vigente (o prorrogado si no hubo ratificación). | — |
| **Durante el ejercicio** | Seguimiento trimestral; modificaciones si procede. | Tesorero + CP |
| **Tras el cierre** | Cuentas anuales y rendición conforme a la normativa. | Tesorero |

El sistema envía **avisos internos** de plazo y muestra una **cuenta atrás** hasta la fecha de la Junta.

---

## 15. Normas de trabajo para Claude Code

### 15.1 Antes de escribir código

1. **Leer este documento entero** y respetarlo como fuente de verdad.
2. Si algo es ambiguo o choca con la normativa, **preguntar al usuario**, no suponer.
3. Para tareas grandes, proponer un **plan por fases** y esperar conformidad.
4. Confirmar que cada requisito nuevo cabe en el alcance (§1 y §16).

### 15.2 Cómo construir

- **Fases recomendadas**:
  1. Cimientos: proyecto, base de datos, usuarios y roles.
  2. Modelo presupuestario y cuadro de cuentas.
  3. Motor de validaciones (V, L, O) con pruebas.
  4. Flujo de estados, votación y ratificación.
  5. Anexos (memoria, tesorería, campaña, comparativa).
  6. Generadores de **Excel** y de **informe HTML**.
  7. Pulido visual, accesibilidad y manual de usuario.
  8. Endurecimiento: seguridad, copias, auditoría.
- **Pruebas primero** en las reglas de negocio: cada regla `V-`, `L-` y `O-` tiene al menos una prueba que la cubre y otra que la rompe.
- Cada cambio relevante se acompaña de **actualización de documentación**.
- **Commits** pequeños, con mensajes claros en español.

### 15.3 Qué NO debe hacer Claude Code

- ❌ Generar **PDF o Word** salvo petición expresa del usuario.
- ❌ Introducir **límites legales a fuego** en el código.
- ❌ Usar `float` para importes.
- ❌ Permitir edición de versiones aprobadas o ratificadas.
- ❌ Borrar registros de auditoría.
- ❌ Afirmar que una norma «está vigente» sin referencia verificada.
- ❌ Dar **asesoramiento jurídico o fiscal**: el sistema ayuda a cumplir, no sustituye a un asesor.
- ❌ Enviar datos a servicios externos sin autorización expresa.
- ❌ Añadir dependencias pesadas sin justificación.

### 15.4 Al terminar cada tarea

Informar de forma breve: qué se ha hecho, qué pruebas lo avalan, qué queda pendiente y qué decisión necesita del usuario.

### 15.5 Definición de «hecho»

Una funcionalidad está terminada cuando: cumple lo descrito aquí, tiene pruebas que pasan, está documentada, respeta el diseño (§12), y no rompe validaciones ni auditoría.

---

## 16. Fuera de alcance y decisiones abiertas

### 16.1 Fuera de alcance (versión 1.0)

- Contabilidad general, asientos y libro diario.
- Ejecución de pagos y conciliación bancaria.
- Gestión de la base de afiliados y cobro de cuotas.
- Presentación telemática ante el Tribunal de Cuentas.
- Firma electrónica cualificada de actas.

### 16.2 Decisiones abiertas

Pendientes de que la organización las confirme; hasta entonces Claude Code usará la opción indicada.

| Tema | Opción provisional | A confirmar con |
|------|--------------------|-----------------|
| Quórum y mayoría de la CP | Leer de `reglas_organicas.yaml`; sin valor por defecto, **bloquea** hasta que se rellene | Estatutos / Secretaría |
| Umbral de modificación que exige Junta | Parámetro configurable, vacío por defecto | Estatutos / Tesorero |
| Cuadro de cuentas definitivo | Mapeo orientativo del §3.3 | Tesorero / asesor contable |
| Identidad gráfica (logo, colores, tipografía) | Paleta sobria neutra | Comunicación |
| Alojamiento (servidor propio o nube) | Docker Compose, a decidir | Tesorero / responsable TIC |
| Mecanismo de acceso de la Junta General | Consulta por enlace seguro o por sesión | Secretaría |
| Ejercicio fiscal | Año natural | Tesorero |
| Hay proceso electoral en el ejercicio | Anexo 7.3 se activa por opción | CP |

---

## 17. Glosario

| Término | Significado |
|---------|-------------|
| **CP** | Comisión Permanente. |
| **JG** | Junta General. |
| **PGC** | Plan General de Contabilidad. |
| **Partida / línea** | Unidad presupuestaria con importe, cuenta y responsable. |
| **Versión sellada** | Copia inmutable del presupuesto con hash, creada en cada transición de estado. |
| **Modificación presupuestaria** | Cambio formal sobre un presupuesto ya ratificado. |
| **Prórroga** | Presupuesto del ejercicio anterior aplicado de forma provisional. |
| **Bloqueante** | Validación que impide avanzar de estado. |
| **Hash** | Huella digital del contenido, para detectar alteraciones. |

---

<div align="center">

**Iniciativa Complutense**
*Presupuesto claro, decisiones compartidas, cuentas ordenadas.*

`Fin del documento de gobierno · v1.0`

</div>
