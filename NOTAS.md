# Notas de avance

| Fase | Estado | Hora | Resultado | Plan B |
| ---- | ------ | ---- | --------- | ------ |
| 0 · Setup del repo | hecha | | Esqueleto, docs y `scripts/check_desktop.py` | — |
| 1 · Conexión RFB | hecha | 2026-10-10 | `demo_rfb.py` OK a 1280×800: handshake 1.2–2.0 s, primer frame 0.9–1.6 s, `wait_stable` ~0.7 s, clic 0.16 s. Ctrl+A + `type_text` verificado en un campo real: «Papelería # ñ Ñandú €» exacto y sin concatenar | Playwright + noVNC si el handshake no sale (no hizo falta) |
| 2 · Agente | pendiente | | | |
| 3 · API + worker | pendiente | | | |
| 4 · Harness | pendiente | | | |
| 5 · Despliegue | pendiente | | | |
