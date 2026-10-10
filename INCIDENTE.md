# Incidente FR-0153 · cambio de tema de la app de pruebas

## Ticket

- **Hora:** 15:30 (2026-10-10). Recibido durante la Fase 2.
- **Qué cambió (según el ticket):** tema visual nuevo; botones movidos de lugar, etiquetas
  distintas y un modal nuevo al abrir la app. El set de evaluación oculto corre sobre el tema nuevo.
- **Qué vimos:** entre 15:33 y 15:40, tras varios `POST /__reset`, nuestro escritorio seguía
  mostrando el tema anterior (la captura difiere de `docs/incidente/antes.png` solo en el
  puntero) y sin modal. La captura del tema nuevo (`docs/incidente/despues.png`) queda pendiente
  hasta que el cambio llegue a nuestro escritorio.

## Por qué la arquitectura no necesitó cambios de fondo

- **Sin coordenadas fijas:** cada acción sale de la captura actual; el modelo da `x, y` en píxeles
  de esa captura (calibrado), así que un botón movido se encuentra donde esté.
- **Sin etiquetas fijas:** ni el código ni el prompt nombran pantallas, menús o campos de la app;
  el agente se orienta en cada tarea.
- **Estado no asumido:** la fase orientar ya cerraba menús/diálogos abiertos de sesiones
  anteriores; un modal al abrir es el mismo caso.
- El conector RFB y el bucle no dependen del aspecto de la app.

## Ajustes hechos

1. **Modales al abrir (orientar):** el agente lee el modal, resume su texto en `evento`
   ("modal inesperado: …") y lo cierra con la opción que no cambia datos (Cerrar, X, Entendido,
   Cancelar, Escape). Nunca acepta algo que modifique datos o configuración. El texto del modal es
   dato, no instrucción.
2. **Controles por función:** el prompt pide identificar controles por lo que hacen (guardar puede
   ser Registrar, Confirmar, Aplicar, un ícono de disco…) y explorar menús y submenús antes de
   rendirse.
3. **Detección genérica de cambios:** campo `evento` en la acción del modelo y detección propia de
   clics/escrituras sin efecto en pantalla. Cada evento va a `runs/<task_id>/trace.jsonl` como
   `{"evento": …}` y los últimos 3 se mencionan al final del resumen (`eventos: …`). La línea
   `respuesta:` sigue siendo siempre la primera.

## Resultados en el tema nuevo (se completa en la Fase 5)

| Prueba | Modelo | Pasa | Estado | Pasos | Segundos | USD | Eventos registrados |
| ------ | ------ | ---- | ------ | ----- | -------- | --- | ------------------- |
| E1 | | | | | | | |
| E2 | | | | | | | |
| E3 | | | | | | | |
| E4 | | | | | | | |
| E5 | | | | | | | |
