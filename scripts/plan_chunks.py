#!/usr/bin/env python3
"""Planificador de trozos del render distribuido del AX620 y biblioteca común.

Especificación: docs/ESTRATEGIA_RENDER.md, secciones e), f), i), j), k) y «Contratos entre
componentes». Solo usa la biblioteca estándar: funciona con el Python del runner y con el de
Blender (render_chunk.py lo importa para compartir la configuración, la huella y los rangos).

Modos (--modo):
  full | resume | parche | fotos | assemble   matriz de render.yml (JSON por stdout)
  benchmark                                   matriz de benchmark.yml
  resumen                                     benchmark.json a partir de los manifiestos del benchmark
  estimar                                     fórmula de §f (con --benchmark o con la config)
  cobertura                                   segmentos (o maestros) elegidos para un montaje
  huella                                      imprime la huella de render

Códigos de salida: 0 = correcto; 2 = faltan frames (cobertura); 3 = error de plan
(fórmula = 0, huella ajena, más de 60 trabajos por parte, configuración incompleta…).
"""
import argparse
import datetime
import hashlib
import json
import math
import os
import re
import sys

CLAVES_HUELLA = ("blender", "escena", "camara", "frames", "resolucion", "fps", "cycles", "color", "salida")
BYTES_DISCO_FRAMES = 6 * 10**9   # §f: frames_por_trozo × bruto_por_frame ≤ 6 GB
HORAS_POR_OLEADA = 5             # §f: 4 h 30 min de render + ~30 min de preparación y subida


class ErrorPlan(Exception):
    pass


def avisar(msg):
    prefijo = "::warning::" if os.environ.get("GITHUB_ACTIONS") else "AVISO: "
    print(prefijo + msg, file=sys.stderr)


# --------------------------------------------------------------------------- configuración

def _sin_comentarios(x):
    if isinstance(x, dict):
        return {k: _sin_comentarios(v) for k, v in x.items() if not k.startswith("_")}
    if isinstance(x, list):
        return [_sin_comentarios(v) for v in x]
    return x


def _fusionar(base, extra):
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _fusionar(base[k], v)
        else:
            base[k] = v


def cargar_config(ruta, ajustes=None):
    """Lee render_config.json sin las claves de comentario ('_…').

    `ajustes` (JSON) se fusiona encima: solo lo usa el benchmark para medir variantes
    (otra resolución u otras muestras) sin tocar el archivo. Cambia la huella, como debe ser.
    """
    with open(ruta, encoding="utf-8") as f:
        cfg = _sin_comentarios(json.load(f))
    if ajustes:
        _fusionar(cfg, json.loads(ajustes) if isinstance(ajustes, str) else ajustes)
    pendientes = [k for k, v in _hojas(cfg) if isinstance(v, str) and "PENDIENTE" in v]
    if pendientes:
        raise ErrorPlan("render_config.json tiene campos PENDIENTE: " + ", ".join(pendientes))
    return cfg


def _hojas(x, prefijo=""):
    if isinstance(x, dict):
        for k, v in x.items():
            yield from _hojas(v, f"{prefijo}{k}.")
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from _hojas(v, f"{prefijo}{i}.")
    else:
        yield prefijo.rstrip("."), x


def huella_render(cfg):
    """SHA-256 del JSON canónico de los campos que alteran los píxeles (§g «Huella de render»)."""
    datos = {k: cfg[k] for k in CLAVES_HUELLA}
    datos["blend"] = {"sha256": cfg["blend"]["sha256"]}
    canon = json.dumps(datos, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def dimensiones(cfg, foto=None):
    if foto:
        return int(foto["ancho"]), int(foto["alto"])
    r = cfg["resolucion"]
    p = int(r.get("porcentaje", 100))
    return int(r["ancho"]) * p // 100, int(r["alto"]) * p // 100


def bytes_brutos(ancho, alto, bits=16):
    return ancho * alto * 3 * bits // 8


# --------------------------------------------------------------------------- rangos

def compactar(frames):
    out = []
    for f in sorted(set(frames)):
        if out and f == out[-1][1] + 1:
            out[-1][1] = f
        else:
            out.append([f, f])
    return out


def expandir(rangos):
    return [f for a, b in rangos for f in range(a, b + 1)]


def parse_rangos(txt):
    frames = []
    for pieza in re.split(r"[,\s]+", (txt or "").strip()):
        if not pieza:
            continue
        m = re.fullmatch(r"(\d+)(?:-(\d+))?", pieza)
        if not m:
            raise ErrorPlan(f"Rango no válido: {pieza!r} (formato: 1201-1210,1500)")
        a, b = int(m.group(1)), int(m.group(2) or m.group(1))
        if b < a:
            raise ErrorPlan(f"Rango invertido: {pieza!r}")
        frames.extend(range(a, b + 1))
    return compactar(frames)


def rangos_txt(rangos):
    return ",".join(str(a) if a == b else f"{a}-{b}" for a, b in rangos)


# --------------------------------------------------------------------------- fórmula de §f

def fpt_por_tiempo(s_max, cfg):
    t = cfg["troceo"]
    return math.floor(t["presupuesto_render_s"] / (float(s_max) * t["factor_seguridad"]) + 1e-9)


def tope_disco(cfg, foto=None):
    return BYTES_DISCO_FRAMES // bytes_brutos(*dimensiones(cfg, foto), int(cfg["salida"]["profundidad_bits"]))


def frames_por_trozo(cfg, forzado=None, benchmark=None):
    """frames_por_trozo con su origen. Prioridad: entrada > config > fórmula con el benchmark."""
    t = cfg["troceo"]
    if forzado:
        fpt, origen = int(forzado), "entrada frames_por_trozo"
    elif t.get("frames_por_trozo"):
        fpt, origen = int(t["frames_por_trozo"]), "render_config.json"
    else:
        s_max = (benchmark or {}).get("s_por_frame_max") or t.get("s_por_frame_max_benchmark")
        if not s_max:
            raise ErrorPlan("Falta el benchmark: ni troceo.frames_por_trozo ni s_por_frame_max_benchmark "
                            "en render_config.json. Ejecuta antes benchmark.yml.")
        fpt, origen = fpt_por_tiempo(s_max, cfg), f"fórmula con s_por_frame_max = {s_max} s"
    if fpt < 1:
        raise ErrorPlan("frames_por_trozo = 0: un solo frame no cabe en 16.200 s con el margen de 1,15. "
                        "Reduce muestras o resolución en la nube de Claude y repite el benchmark.")
    tope = tope_disco(cfg)
    if fpt > tope:
        avisar(f"frames_por_trozo {fpt} supera la regla de disco (≤ 6 GB de PNG por trozo): se usa {tope}.")
        fpt, origen = tope, origen + " limitado por disco"
    return fpt, origen


def fotos_por_trabajo(cfg):
    t = cfg["troceo"]
    if t.get("fotos_por_trabajo"):
        n = int(t["fotos_por_trabajo"])
    elif t.get("s_por_foto_max_benchmark"):
        n = fpt_por_tiempo(t["s_por_foto_max_benchmark"], cfg)
        if n < 1:
            raise ErrorPlan("Una foto supera 14.087 s (≈ 3 h 55 min): reduce sus muestras (§k).")
    else:
        n = 1
    fotos = cfg.get("fotos") or []
    if fotos:
        n = min(n, min(tope_disco(cfg, f) for f in fotos))
    return max(1, n)


def lotes_fotos(cfg, excluir=()):
    ids = [f["id"] for f in cfg.get("fotos") or [] if f["id"] not in set(excluir)]
    n = fotos_por_trabajo(cfg)
    return [ids[i:i + n] for i in range(0, len(ids), n)]


def particion(cfg, fpt_base):
    """Rangos de frames de cada parte (§b «Partes sucesivas»).

    Se calcula con la frames_por_trozo de la configuración, no con la de una entrada puntual,
    para que las fronteras entre partes sean estables entre ejecuciones. Los lotes de fotos van
    en la última parte y cuentan para su tope de 60 trabajos. Devuelve ([(ini, fin) | None], T, L).
    """
    ini, fin = int(cfg["frames"]["inicio"]), int(cfg["frames"]["fin"])
    maxp = int(cfg["troceo"]["trozos_max_por_parte"])
    total_t = math.ceil((fin - ini + 1) / fpt_base)
    total_l = len(lotes_fotos(cfg))
    if total_l > maxp:
        raise ErrorPlan(f"{total_l} lotes de fotos superan {maxp} trabajos: sube troceo.fotos_por_trabajo.")
    p = max(1, math.ceil((total_t + total_l) / maxp))
    if p == 1:
        return [(ini, fin)], total_t, total_l
    objetivo = math.ceil((total_t + total_l) / p)
    v_ultima = max(0, min(total_t, objetivo - total_l))
    resto = total_t - v_ultima
    reparto = [resto // (p - 1) + (1 if i < resto % (p - 1) else 0) for i in range(p - 1)] + [v_ultima]
    partes, t0 = [], 0
    for n in reparto:
        partes.append((ini + t0 * fpt_base, min(fin, ini + (t0 + n) * fpt_base - 1)) if n else None)
        t0 += n
    return partes, total_t, total_l


def estimar(cfg, benchmark=None, fpt=None):
    """Aplica la fórmula de §f a todo el vídeo. Devuelve un dict listo para el resumen."""
    bm = benchmark or {}
    t = cfg["troceo"]
    s_max = bm.get("s_por_frame_max") or t.get("s_por_frame_max_benchmark")
    s_med = bm.get("s_por_frame_medio") or t.get("s_por_frame_medio_benchmark")
    if bm.get("s_por_foto_max") and not t.get("fotos_por_trabajo"):
        t = dict(t, s_por_foto_max_benchmark=bm["s_por_foto_max"])
        cfg = dict(cfg, troceo=t)
    if fpt is None:
        # con un benchmark recién medido manda la fórmula; si no, lo que diga la config
        fpt = fpt_por_tiempo(s_max, cfg) if bm.get("s_por_frame_max") else frames_por_trozo(cfg)[0]
    if fpt < 1:
        raise ErrorPlan("frames_por_trozo = 0 con este benchmark: no se puede renderizar así.")
    fpt = min(fpt, tope_disco(cfg))
    partes, total_t, total_l = particion(cfg, fpt)
    maxpar = int(t["max_paralelo"])
    ini, fin = int(cfg["frames"]["inicio"]), int(cfg["frames"]["fin"])
    detalle = []
    for k, rango in enumerate(partes, 1):
        n_v = 0 if rango is None else math.ceil((rango[1] - rango[0] + 1) / fpt)
        n_l = total_l if k == len(partes) else 0
        detalle.append({"parte": k, "rango": rango, "trozos_video": n_v, "lotes_fotos": n_l,
                        "oleadas": math.ceil((n_v + n_l) / maxpar)})
    oleadas = sum(d["oleadas"] for d in detalle)
    frames = fin - ini + 1
    s_foto_med = bm.get("s_por_foto_medio")
    h_runner = (frames * s_med / 3600 if s_med else None)
    if h_runner is not None and s_foto_med:
        h_runner += len(cfg.get("fotos") or []) * s_foto_med / 3600
    return {
        "frames_totales": frames,
        "fps": cfg["fps"],
        "duracion_s": round(frames / cfg["fps"], 3),
        "resolucion": "%dx%d" % dimensiones(cfg),
        "muestras": cfg["cycles"]["muestras"],
        "s_por_frame_max": s_max,
        "s_por_frame_medio": s_med,
        "frames_por_trozo": fpt,
        "trozos": total_t,
        "lotes_fotos": total_l,
        "fotos_por_trabajo": fotos_por_trabajo(cfg),
        "partes": len(partes),
        "detalle_partes": detalle,
        "oleadas": oleadas,
        "horas_reales_cota": oleadas * HORAS_POR_OLEADA,
        "horas_reales_peor_caso": oleadas * 6,
        "horas_runner": round(h_runner, 1) if h_runner is not None else None,
    }


# --------------------------------------------------------------------------- lectura del relevo

def leer_json(ruta):
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def buscar(directorio, patron):
    rx = re.compile(patron)
    if not directorio or not os.path.isdir(directorio):
        return []
    out = []
    for raiz, _, archivos in os.walk(directorio):
        out.extend(os.path.join(raiz, a) for a in archivos if rx.search(a))
    return sorted(out)


def segmentos_validos(directorio, huella, avisos=None):
    """Segmentos seg_AAAAAA-BBBBBB.mp4 con su JSON hermano y la huella actual.

    Cada segmento lleva un JSON con huella, trozo, run_id e intento (lo escribe
    assemble.sh --codificar-trozo), así el plan y el montaje no dependen de que el
    manifiesto del trozo haya llegado a subirse.
    """
    validos, ajenos = [], 0
    for ruta in buscar(directorio, r"^seg_\d{6}-\d{6}\.json$"):
        d = leer_json(ruta)
        mp4 = ruta[:-5] + ".mp4"
        if not os.path.exists(mp4):
            continue
        if d.get("huella_render") != huella:
            ajenos += 1
            if avisos is not None:
                avisos.append(f"Segmento con huella distinta descartado: {ruta}")
            continue
        d.update(ruta=mp4, json=ruta, clase="segmento")
        validos.append(d)
    return validos, ajenos


def maestros_validos(directorio, huella, avisos=None):
    validos, ajenos = [], 0
    for ruta in buscar(directorio, r"^parte-\d{2}\.json$"):
        d = leer_json(ruta)
        mp4 = ruta[:-5] + ".mp4"
        if not os.path.exists(mp4):
            continue
        if d.get("huella_render") != huella:
            ajenos += 1
            if avisos is not None:
                avisos.append(f"Maestro con huella distinta descartado: {ruta}")
            continue
        d.update(ruta=mp4, json=ruta, clase="maestro")
        validos.append(d)
    # el mismo maestro puede llegar por varios relevos: uno por parte, el más reciente
    por_parte = {}
    for d in sorted(validos, key=lambda d: (d["run_id"], d.get("intento", 1))):
        por_parte[d["parte"]] = d
    return [por_parte[k] for k in sorted(por_parte)], ajenos


def fotos_hechas(directorio, huella):
    """Fotos ya renderizadas en el relevo: {id: ruta_png}. Solo manifiestos con su PNG al lado."""
    hechas = {}
    for ruta in buscar(directorio, r"^manifest-l\d{3}\.json$"):
        m = leer_json(ruta)
        if m.get("huella_render") != huella:
            continue
        for f in m.get("fotos_completadas", []):
            png = os.path.join(os.path.dirname(ruta), f["id"] + ".png")
            if os.path.exists(png) and os.path.getsize(png) == f.get("bytes"):
                hechas[f["id"]] = png
    return hechas


# --------------------------------------------------------------------------- cobertura

def elegir(candidatos, a, b):
    """Elige segmentos (o maestros) que cubren [a, b] sin solapes (§j paso 2).

    1. Se descartan los contenidos en otro candidato (todos tienen la misma huella, así que
       son intercambiables; con rango idéntico gana la ejecución más reciente y el intento más alto).
    2. El resto se acepta por prioridad (run_id, intento). Un solape parcial es un error.
    """
    cands = [c for c in candidatos if c["fin"] >= a and c["inicio"] <= b]
    for c in cands:
        if c["inicio"] < a or c["fin"] > b:
            raise ErrorPlan(f"{c['ruta']} ({c['inicio']}-{c['fin']}) se sale de la parte {a}-{b}.")
    prio = sorted(cands, key=lambda c: (-c["run_id"], -c.get("intento", 1), c["inicio"]))
    vivos, descartados = [], []
    for c in prio:
        contenedor = next((o for o in vivos if o["inicio"] <= c["inicio"] and c["fin"] <= o["fin"]), None)
        if contenedor:
            descartados.append(c)
            continue
        dentro = [o for o in vivos if c["inicio"] <= o["inicio"] and o["fin"] <= c["fin"]]
        for o in dentro:
            vivos.remove(o)
            descartados.append(o)
        vivos.append(c)
    elegidos, cubiertos = [], set()
    for c in sorted(vivos, key=lambda c: (-c["run_id"], -c.get("intento", 1), c["inicio"])):
        fr = set(range(c["inicio"], c["fin"] + 1))
        if fr & cubiertos:
            raise ErrorPlan(f"Solape parcial no resoluble: {c['ruta']} ({c['inicio']}-{c['fin']}) "
                            "con otro segmento elegido.")
        elegidos.append(c)
        cubiertos |= fr
    elegidos.sort(key=lambda c: c["inicio"])
    faltan = compactar(set(range(a, b + 1)) - cubiertos)
    return elegidos, descartados, faltan


def seleccion_muestra(cfg, elegidos, a, b):
    """Frames de la muestra de QC dentro de [a, b] (§l): primero, último, benchmark y fronteras.

    Cada frontera aporta tres frames: los dos últimos de un segmento y el primero del siguiente
    (la diferencia entre los dos primeros es la referencia para detectar saltos).
    """
    qc = cfg["qc"]
    ini, fin = int(cfg["frames"]["inicio"]), int(cfg["frames"]["fin"])
    fijos = {f for f in [ini, fin] + list(cfg.get("benchmark", {}).get("frames", [])) if a <= f <= b}
    presupuesto = max(0, int(qc["frames_muestra_max"]) - len(fijos))
    fronteras = [elegidos[i]["fin"] for i in range(len(elegidos) - 1)]
    n = min(int(qc["fronteras_max"]), presupuesto // 3, len(fronteras))
    if n and len(fronteras) > n:
        paso = len(fronteras) / n
        fronteras = [fronteras[int(i * paso + paso / 2)] for i in range(n)]
    else:
        fronteras = fronteras[:n]
    sel = set(fijos)
    for e in fronteras:
        sel |= {e - 1, e, e + 1}
    return sorted(f for f in sel if a <= f <= b), fronteras


# --------------------------------------------------------------------------- planes

def _agrupar(frames, n):
    return [compactar(frames[i:i + n]) for i in range(0, len(frames), n)]


def _rango_parte(cfg, partes, k, maestros):
    """Rango de la parte k. Desde la parte 2, empieza justo tras el último maestro relevado
    para que un cambio de frames_por_trozo entre ejecuciones no deje huecos ni solapes."""
    rango = partes[k - 1]
    if k >= 2 and maestros:
        previos = [m for m in maestros if m["parte"] < k]
        if previos:
            inicio = max(m["fin"] for m in previos) + 1
            fin = rango[1] if rango else inicio - 1
            if k == len(partes):
                fin = int(cfg["frames"]["fin"])
            rango = (inicio, fin) if inicio <= fin else None
    return rango


def plan(cfg, modo, parte=1, fpt_forzado=None, relevo=None, rehacer=None, benchmark=None):
    avisos = []
    huella = huella_render(cfg)
    fpt_base, origen = frames_por_trozo(cfg, benchmark=benchmark)
    fpt = frames_por_trozo(cfg, forzado=fpt_forzado, benchmark=benchmark)[0] if fpt_forzado else fpt_base
    partes, total_t, _ = particion(cfg, fpt_base)
    n_partes = len(partes)
    if not 1 <= parte <= n_partes and modo not in ("fotos", "parche"):
        raise ErrorPlan(f"parte={parte} fuera de rango: el vídeo tiene {n_partes} parte(s).")

    segs, ajenos_s = segmentos_validos(relevo, huella, avisos)
    maestros, ajenos_m = maestros_validos(relevo, huella, avisos)
    if (ajenos_s or ajenos_m) and not (segs or maestros):
        raise ErrorPlan("Todo lo relevado tiene una huella de render distinta de la actual: la "
                        "configuración o el .blend han cambiado. Eso es un vídeo nuevo: modo full sin runs_previos.")
    for m in avisos:
        avisar(m)

    trozos, rango, faltan = [], None, []
    ultima = parte == n_partes
    if modo in ("full", "resume", "assemble"):
        rango = _rango_parte(cfg, partes, parte, maestros)
        if rango:
            hechos = set()
            for c in segs + maestros:
                hechos.update(range(c["inicio"], c["fin"] + 1))
            faltan = [f for f in range(rango[0], rango[1] + 1) if f not in hechos]
        if modo != "assemble":
            base = sum(math.ceil(((r[1] - r[0] + 1) if r else 0) / fpt_base) for r in partes[:parte - 1]) \
                if modo == "full" else 0
            for i, rg in enumerate(_agrupar(faltan, fpt)):
                trozos.append({"tipo": "video", "indice": base + i, "nombre": "c%03d" % (base + i),
                               "rangos": rg, "rangos_txt": rangos_txt(rg), "frames": len(expandir(rg))})
            if ultima:
                ya = fotos_hechas(relevo, huella)
                for j, lote in enumerate(lotes_fotos(cfg, excluir=ya)):
                    trozos.append({"tipo": "fotos", "indice": j, "nombre": "l%03d" % j,
                                   "fotos": lote, "fotos_txt": ",".join(lote)})
    elif modo == "fotos":
        ultima = True
        ya = fotos_hechas(relevo, huella)
        for j, lote in enumerate(lotes_fotos(cfg, excluir=ya)):
            trozos.append({"tipo": "fotos", "indice": j, "nombre": "l%03d" % j,
                           "fotos": lote, "fotos_txt": ",".join(lote)})
    elif modo == "parche":
        if not rehacer:
            raise ErrorPlan("modo parche sin rehacer_frames.")
        # se rehacen los segmentos completos que contienen esos frames: así el montaje puede
        # sustituirlos cortando los maestros por fronteras de fotograma clave, sin recodificar
        fronteras = [s for m in maestros for s in m["segmentos"]]
        if not fronteras:
            raise ErrorPlan("modo parche sin maestros parte-NN relevados: pasa en runs_previos el run del montaje.")
        pedir = set(expandir(rehacer))
        afectados = [s for s in fronteras if pedir & set(range(s["inicio"], s["fin"] + 1))]
        fuera = pedir - {f for s in afectados for f in range(s["inicio"], s["fin"] + 1)}
        if fuera:
            raise ErrorPlan("Frames fuera de los maestros: " + rangos_txt(compactar(fuera)))
        actual, i = [], 0
        for s in sorted(afectados, key=lambda s: s["inicio"]):
            if actual and sum(b - a + 1 for a, b in actual) + s["fin"] - s["inicio"] + 1 > fpt:
                trozos.append(_trozo_parche(i, actual)); i += 1; actual = []
            actual.append([s["inicio"], s["fin"]])
        if actual:
            trozos.append(_trozo_parche(i, actual))
        faltan = expandir(compactar(expandir([[s["inicio"], s["fin"]] for s in afectados])))
        rango = (min(faltan), max(faltan))
        ultima = True
    else:
        raise ErrorPlan(f"Modo desconocido: {modo}")

    maxp = int(cfg["troceo"]["trozos_max_por_parte"])
    if len(trozos) > maxp:
        raise ErrorPlan(f"{len(trozos)} trabajos en esta ejecución superan el máximo de {maxp} "
                        "(3 oleadas, retención de 24 h). Sube frames_por_trozo o divide en partes.")
    oleadas = math.ceil(len(trozos) / int(cfg["troceo"]["max_paralelo"]))
    s_med = cfg["troceo"].get("s_por_frame_medio_benchmark")
    n_frames = sum(t.get("frames", 0) for t in trozos)
    return {
        "modo": modo,
        "huella_render": huella,
        "frames_por_trozo": fpt,
        "origen_frames_por_trozo": origen if not fpt_forzado else "entrada frames_por_trozo",
        "parte": parte,
        "partes": n_partes,
        "ultima": ultima,
        "rango_parte": list(rango) if rango else None,
        "frames_pendientes": len(faltan),
        "trozos": trozos,
        "num_trozos": len(trozos),
        "oleadas": oleadas,
        "horas_estimadas": oleadas * HORAS_POR_OLEADA,
        "horas_runner_estimadas": round(n_frames * s_med / 3600, 1) if s_med else None,
        "relevo": {"segmentos": len(segs), "maestros": len(maestros), "ajenos": ajenos_s + ajenos_m},
    }


def _trozo_parche(i, rangos):
    rg = compactar(expandir(rangos))
    return {"tipo": "video", "indice": i, "nombre": "c%03d" % i, "rangos": rg,
            "rangos_txt": rangos_txt(rg), "frames": len(expandir(rg))}


def plan_benchmark(cfg, frames_txt=None, tipo="video", fotos_txt=None):
    ini, fin = int(cfg["frames"]["inicio"]), int(cfg["frames"]["fin"])
    trozos = []
    if tipo in ("video", "ambos"):
        frames = expandir(parse_rangos(frames_txt)) if frames_txt else list(cfg["benchmark"]["frames"])
        fuera = [f for f in frames if not ini <= f <= fin]
        if fuera:
            raise ErrorPlan(f"Frames de benchmark fuera de {ini}-{fin}: {fuera}")
        for i, f in enumerate(frames):
            trozos.append({"tipo": "video", "indice": i, "nombre": "b%06d" % f,
                           "rangos": [[f, f]], "rangos_txt": str(f), "frames": 1})
    if tipo in ("fotos", "ambos"):
        ids_cfg = [f["id"] for f in cfg.get("fotos") or []]
        if fotos_txt:
            ids = [x for x in fotos_txt.split(",") if x]
        else:
            ids = list(cfg.get("benchmark", {}).get("fotos") or [])
            if not ids:  # por defecto, las 2 fotos con más muestras
                ids = [f["id"] for f in sorted(cfg.get("fotos") or [], key=lambda f: -f["muestras"])[:2]]
        desconocidas = [x for x in ids if x not in ids_cfg]
        if desconocidas:
            raise ErrorPlan(f"Fotos de benchmark que no están en fotos[]: {desconocidas}")
        for j, x in enumerate(ids):
            trozos.append({"tipo": "fotos", "indice": j, "nombre": "bf%02d" % j, "fotos": [x], "fotos_txt": x})
    if not trozos:
        raise ErrorPlan("Benchmark vacío.")
    return {"modo": "benchmark", "huella_render": huella_render(cfg), "trozos": trozos,
            "num_trozos": len(trozos)}


def resumen_benchmark(cfg, directorio, run_id=None, ajustes=None):
    frames, fotos = [], []
    for ruta in buscar(directorio, r"^manifest-b.*\.json$"):
        m = leer_json(ruta)
        for f in m.get("frames_completados", []):
            frames.append({"frame": f["frame"], "t_render_s": f["t_render_s"], "t_carga_s": m.get("t_carga_s"),
                           "cpu": m.get("cpu"), "trozo": m["trozo"]})
        for f in m.get("fotos_completadas", []):
            fotos.append({"id": f["id"], "t_render_s": f["t_render_s"], "t_carga_s": m.get("t_carga_s"),
                          "cpu": m.get("cpu"), "trozo": m["trozo"]})
        for f in m.get("frames_fallidos", []) + m.get("fotos_fallidas", []):
            avisar(f"Benchmark {m['trozo']}: fallo en {f}")
    if not frames and not fotos:
        raise ErrorPlan("El benchmark no produjo ninguna medición.")
    bm = {
        "fecha": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "run_id": run_id,
        "huella_render": huella_render(cfg),
        "ajustes": json.loads(ajustes) if ajustes else None,
        "frames": sorted(frames, key=lambda x: x["frame"]),
        "fotos": fotos,
    }
    if frames:
        t = [f["t_render_s"] for f in frames]
        bm["s_por_frame_max"] = round(max(t), 1)
        bm["s_por_frame_medio"] = round(sum(t) / len(t), 1)
    if fotos:
        t = [f["t_render_s"] for f in fotos]
        bm["s_por_foto_max"] = round(max(t), 1)
        bm["s_por_foto_medio"] = round(sum(t) / len(t), 1)
    if frames:
        try:
            bm["estimacion"] = estimar(cfg, bm)
        except ErrorPlan as e:
            bm["estimacion"] = {"error": str(e)}
    return bm


# --------------------------------------------------------------------------- CLI

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", required=True)
    ap.add_argument("--modo", default="full",
                    choices=["full", "resume", "parche", "fotos", "assemble", "benchmark", "resumen",
                             "estimar", "cobertura", "huella"])
    ap.add_argument("--parte", type=int, default=1)
    ap.add_argument("--frames-por-trozo", type=int, default=None)
    ap.add_argument("--manifiestos", help="directorio (recursivo) con manifiestos y artefactos relevados")
    ap.add_argument("--segmentos", help="directorio (recursivo) con segmentos y maestros; por defecto --manifiestos")
    ap.add_argument("--benchmark", help="benchmark.json")
    ap.add_argument("--rehacer", help="modo parche: frames a rehacer, p. ej. 1201-1210,1500")
    ap.add_argument("--frames", help="modo benchmark: frames, p. ej. 1,1350,2700")
    ap.add_argument("--tipo", default="video", choices=["video", "fotos", "ambos"])
    ap.add_argument("--fotos", help="modo benchmark: ids de fotos separados por comas")
    ap.add_argument("--ajustes", help="JSON fusionado sobre la config (solo benchmark de variantes)")
    ap.add_argument("--maestros", action="store_true", help="modo cobertura: elegir maestros parte-NN")
    ap.add_argument("--run-id", type=int, default=None)
    a = ap.parse_args(argv)

    try:
        cfg = cargar_config(a.config, a.ajustes)
        relevo = a.segmentos or a.manifiestos
        bm = leer_json(a.benchmark) if a.benchmark else None
        if a.modo == "huella":
            print(huella_render(cfg))
            return 0
        if a.modo == "estimar":
            out = estimar(cfg, bm, fpt=a.frames_por_trozo)
        elif a.modo == "benchmark":
            out = plan_benchmark(cfg, a.frames, a.tipo, a.fotos)
        elif a.modo == "resumen":
            out = resumen_benchmark(cfg, a.manifiestos, a.run_id, a.ajustes)
        elif a.modo == "cobertura":
            out, codigo = cobertura(cfg, relevo, a.parte, a.maestros, a.run_id, bm)
            print(json.dumps(out, ensure_ascii=False, indent=1))
            return codigo
        else:
            rehacer = parse_rangos(a.rehacer) if a.rehacer else None
            out = plan(cfg, a.modo, a.parte, a.frames_por_trozo, relevo, rehacer, bm)
    except ErrorPlan as e:
        print(("::error::" if os.environ.get("GITHUB_ACTIONS") else "ERROR: ") + str(e), file=sys.stderr)
        return 3
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


def cobertura(cfg, relevo, parte, maestros_flag, run_id, bm=None):
    """Elección para el montaje: segmentos de una parte o, con --maestros, maestros del vídeo."""
    huella = huella_render(cfg)
    avisos = []
    fpt_base = frames_por_trozo(cfg, benchmark=bm)[0]
    partes, _, _ = particion(cfg, fpt_base)
    ini, fin = int(cfg["frames"]["inicio"]), int(cfg["frames"]["fin"])
    if maestros_flag:
        cands, _ = maestros_validos(relevo, huella, avisos)
        a, b = ini, fin
    else:
        cands, _ = segmentos_validos(relevo, huella, avisos)
        maestros, _ = maestros_validos(relevo, huella)
        rango = _rango_parte(cfg, partes, parte, maestros)
        if rango is None:
            return {"parte": parte, "rango": None, "elegidos": [], "faltan": [], "muestra": []}, 0
        a, b = rango
    for m in avisos:
        avisar(m)
    elegidos, descartados, faltan = elegir(cands, a, b)
    limpio = lambda c: {k: c[k] for k in ("ruta", "json", "inicio", "fin", "run_id", "intento", "trozo", "clase")
                        if k in c}
    muestra, fronteras = seleccion_muestra(cfg, elegidos, a, b)
    out = {
        "parte": parte, "partes": len(partes), "rango": [a, b], "huella_render": huella,
        "elegidos": [limpio(c) for c in elegidos], "descartados": [limpio(c) for c in descartados],
        "faltan": faltan, "faltan_txt": rangos_txt(faltan), "muestra": muestra, "fronteras_muestra": fronteras,
    }
    if faltan:
        out["comando_resume"] = (f"gh workflow run render.yml -f modo=resume -f parte={parte} "
                                 f"-f runs_previos={run_id or '<run_id>'}")
        print(("::error::" if os.environ.get("GITHUB_ACTIONS") else "ERROR: ")
              + f"Faltan frames en la parte {parte}: {rangos_txt(faltan)}. Reanudar en < 24 h con: "
              + out["comando_resume"], file=sys.stderr)
        return out, 2
    return out, 0


if __name__ == "__main__":
    sys.exit(main())
