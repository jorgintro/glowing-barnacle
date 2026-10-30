# 0006 · Decisiones de la Fase 5 (memoria y plan de tesorería)

Fecha: 30/10/2026 · Estado: propuesta, pendiente de visto bueno del Tesorero.

1. **Configuración en el panel, no en ficheros.** El Tesorero pidió configurar desde el panel. Los
   valores viven en la base de datos (`SeccionMemoriaCfg`, `ParametrosAnexosCfg`); un juego para lo
   real y otro, ficticio, para la demostración (`es_demo`). `config/memoria.yaml` solo siembra los
   valores propuestos y nunca pisa lo editado. Es una excepción razonada a «configuración en
   `config/`»: aquí no hay normativa, solo preferencias de redacción y de tesorería.
2. **Los parámetros de tesorería no tienen valor propuesto** (saldo mínimo, descuentos de los
   escenarios): dependen de la organización y no se inventan. Sin ellos, la comprobación avisa de
   que no puede hacerse y el escenario no se calcula.
3. **Instantánea al proponer.** Se guarda una copia de los parámetros de los anexos y de los
   parámetros legales en la hoja de control (`TransicionEstado.validacion`). Una versión propuesta
   se muestra con esa copia aunque la configuración cambie después.
4. **Huella de tipo 2.** La memoria y el saldo inicial entran en la huella. Para no invalidar lo ya
   sellado se añade `version_huella` (1 = anterior, 2 = nueva); las versiones antiguas se verifican
   con su método. Los disparadores hacen inmutables `version_huella` y el saldo inicial.
5. **La memoria se guarda por secciones** (`SeccionMemoria`), no como un único `Anexo` genérico
   (§10): permite validar cada sección y mostrar qué falta. Las partes automáticas no se guardan:
   se recalculan a partir de los datos (así no pueden contradecir las cifras); la de cumplimiento
   de una versión propuesta se lee de la instantánea del momento de proponer.
6. **Reglas nuevas.** V-008 (bloqueante, memoria completa), V-009 (aviso, falta saldo inicial) y
   V-010 (aviso, tensión de tesorería en el escenario base). Anotadas en `CLAUDE.md` §8.1 como exige
   §8. El usuario eligió «aviso» para la alerta de tesorería, no bloqueo.
7. **Hipótesis del plan de tesorería.** Cobro y pago en el mes presupuestado (aprobada por el
   Tesorero). Queda abierto un «mes de cobro/pago» por línea si más adelante se necesita.
8. **Auditoría sin el texto de la memoria** (podría llevar nombres): solo clave de sección, longitud
   y huella parcial del texto.
9. **Derivadas.** La memoria copiada a un borrador nuevo queda «pendiente de revisar» y bloquea la
   propuesta hasta que se guarde de nuevo cada sección. El saldo inicial no se copia en prórrogas.
10. **Fuera de esta fase.** Presupuesto de campaña (§7.3) y comparativa con ejecución real (§7.4),
    que son la Fase 6; los generadores de Excel/HTML pasan a ser la Fase 7.
