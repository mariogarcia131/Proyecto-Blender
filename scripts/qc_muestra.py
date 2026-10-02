#!/usr/bin/env python3
"""Comprobaciones automáticas del control de calidad (docs/ESTRATEGIA_RENDER.md, sección l).

Se ejecuta en la nube de Claude sobre el artefacto muestra-qc ya descomprimido:

    python3 scripts/qc_muestra.py muestra/ --config render_config.json [--informe qc.json]

Comprueba resolución y profundidad de los PNG, frames negros o en blanco, píxeles inválidos
(fireflies aislados), fidelidad de la codificación (PSNR PNG ↔ MP4), saltos en las fronteras
entre trozos, metadatos de ffprobe, la serie de un frame cada 5 s y la presencia de todas las
fotos. Devuelve 0 si todo pasa y 1 si algo se rechaza. La revisión visual la completa Claude.
Requiere numpy y Pillow.
"""
import argparse
import glob
import json
import math
import os
import re
import struct
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import plan_chunks as pc  # noqa: E402

LUMA = np.array([0.2126, 0.7152, 0.0722])


def cabecera_png(ruta):
    with open(ruta, "rb") as f:
        d = f.read(29)
    if d[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("cabecera PNG no válida")
    w, h = struct.unpack(">II", d[16:24])
    return w, h, d[24], d[25]


def cargar(ruta):
    """Imagen RGB en float64 0–1 (PNG de 8 o 16 bits, JPG)."""
    im = Image.open(ruta)
    if ruta.lower().endswith(".png"):
        w, h, bits, _ = cabecera_png(ruta)
        if bits == 16:
            # Pillow no abre RGB de 16 bits como tal: se leen los datos crudos con numpy
            import zlib
            datos, idat = open(ruta, "rb").read(), b""
            i = 8
            while i < len(datos):
                n = struct.unpack(">I", datos[i:i + 4])[0]
                tipo = datos[i + 4:i + 8]
                if tipo == b"IDAT":
                    idat += datos[i + 8:i + 8 + n]
                i += 12 + n
            crudo = np.frombuffer(zlib.decompress(idat), dtype=np.uint8)
            canales = {2: 3, 6: 4, 0: 1, 4: 2}[cabecera_png(ruta)[3]]
            bpp = canales * 2
            fila = w * bpp
            crudo = crudo.reshape(h, fila + 1)
            img = desfiltrar(crudo, bpp)
            arr = img.view(">u2").reshape(h, w, canales).astype(np.float64) / 65535.0
            return arr[..., :3] if canales >= 3 else np.repeat(arr[..., :1], 3, axis=2)
    return np.asarray(im.convert("RGB"), dtype=np.float64) / 255.0


def desfiltrar(crudo, bpp):
    """Deshace los filtros PNG fila a fila (None, Sub, Up, Average, Paeth)."""
    h, n = crudo.shape[0], crudo.shape[1] - 1
    out = np.zeros((h, n), dtype=np.uint8)
    previa = np.zeros(n, dtype=np.int32)
    for y in range(h):
        filtro, fila = crudo[y, 0], crudo[y, 1:].astype(np.int32)
        if filtro == 0:
            rec = fila
        elif filtro == 2:
            rec = (fila + previa) & 0xFF
        else:
            rec = np.zeros(n, dtype=np.int32)
            for x in range(n):
                a = rec[x - bpp] if x >= bpp else 0
                b = previa[x]
                c = previa[x - bpp] if x >= bpp else 0
                if filtro == 1:
                    p = a
                elif filtro == 3:
                    p = (a + b) >> 1
                else:
                    pa, pb, pc_ = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                    p = a if pa <= pb and pa <= pc_ else (b if pb <= pc_ else c)
                rec[x] = (fila[x] + p) & 0xFF
        out[y] = rec
        previa = rec
    return out


def cargar_rapido(ruta):
    """Como cargar(), pero usa OpenCV si está disponible (los filtros PNG en Python son lentos)."""
    try:
        import cv2
        a = cv2.imread(ruta, cv2.IMREAD_UNCHANGED)
        if a is None:
            raise ValueError
        a = a[..., :3][..., ::-1].astype(np.float64)
        return a / (65535.0 if a.max() > 255 or a.dtype == np.uint16 else 255.0)
    except Exception:  # noqa: BLE001
        pass
    try:  # Pillow ≥ 10 abre algunos PNG de 16 bits en modo «I;16»/«RGB;16»
        im = Image.open(ruta)
        if im.mode in ("RGB", "RGBA", "L") and cabecera_png(ruta)[2] == 8:
            return np.asarray(im.convert("RGB"), dtype=np.float64) / 255.0
    except Exception:  # noqa: BLE001
        pass
    return cargar(ruta)


def luminancia(img):
    return float((img @ LUMA).mean())


def fireflies(img):
    """Fracción de píxeles saturados aislados (los 8 vecinos claramente más oscuros)."""
    y = img @ LUMA
    sat = y >= 0.995
    if not sat.any():
        return 0.0
    p = np.pad(y, 1, mode="edge")
    vecinos = sum(p[1 + dy:1 + dy + y.shape[0], 1 + dx:1 + dx + y.shape[1]]
                  for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx) / 8.0
    return float((sat & (vecinos < 0.5)).mean())


def psnr(a, b):
    mse = float(((a - b) ** 2).mean())
    return float("inf") if mse == 0 else 10 * math.log10(1.0 / mse)


def frame_de(nombre):
    m = re.search(r"frame_(\d{6})", nombre)
    return int(m.group(1)) if m else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("muestra")
    ap.add_argument("--config", required=True)
    ap.add_argument("--informe", default=None, help="ruta del informe JSON (por defecto <muestra>/qc_informe.json)")
    a = ap.parse_args()
    cfg = pc.cargar_config(a.config)
    qc = cfg["qc"]
    M = a.muestra
    ancho, alto = pc.dimensiones(cfg)
    bits = int(cfg["salida"]["profundidad_bits"])
    fps = int(cfg["fps"])
    ini, fin = int(cfg["frames"]["inicio"]), int(cfg["frames"]["fin"])
    n_frames = fin - ini + 1
    rechazos, avisos, filas = [], [], []

    def rechazar(msg):
        rechazos.append(msg)

    # 1) PNG originales de vídeo y fotos: resolución, bits, negro/blanco, fireflies
    origen = {}
    for ruta in sorted(glob.glob(os.path.join(M, "frames", "*.png"))):
        f = frame_de(os.path.basename(ruta))
        w, h, b, _ = cabecera_png(ruta)
        if (w, h) != (ancho, alto) or b != bits:
            rechazar(f"frame {f}: {w}x{h} {b} bits ≠ {ancho}x{alto} {bits} bits")
        img = cargar_rapido(ruta)
        origen[f] = img
        lum, ff = luminancia(img), fireflies(img)
        filas.append({"tipo": "frame", "id": f, "luminancia": round(lum, 4), "fireflies": round(ff, 6)})
        if lum < float(qc["luminancia_negro"]) or lum > 0.998:
            rechazar(f"frame {f}: luminancia media {lum:.4f} (negro o en blanco)")
        if ff > 0.001:
            rechazar(f"frame {f}: {ff:.4%} de píxeles saturados aislados (> 0,1 %)")
    fotos_cfg = {f["id"]: f for f in cfg.get("fotos") or []}
    for ruta in sorted(glob.glob(os.path.join(M, "fotos", "*.png"))):
        fid = os.path.basename(ruta)[:-4]
        w, h, b, _ = cabecera_png(ruta)
        esp = fotos_cfg.get(fid)
        if esp is None:
            rechazar(f"foto {fid}: no está en la configuración")
        elif (w, h) != (int(esp["ancho"]), int(esp["alto"])) or b != bits:
            rechazar(f"foto {fid}: {w}x{h} {b} bits ≠ {esp['ancho']}x{esp['alto']} {bits} bits")
        if min(w, h) < 2160 or max(w, h) < 3840:
            rechazar(f"foto {fid}: {w}x{h} por debajo de 3840×2160")
        img = cargar_rapido(ruta)
        lum, ff = luminancia(img), fireflies(img)
        filas.append({"tipo": "foto", "id": fid, "luminancia": round(lum, 4), "fireflies": round(ff, 6)})
        if lum < float(qc["luminancia_negro"]) or lum > 0.998:
            rechazar(f"foto {fid}: luminancia media {lum:.4f}")
        if ff > 0.001:
            rechazar(f"foto {fid}: {ff:.4%} de píxeles saturados aislados")
    previas = {os.path.basename(x)[:-4] for x in glob.glob(os.path.join(M, "fotos_previas", "*.jpg"))}
    faltan_fotos = sorted(set(fotos_cfg) - previas)
    if faltan_fotos:
        rechazar(f"faltan fotos en la muestra: {faltan_fotos}")

    # 2) fidelidad de la codificación
    for ruta in sorted(glob.glob(os.path.join(M, "mp4", "mp4_frame_*.png"))):
        f = frame_de(os.path.basename(ruta))
        if f not in origen:
            avisos.append(f"frame {f}: sin PNG original para medir el PSNR")
            continue
        p = psnr(origen[f], cargar_rapido(ruta))
        next(x for x in filas if x["tipo"] == "frame" and x["id"] == f)["psnr_db"] = round(p, 2)
        if p < float(qc["psnr_min_db"]):
            rechazar(f"frame {f}: PSNR {p:.2f} dB < {qc['psnr_min_db']} dB")

    # 3) saltos en fronteras: tríos (e-1, e, e+1) de la muestra
    ref = {}
    for ruta in glob.glob(os.path.join(M, "mp4", "mp4_frame_*.png")):
        ref[frame_de(os.path.basename(ruta))] = ruta
    def img_de(f):
        return origen.get(f) if f in origen else (cargar_rapido(ref[f]) if f in ref else None)
    trios = [f for f in sorted(set(origen) | set(ref)) if (f - 1) in (set(origen) | set(ref))
             and (f + 1) in (set(origen) | set(ref))]
    dif_int, dif_front = [], []
    for e in trios:
        a_, b_, c_ = img_de(e - 1), img_de(e), img_de(e + 1)
        dif_int.append(float(np.abs(a_ - b_).mean()))
        dif_front.append((e, float(np.abs(b_ - c_).mean())))
    if dif_int:
        med = float(np.median(dif_int))
        for e, d in dif_front:
            if d > 3 * max(med, 1e-4):
                rechazar(f"salto en la frontera {e}|{e + 1}: diferencia {d:.4f} > 3 × mediana {med:.4f}")
    else:
        avisos.append("sin tríos de frontera en la muestra (vídeo de un solo segmento)")

    # 4) metadatos
    fp = json.load(open(os.path.join(M, "ffprobe.json")))
    s, fo = fp["streams"][0], fp["format"]
    if (s["width"], s["height"]) != (ancho, alto):
        rechazar(f"ffprobe: {s['width']}x{s['height']} ≠ {ancho}x{alto}")
    if s["r_frame_rate"] != f"{fps}/1":
        rechazar(f"ffprobe: r_frame_rate {s['r_frame_rate']} ≠ {fps}/1")
    if int(s.get("nb_read_frames", -1)) != n_frames:
        rechazar(f"ffprobe: {s.get('nb_read_frames')} frames ≠ {n_frames}")
    if abs(float(fo["duration"]) - n_frames / fps) > 1.0 / fps + 1e-6:
        rechazar(f"ffprobe: duración {fo['duration']} ≠ {n_frames / fps:.3f} s")
    if s.get("pix_fmt") != cfg["video"]["pix_fmt_final"] or s.get("profile") != "High":
        rechazar(f"ffprobe: {s.get('pix_fmt')} / {s.get('profile')} ≠ {cfg['video']['pix_fmt_final']} / High")

    # 5) un frame cada 5 s: completo y sin negros
    c5 = sorted(glob.glob(os.path.join(M, "cada5s", "*.jpg")))
    esperados = (n_frames - 1) // (5 * fps) + 1
    if len(c5) != esperados:
        rechazar(f"cada5s: {len(c5)} frames, se esperaban {esperados}")
    for ruta in c5:
        lum = luminancia(np.asarray(Image.open(ruta).convert("RGB"), dtype=np.float64) / 255.0)
        if lum < float(qc["luminancia_negro"]) or lum > 0.998:
            rechazar(f"{os.path.basename(ruta)}: luminancia {lum:.4f}")

    informe = {
        "veredicto_automatico": "APROBADO" if not rechazos else "RECHAZADO",
        "rechazos": rechazos, "avisos": avisos, "detalle": filas,
        "frames_cada5s": len(c5), "fotos_en_muestra": len(previas),
        "ffprobe": {k: s.get(k) for k in ("width", "height", "r_frame_rate", "nb_read_frames", "pix_fmt", "profile")}
                   | {"duration": fo.get("duration"), "size": fo.get("size")},
    }
    ruta_inf = a.informe or os.path.join(M, "qc_informe.json")
    with open(ruta_inf, "w", encoding="utf-8") as f:
        json.dump(informe, f, ensure_ascii=False, indent=1)
    print(f"Veredicto automático: {informe['veredicto_automatico']}")
    for r in rechazos:
        print("  ✗ " + r)
    for w_ in avisos:
        print("  · " + w_)
    psnrs = [x["psnr_db"] for x in filas if "psnr_db" in x]
    if psnrs:
        print(f"  PSNR mínimo {min(psnrs):.2f} dB en {len(psnrs)} frames")
    print(f"  {len(c5)} frames cada 5 s, {len(previas)} fotos, informe en {ruta_inf}")
    print("  Falta la revisión visual (encuadre, geometría, materiales, luz, ruido, continuidad).")
    return 0 if not rechazos else 1


if __name__ == "__main__":
    sys.exit(main())
