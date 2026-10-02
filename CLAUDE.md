# CLAUDE.md — Proyecto AX620 (render distribuido en GitHub Actions)

Repositorio **público** del avión comercial **AX620** (Blender 5.2, modelado 100 % procedural
por fases). Contiene solo código, workflows y documentación para renderizar sus vídeos y fotos
en runners estándar gratuitos de GitHub Actions. **No almacena resultados.**

> 🟥 **Regla de oro:** antes de tocar workflows, scripts o configuración de render, lee
> [`docs/ESTRATEGIA_RENDER.md`](docs/ESTRATEGIA_RENDER.md). Es la especificación. Si algo de
> este archivo parece contradecirla, manda el documento maestro y hay que corregir este.

## Reparto de roles

- 🧠 **Tú (nube de Claude):** inspección del `.blend`, modelado, cámaras, animación,
  previsualizaciones rápidas, `render_config.json`, lanzar y vigilar workflows (MCP de GitHub:
  `actions_run_trigger`, `actions_list`, `actions_get`), **control de calidad** y entrega de
  enlaces al usuario. ⛔ No hagas aquí renders finales (2 núcleos): eso es de Actions.
- ⚙️ **GitHub Actions:** exclusivamente cálculo — renderizar, codificar, montar, subir la
  entrega al servicio externo y limpiar.

## Estado

- Documentación, plantilla de configuración, workflows y scripts: **hechos** (probados de extremo a
  extremo en local con una escena sintética; ver `docs/ESTRATEGIA_RENDER.md` § r).
- `workflow_dispatch` solo existe si el workflow está en la rama por defecto: desde una rama de
  trabajo se lanza con un push que modifique `lanzamiento/<workflow>.json` (mismas entradas).

## Reglas obligatorias

- 🌐 El repositorio es **público**: código, logs, resúmenes de ejecución, artefactos y Releases (mientras existen) son visibles para cualquiera.
- 🔑 **Nada de credenciales en el repositorio.** Si un servicio las necesita, van en **GitHub Secrets** y se leen con `${{ secrets.NOMBRE }}`. Hoy no hace falta ninguna: el `GITHUB_TOKEN` automático basta, con permisos mínimos por trabajo.
- 🖥️ **Solo runners estándar** (`runs-on: ubuntu-latest`). ⛔ Nunca *larger runners* de pago, ni macOS, ni GPU.
- ⏱️ El paso de render lleva `timeout-minutes: 330` (**≤ 5 h 30 min**). Cada trozo se planifica para **4 h 30 min (16.200 s)** de render útil. Máximo **60 trozos (3 oleadas) por ejecución**; si hacen falta más, partes.
- 🧾 **Un único** `scripts/render_chunk.py` y **un único** `render_config.json` compartidos por todos los trabajos.
- 🔒 ⛔ **Prohibido** cambiar la versión de Blender o cualquier ajuste de la huella de render **a mitad de un vídeo**. Si hay que cambiarlo: vídeo nuevo con benchmark nuevo. `troceo.frames_por_trozo` **sí** puede cambiar entre ejecuciones.
- 📦 ⛔ **Nunca** `.blend` ni binarios en Git ni en LFS. El `.blend` viaja: nube de Claude → temp.sh → **Release temporal** de transporte (pública mientras existe) → runners. `render.yml` **borra la Release y su tag al terminar el render**.
- 🗑️ **Todos los artefactos con `retention-days: 1`.** Frames, segmentos y fotos intermedias se borran al terminar el montaje. Reanudar y hacer el QC en **< 24 h**.
- ✅ ⛔ **Ningún enlace se entrega sin QC aprobado:** descarga `muestra-qc`, ejecuta `scripts/qc_muestra.py`, revisa las imágenes tú mismo y solo entonces lanza `entrega.yml`.
- 📤 Entrega en **temp.sh** (4 GB/archivo, 3 días; alternativa **Litterbox**, 1 GB, 72 h): MP4 final, ZIP de fotos y `.blend` final; enlaces en `$GITHUB_STEP_SUMMARY` y en `entrega.json`.
- 🧹 **Estado final obligatorio:** 0 Releases, 0 tags, 0 artefactos, 0 cachés, 0 binarios. Lo verifica el trabajo `limpieza`.
- 🧪 **Benchmark obligatorio** antes de cada vídeo. Nunca inventes tiempos por frame.
- 🚫 `fail-fast: false` y `max-parallel: 20`. No crear repositorios extra (el límite de 20 es por cuenta). Un vídeo a la vez.

## Mapa de archivos (nombres exactos)

| Archivo | Función |
|---|---|
| `render_config.json` | Configuración única del vídeo en curso (copia de `render_config.example.json`). |
| `.github/workflows/benchmark.yml` | `transporte` (crea la Release temporal) → benchmark de 3–5 frames → `resumen`. |
| `.github/workflows/render.yml` | `plan` (+ relevo) → `render` (matriz) → `assemble`. Modos `full`, `resume`, `assemble`, `fotos`, `parche`. |
| `.github/workflows/entrega.yml` | `entrega` (sube y verifica) → `limpieza`. Solo tras QC aprobado. |
| `scripts/render_chunk.py` | Dentro de Blender: aplica la config, renderiza, salta existentes, valida y escribe el manifiesto. |
| `scripts/plan_chunks.py` | `frames_por_trozo`, partes, matriz; en `resume`, solo los frames que faltan. |
| `scripts/assemble.sh` | Maestros de parte, codificación final, `ffprobe`, ZIP de fotos, `muestra-qc`. |
| `scripts/entrega.sh` | Subida a temp.sh/Litterbox, verificación SHA-256, `entrega.json`. |
| `scripts/limpieza.sh` | Borra Releases, tags, artefactos y cachés, y verifica que no queda nada. |
| `scripts/qc_muestra.py` | Se ejecuta en la **nube de Claude**: comprobaciones automáticas del QC. |
| `scripts/entradas.py` | Resuelve las entradas de cada workflow (`workflow_dispatch` o `lanzamiento/<workflow>.json`). |
| `.github/actions/preparar-runner/action.yml` | Blender exacto (caché + SHA-256), dependencias, ffmpeg y `.blend` verificado. |
| `lanzamiento/*.json` | Solo en ramas de trabajo: un push que lo cambie lanza el workflow del mismo nombre. |

## Flujo

1. **Preparar** (nube de Claude): `.blend` con recursos empaquetados → `sha256sum` →
   `curl -F "file=@X.blend" https://temp.sh/upload` → rellenar `blend.*` en `render_config.json`.
2. **Benchmark:** `benchmark.yml` con `frames=1,1350,2700` (crea la Release de transporte).
3. **Planificar:** `frames_por_trozo = floor(16200 / (s_por_frame_max × 1.15))`; commit.
4. **Lanzar:** `render.yml` con `modo=full`. Vigilar con revisiones programadas.
5. **Reanudar** (< 24 h): *Re-run failed jobs* o `render.yml` con `modo=resume`, `runs_previos=<id>`.
6. **Montar:** automático; borra intermedios y la Release de transporte.
7. **QC** (nube de Claude, < 24 h): descargar `muestra-qc`, revisar, veredicto.
8. **Entregar:** `entrega.yml` con `run_montaje`, `qc_aprobado=true`, `qc_resumen` → enlaces + limpieza.
   Comprueba los enlaces y dáselos al usuario con su fecha de caducidad.

## Convenciones

- Idioma: castellano de España en documentación, mensajes de commit y logs de cara al usuario.
- Frames: `frame_000123.png` (6 dígitos, PNG RGB 16 bits). Trozos: `c000`; lotes de fotos: `l000`.
- Artefactos: `frames-c007-a1`, `manifest-c007-a1`, `segmento-c007-a1` (`a` = `github.run_attempt`).
- Release de transporte: `transporte-<fase>-v<n>`. Nombres de archivo ASCII sin espacios.
- Al tocar números (límites, fórmulas, ejemplos), comprueba que la aritmética cuadra y que coincide con el documento maestro.
