# Fase 3 · Cabina y morro del AX620 (modelado procedural)

Código que convierte `Avion_Fase_2.5` en `Avion_Fase_3_Cabina.blend`. Todo es procedural
(bmesh, Geometry Nodes y materiales por nodos, **sin texturas de imagen**) y solo toca las
colecciones `CABINA`, `Morro_Exterior` y `Morro_Ventanas`, más las colecciones nuevas de
presentación (`Entorno_Presentacion`, `Camaras_Presentacion`, `Iluminacion_Cabina`). El resto del
avión no se modifica: `inventario_ax620.py` calcula su huella y `verificar.py` lo comprueba.

El `.blend` **no** se guarda aquí (ver `docs/ESTRATEGIA_RENDER.md`, sección c).

## Fases (`construir.sh [desde] [hasta]`)

| Fase | Script | Contenido |
|---|---|---|
| F01 | `fases/f01_base.py` | Lado del primer oficial con geometría real (espejo con escala positiva y rótulos legibles), Design Eye Point, corrección de `GN_CAB_Rotulos`. |
| F02 | `fases/f02_overhead.py` | Overhead delantero completo (ELEC, HYD, FUEL, AIR COND, CAB PRESS, ANTI ICE, ADIRS, EXT/INT LT, SIGNS, APU, FIRE, WIPER, RCDR/CVR, OXYGEN, CALLS, EVAC, CARGO SMOKE, VENTILATION, FLT CTL, GPWS…) y overhead trasero de breakers. |
| F03 | `fases/f03_panel.py` | Panel principal, glareshield, FCU (siete segmentos, push/pull), EFIS, tren y frenos, flood lights. |
| F04 | `fases/f04_pedestal.py` | Pedestal: MCDU/RMP/ACP 3, ECP, luces, impresora, SWITCHING, manivela de tren por gravedad. |
| F05 | `fases/f05_cabina.py` | Consolas laterales, asientos y piel de oveja, observadores, mamparo, puerta, forro y techo. |
| F06 | `fases/f06_morro.py` | Morro exterior: paneles y remaches, radomo, librea, sondas, antenas, limpiaparabrisas, rótulos. |
| F07 | `fases/f07_funcional.py` | Límites y drivers de todos los mandos a `CAB_Control`, guardas animables, pantallas. |
| F08 | `fases/f08_presentacion.py` | Mundo día/noche, plataforma, luces físicas, exposición por plano, cámara del vídeo (plano secuencia de 100 s) y una cámara por foto (`fases/fotos.json`). |

Bibliotecas: `fases/axlib.py` (utilidades de malla, nodos, drivers y `CAB_Control`) y
`fases/panel_lib.py` (paneles Airbus: pulsadores de doble leyenda, palancas, rótulos, Dzus).

## Uso

```bash
# hitos/h00_inicial.blend = Fase 2.5 de partida; Blender 5.2.2
./construir.sh            # F01 → F08, un hito .blend por fase en hitos/
AX_FPS=60 ./construir.sh 8 8   # solo F08 con otro fps (el guion está en segundos)
blender -b hitos/h08_presentacion.blend -P verificar.py
blender -b hitos/h08_presentacion.blend -P inventario_ax620.py -- --salida inventario.json
blender -b hitos/h08_presentacion.blend -P previa.py -- lista.json previas 960 540 32
```
