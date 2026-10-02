# CLAUDE.md — Proyecto AX620 (render distribuido en GitHub Actions)

Repositorio **público** que renderiza los vídeos y fotos de presentación del avión comercial
**AX620** (Blender 5.2, modelado 100 % procedural por fases) usando runners estándar gratuitos
de GitHub Actions. Los frames se reparten en **trozos** que se renderizan en paralelo
(un trabajo de matriz por trozo) y se montan al final en un único MP4.

> 🟥 **Regla de oro:** antes de tocar workflows, scripts o configuración de render, lee
> [`docs/ESTRATEGIA_RENDER.md`](docs/ESTRATEGIA_RENDER.md). Es la especificación. Si algo de
> este archivo parece contradecirla, manda el documento maestro y hay que corregir este.

## Estado

- Documentación y plantilla de configuración: **hechas**.
- Workflows y scripts: **pendientes de implementar** siguiendo el documento maestro.

## Reglas obligatorias

- 🌐 El repositorio es **público**: todo lo que entra en él (código, Releases, artefactos, logs) es visible para cualquiera.
- 🔑 **Nada de secretos.** Solo se usa el `GITHUB_TOKEN` automático con permisos mínimos (`contents: write` solo en el trabajo que publica la Release; `actions: read` para leer artefactos de otras ejecuciones). Ni tokens personales, ni claves, ni datos personales en código, logs o artefactos.
- 🖥️ **Solo runners estándar** (`runs-on: ubuntu-latest`). ⛔ Nunca *larger runners* de pago, ni macOS, ni GPU.
- ⏱️ El paso de render de cada trabajo lleva `timeout-minutes: 330` (**≤ 5 h 30 min**). Cada trozo se planifica para **4 h 30 min (16.200 s)** de render útil.
- 🧾 **Un único** `scripts/render_chunk.py` y **un único** `render_config.json` (en la raíz) compartidos por todos los trabajos. Nada de ajustes por trozo ni scripts alternativos.
- 🔒 ⛔ **Prohibido** cambiar la versión de Blender o cualquier ajuste que altere píxeles (sección `huella_render` del documento maestro) **a mitad de un vídeo**. Si hay que cambiarlo, se empieza el vídeo de cero con un benchmark nuevo. `troceo.frames_por_trozo` **sí** puede cambiar entre ejecuciones (p. ej. −20 % en un *resume*).
- 📦 ⛔ **Nunca** subas archivos `.blend` al repositorio ni a Git LFS. El `.blend` se publica como asset de una **Release** y se referencia por **URL + SHA-256** en `render_config.json`. Un asset publicado no se reemplaza: versión nueva → Release nueva.
- 🧪 **Benchmark obligatorio** antes de cada vídeo y cada vez que cambie la huella de render. Nunca inventes tiempos por frame.
- 🚫 `fail-fast: false` y `max-parallel: 20` en la matriz de render. No crear repositorios extra para ganar concurrencia (el límite de 20 es por cuenta).
- 🧹 Uso razonable: un vídeo a la vez, cancelar ejecuciones que se sepan inútiles, PNG con retención corta (`retention-days: 7`).

## Mapa de archivos (nombres exactos)

| Archivo | Función |
|---|---|
| `render_config.json` | Configuración única del vídeo en curso (se crea copiando `render_config.example.json`). |
| `render_config.example.json` | Plantilla documentada. Campos que empiezan por `_` = comentarios, se ignoran. |
| `.github/workflows/benchmark.yml` | Renderiza 3–5 frames representativos (uno por trabajo) y mide s/frame. |
| `.github/workflows/render.yml` | Trabajos `plan` → `render` (matriz) → `assemble`. Modos `full`, `resume`, `assemble`, `fotos`. |
| `scripts/render_chunk.py` | Se ejecuta dentro de Blender. Aplica la config, renderiza los frames del trozo, salta los existentes, valida cada PNG y escribe el manifiesto. |
| `scripts/plan_chunks.py` | Calcula `frames_por_trozo`, genera la matriz (o solo los frames que faltan en `resume`). |
| `scripts/assemble.sh` | Ordena y concatena segmentos, codificación final, validación con `ffprobe`. |
| `docs/ESTRATEGIA_RENDER.md` | Documento maestro (especificación). |

## Flujo en 6 pasos

1. **Benchmark** — publica el `.blend` en una Release, rellena `render_config.json` y lanza:
   `gh workflow run benchmark.yml -f frames=1,1350,2700`
2. **Planificar** — con el `s_por_frame_max` medido:
   `frames_por_trozo = floor(16200 / (s_por_frame_max × 1.15))`
   (`python scripts/plan_chunks.py --config render_config.json --benchmark benchmark.json`). Commit del valor en `render_config.json`.
3. **Lanzar** — `gh workflow run render.yml -f modo=full`
4. **Vigilar** — `gh run watch <run_id>` y el resumen de cada trabajo (frames hechos, s/frame real).
5. **Reanudar** — si algún trozo no terminó: *Re-run failed jobs* (misma ejecución) o
   `gh workflow run render.yml -f modo=resume -f runs_previos=<run_id>[,<run_id>…]`.
6. **Montar** — automático al final de la ejecución si la cobertura de frames es completa; si no,
   `gh workflow run render.yml -f modo=assemble -f runs_previos=<ids>`. El MP4 validado se publica en la Release `video-<fase>-v<n>`.

## Convenciones

- Idioma: castellano de España en documentación, mensajes de commit y logs de cara al usuario.
- Frames: `frame_000123.png` (6 dígitos, PNG RGB 16 bits). Trozos: índice desde 0, nombre `c000`.
- Artefactos: `frames-c007-a1`, `manifest-c007-a1`, `segmento-c007-a1` (`a` = `github.run_attempt`).
- Releases: `blend-<fase>-v<n>`, `video-<fase>-v<n>`, `fotos-<fase>-v<n>`. Nombres de archivo ASCII sin espacios.
- Al tocar números (límites, fórmulas, ejemplos), comprueba que la aritmética cuadra y que coincide con el documento maestro.
