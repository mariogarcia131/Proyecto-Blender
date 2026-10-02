"""Render de un trozo de vídeo o de un lote de fotos dentro de Blender (headless).

Especificación: docs/ESTRATEGIA_RENDER.md, secciones d), g), h), i), k) y o).

  blender -b escena.blend --factory-startup -noaudio -t 4 -P scripts/render_chunk.py -- \
    --config render_config.json --trozo c007 --rangos 323-368 \
    --salida "$RUNNER_TEMP/frames" --manifiesto "$RUNNER_TEMP/manifest-c007.json" \
    [--fotos id1,id2] [--previos DIR] [--benchmark [--ajustes JSON]]

- Impone los ajustes de §g desde render_config.json (no se fía del .blend).
- Comprueba la versión de Blender y el SHA-256 del .blend contra la configuración.
- Recorre los frames él mismo: salta los que ya existen y validan (re-run), escribe cada PNG
  en un temporal, lo valida (cabecera, resolución, 16 bits, no negro) y lo renombra.
- Reescribe el manifiesto de forma atómica tras cada frame.
- Parada suave (§h): no empieza un frame si no cabe antes de troceo.parada_suave_s.
Salida: 0 si «completo» o «parcial» por parada suave; 1 si hay frames fallidos; 2 si la
configuración no cuadra con el .blend o con la versión de Blender.
"""
import argparse
import datetime
import hashlib
import json
import os
import struct
import sys
import time

import bpy

T_SCRIPT = time.time()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import plan_chunks as pc  # noqa: E402

FIRMA_PNG = b"\x89PNG\r\n\x1a\n"


def ahora():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg):
    print(f"[render_chunk {time.time() - T_SCRIPT:8.1f}s] {msg}", flush=True)


def argumentos():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(prog="render_chunk.py")
    ap.add_argument("--config", required=True)
    ap.add_argument("--trozo", required=True)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--rangos", help="frames del trozo, p. ej. 323-368[,400-410]")
    g.add_argument("--fotos", help="ids de fotos separados por comas")
    ap.add_argument("--salida", required=True)
    ap.add_argument("--manifiesto", required=True)
    ap.add_argument("--previos", help="manifiestos de intentos anteriores (los PNG ya están en --salida)")
    ap.add_argument("--benchmark", action="store_true")
    ap.add_argument("--ajustes", help="solo con --benchmark: JSON fusionado sobre la config")
    return ap.parse_args(argv)


def sha256_archivo(ruta):
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def escribir_atomico(ruta, datos):
    tmp = ruta + ".tmp"
    os.makedirs(os.path.dirname(os.path.abspath(ruta)), exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, ruta)


def modelo_cpu():
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as f:
            for linea in f:
                if linea.startswith("model name"):
                    return linea.split(":", 1)[1].strip()
    except OSError:
        pass
    return None


def cabecera_png(ruta):
    with open(ruta, "rb") as f:
        if f.read(8) != FIRMA_PNG:
            raise ValueError("firma PNG incorrecta")
        _, tipo = struct.unpack(">I4s", f.read(8))
        if tipo != b"IHDR":
            raise ValueError("falta IHDR")
        ancho, alto, bits, color = struct.unpack(">IIBB", f.read(10))
    return ancho, alto, bits, color


def luminancia_media(ruta):
    """Luminancia media (0–1) de los valores guardados en el PNG, sin conversión de color."""
    import numpy as np
    img = bpy.data.images.load(ruta, check_existing=False)
    try:
        img.colorspace_settings.name = "Non-Color"
        n = img.size[0] * img.size[1] * img.channels
        buf = np.empty(n, dtype=np.float32)
        img.pixels.foreach_get(buf)
        px = buf.reshape(-1, img.channels)[:, :3]
        return float((px @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)).mean())
    finally:
        bpy.data.images.remove(img)


# --------------------------------------------------------------------------- ajustes de §g

def aplicar_ajustes(escena, cfg, camara, ancho, alto, porcentaje, muestras):
    cy, col, sal = cfg["cycles"], cfg["color"], cfg["salida"]
    r = escena.render
    r.engine = "CYCLES"
    c = escena.cycles
    c.device = cy["dispositivo"]
    if hasattr(c, "denoising_use_gpu"):
        c.denoising_use_gpu = False
    r.threads_mode = "FIXED"
    r.threads = int(cy["hilos"])
    c.samples = int(muestras)
    c.use_adaptive_sampling = bool(cy["muestreo_adaptativo"])
    c.adaptive_threshold = float(cy["umbral_adaptativo"])
    c.adaptive_min_samples = int(cy["muestras_min"])
    c.use_denoising = bool(cy["denoise"])
    if cy["denoise"]:
        c.denoiser = cy["denoiser"]
    r.use_persistent_data = bool(cy["persistent_data"])
    c.seed = int(cy["semilla"])
    c.use_animated_seed = bool(cy["semilla_animada"])

    escena.display_settings.display_device = col["dispositivo_display"]
    escena.view_settings.view_transform = col["view_transform"]
    escena.view_settings.look = col["look"]
    escena.view_settings.exposure = float(col["exposicion"])
    escena.view_settings.gamma = float(col["gamma"])

    r.resolution_x, r.resolution_y, r.resolution_percentage = int(ancho), int(alto), int(porcentaje)
    r.use_border = False
    r.fps, r.fps_base = int(cfg["fps"]), 1.0

    cam = bpy.data.objects.get(camara)
    if cam is None or cam.type != "CAMERA":
        raise SystemExit(f"ERROR: la cámara '{camara}' no existe en el .blend o no es una cámara.")
    escena.camera = cam

    im = r.image_settings
    if hasattr(im, "media_type"):
        im.media_type = "IMAGE"
    im.file_format = sal["formato"]
    im.color_mode = sal["modo_color"]
    im.color_depth = str(sal["profundidad_bits"])
    im.compression = int(sal["compresion_png"])
    if hasattr(im, "color_management"):
        im.color_management = "FOLLOW_SCENE"
    r.use_file_extension = True
    return {
        "motor": r.engine, "dispositivo": c.device, "hilos": r.threads, "muestras": c.samples,
        "adaptativo": c.use_adaptive_sampling, "umbral": round(c.adaptive_threshold, 6),
        "denoise": c.use_denoising, "denoiser": c.denoiser, "persistent_data": r.use_persistent_data,
        "semilla": c.seed, "semilla_animada": c.use_animated_seed,
        "color": [escena.display_settings.display_device, escena.view_settings.view_transform,
                  escena.view_settings.look, escena.view_settings.exposure, escena.view_settings.gamma],
        "resolucion": [r.resolution_x, r.resolution_y, r.resolution_percentage], "fps": r.fps,
        "camara": cam.name, "salida": [im.file_format, im.color_mode, im.color_depth, im.compression],
    }


# --------------------------------------------------------------------------- render y validación

def renderizar(escena, ruta_final, ancho, alto, bits, umbral_negro):
    """Renderiza a <final>.tmp.png, valida y renombra. Devuelve (t_render_s, error | None)."""
    tmp = ruta_final[:-4] + ".tmp.png"
    if os.path.exists(tmp):
        os.remove(tmp)
    escena.render.filepath = tmp
    t = time.time()
    try:
        bpy.ops.render.render(write_still=True, scene=escena.name)
    except Exception as e:  # noqa: BLE001
        return time.time() - t, f"excepción de render: {e}"
    dt = time.time() - t
    try:
        if not os.path.exists(tmp) or os.path.getsize(tmp) == 0:
            return dt, "no se escribió el PNG"
        w, h, b, color = cabecera_png(tmp)
        if (w, h) != (ancho, alto):
            return dt, f"resolución {w}x{h}, se esperaba {ancho}x{alto}"
        if b != bits or color != 2:
            return dt, f"PNG de {b} bits y tipo de color {color}, se esperaba RGB de {bits} bits"
        lum = luminancia_media(tmp)
        if lum < umbral_negro:
            return dt, f"frame negro (luminancia media {lum:.5f})"
    except Exception as e:  # noqa: BLE001
        return dt, f"PNG no válido: {e}"
    os.replace(tmp, ruta_final)
    return dt, None


def previos_validos(directorio, huella, clave):
    """{frame|id: sha256} de manifiestos anteriores con la misma huella."""
    out = {}
    for ruta in pc.buscar(directorio, r"^manifest-.*\.json$"):
        try:
            m = pc.leer_json(ruta)
        except (OSError, ValueError):
            continue
        if m.get("huella_render") != huella:
            continue
        for f in m.get("frames_completados" if clave == "frame" else "fotos_completadas", []):
            out[f[clave]] = f["sha256"]
    return out


def main():
    a = argumentos()
    if a.ajustes and not a.benchmark:
        raise SystemExit("ERROR: --ajustes solo se admite con --benchmark.")
    try:
        cfg = pc.cargar_config(a.config, a.ajustes)
    except pc.ErrorPlan as e:
        log(f"ERROR: {e}")
        return 2
    huella = pc.huella_render(cfg)

    esperada = tuple(int(x) for x in cfg["blender"]["version"].split("."))
    if tuple(bpy.app.version) != esperada:
        log(f"ERROR: Blender {bpy.app.version_string}, la configuración exige {cfg['blender']['version']}.")
        return 2
    sha_blend = sha256_archivo(bpy.data.filepath)
    if sha_blend != cfg["blend"]["sha256"]:
        log(f"ERROR: SHA-256 del .blend {sha_blend} ≠ blend.sha256 de la configuración.")
        return 2
    escena = bpy.data.scenes.get(cfg["escena"])
    if escena is None:
        log(f"ERROR: la escena '{cfg['escena']}' no existe.")
        return 2

    inicio_paso = float(os.environ.get("RENDER_PASO_INICIO", T_SCRIPT))
    troceo = cfg["troceo"]
    parada = float(troceo["parada_suave_s"])
    factor = float(troceo["factor_seguridad"])
    umbral_negro = float(cfg["qc"]["luminancia_negro"])
    bits = int(cfg["salida"]["profundidad_bits"])
    os.makedirs(a.salida, exist_ok=True)

    es_fotos = a.fotos is not None
    m = {
        "version_manifiesto": 1,
        "trozo": a.trozo,
        "tipo": "fotos" if es_fotos else "video",
        "benchmark": a.benchmark,
        "run_id": int(os.environ["GITHUB_RUN_ID"]) if os.environ.get("GITHUB_RUN_ID") else None,
        "intento": int(os.environ.get("GITHUB_RUN_ATTEMPT", "1")),
        "commit": os.environ.get("GITHUB_SHA"),
        "huella_render": huella,
        "blender": bpy.app.version_string,
        "blend_sha256": sha_blend,
        "cpu": modelo_cpu(),
        "t_carga_s": round(T_SCRIPT - inicio_paso, 1),
        "estado": "en_curso",
        "inicio": ahora(),
        "fin": None,
    }
    if es_fotos:
        ids = [x for x in a.fotos.split(",") if x]
        por_id = {f["id"]: f for f in cfg.get("fotos") or []}
        faltan = [x for x in ids if x not in por_id]
        if faltan:
            log(f"ERROR: fotos desconocidas en render_config.json: {faltan}")
            return 2
        m.update(fotos_planificadas=ids, fotos_completadas=[], fotos_fallidas=[])
        s_max = troceo.get("s_por_foto_max_benchmark")
        previos = previos_validos(a.previos, huella, "id")
        trabajos = [(x, os.path.join(a.salida, x + ".png")) for x in ids]
    else:
        rangos = pc.parse_rangos(a.rangos)
        ini, fin = int(cfg["frames"]["inicio"]), int(cfg["frames"]["fin"])
        fuera = [f for f in pc.expandir(rangos) if not ini <= f <= fin]
        if fuera:
            log(f"ERROR: frames fuera de {ini}-{fin}: {pc.rangos_txt(pc.compactar(fuera))}")
            return 2
        m.update(rangos_planificados=rangos, frames_completados=[], frames_fallidos=[])
        s_max = troceo.get("s_por_frame_max_benchmark")
        previos = previos_validos(a.previos, huella, "frame")
        patron = cfg["salida"]["patron"]
        trabajos = [(f, os.path.join(a.salida, patron.format(f))) for f in pc.expandir(rangos)]
    escribir_atomico(a.manifiesto, m)

    ajustes_vistos = None
    tiempos = []
    parcial = False
    for clave, ruta in trabajos:
        etiqueta = f"foto {clave}" if es_fotos else f"frame {clave}"
        # 1) ya hecho en un intento anterior (re-run): el PNG está en --salida y su hash cuadra
        if clave in previos and os.path.exists(ruta) and sha256_archivo(ruta) == previos[clave]:
            reg = {"t_render_s": None, "bytes": os.path.getsize(ruta), "sha256": previos[clave], "reutilizado": True}
            (m["fotos_completadas"] if es_fotos else m["frames_completados"]).append(
                dict({"id" if es_fotos else "frame": clave}, **reg))
            escribir_atomico(a.manifiesto, m)
            log(f"{etiqueta}: reutilizado de un intento anterior")
            continue
        # 2) parada suave
        estimado = max([float(s_max or 0)] + tiempos) * factor
        transcurrido = time.time() - inicio_paso
        if not a.benchmark and transcurrido + estimado > parada:
            log(f"PARADA SUAVE antes de {etiqueta}: {transcurrido:.0f} s + {estimado:.0f} s > {parada:.0f} s")
            parcial = True
            break
        # 3) ajustes (por foto pueden cambiar cámara, resolución y muestras)
        if es_fotos:
            f = por_id[clave]
            ancho, alto, porc, muestras, camara, frame = f["ancho"], f["alto"], 100, f["muestras"], f["camara"], f["frame"]
        else:
            ancho, alto = cfg["resolucion"]["ancho"], cfg["resolucion"]["alto"]
            porc, muestras = cfg["resolucion"].get("porcentaje", 100), cfg["cycles"]["muestras"]
            camara, frame = cfg["camara"], clave
        ajustes = aplicar_ajustes(escena, cfg, camara, ancho, alto, porc, muestras)
        if ajustes != ajustes_vistos:
            log("ajustes impuestos: " + json.dumps(ajustes, ensure_ascii=False))
            ajustes_vistos = ajustes
            m.setdefault("ajustes", ajustes)
        escena.frame_set(int(frame))
        ancho_px, alto_px = int(ancho) * int(porc) // 100, int(alto) * int(porc) // 100
        # 4) render con un reintento si sale negro o inválido
        error = None
        for intento in (1, 2):
            dt, error = renderizar(escena, ruta, ancho_px, alto_px, bits, umbral_negro)
            if error is None:
                break
            log(f"{etiqueta}: intento {intento} fallido: {error}")
        if error:
            (m["fotos_fallidas"] if es_fotos else m["frames_fallidos"]).append(
                {"id" if es_fotos else "frame": clave, "error": error})
        else:
            tiempos.append(dt)
            reg = {"id" if es_fotos else "frame": clave, "t_render_s": round(dt, 1),
                   "bytes": os.path.getsize(ruta), "sha256": sha256_archivo(ruta)}
            (m["fotos_completadas"] if es_fotos else m["frames_completados"]).append(reg)
            log(f"{etiqueta}: {dt:.1f} s")
            if s_max and dt > float(s_max) * factor:
                aviso = f"{etiqueta} tardó {dt:.0f} s > 1,15 × benchmark ({float(s_max):.0f} s)"
                print(("::warning::" if os.environ.get("GITHUB_ACTIONS") else "AVISO: ") + aviso, flush=True)
        escribir_atomico(a.manifiesto, m)

    fallidos = m["fotos_fallidas"] if es_fotos else m["frames_fallidos"]
    m["estado"] = "fallido" if fallidos else ("parcial" if parcial else "completo")
    m["fin"] = ahora()
    if tiempos:
        m["s_por_frame_max"] = round(max(tiempos), 1)
        m["s_por_frame_medio"] = round(sum(tiempos) / len(tiempos), 1)
    escribir_atomico(a.manifiesto, m)
    log(f"estado {m['estado']}: {len(m['fotos_completadas'] if es_fotos else m['frames_completados'])} hechos, "
        f"{len(fallidos)} fallidos")
    return 1 if fallidos else 0


if __name__ == "__main__":
    codigo = main()
    sys.stdout.flush()
    sys.exit(codigo)
