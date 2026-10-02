#!/usr/bin/env python3
"""Resuelve las entradas de un workflow y las escribe en $GITHUB_OUTPUT.

Los workflows se lanzan normalmente con workflow_dispatch (actions_run_trigger desde la nube de
Claude). Como workflow_dispatch solo está disponible cuando el workflow está en la rama por
defecto, también se pueden lanzar con un push que modifique lanzamiento/<workflow>.json en la
rama de trabajo: este script lee entonces las entradas de ese archivo. Los valores por defecto
son los mismos en los dos casos.

    python3 scripts/entradas.py render      (en un paso con EVENTO e INPUTS_JSON en el entorno)
"""
import json
import os
import sys

DEFECTOS = {
    "benchmark": {"frames": "", "tipo": "video", "fotos": "", "solo_transporte": "false", "variantes": "[]"},
    "render": {"modo": "full", "parte": "1", "runs_previos": "", "frames_por_trozo": "", "rehacer_frames": "",
               "conservar_transporte": "false"},
    "entrega": {"run_montaje": "", "qc_aprobado": "false", "qc_resumen": "", "servicio": "temp.sh",
                "solo_limpieza": "false"},
}
VALORES = {
    ("benchmark", "tipo"): {"video", "fotos", "ambos"},
    ("render", "modo"): {"full", "resume", "assemble", "fotos", "parche"},
    ("entrega", "servicio"): {"temp.sh", "litterbox"},
}


def main():
    wf = sys.argv[1]
    entradas = dict(DEFECTOS[wf])
    if os.environ.get("EVENTO") == "workflow_dispatch":
        datos = json.loads(os.environ.get("INPUTS_JSON") or "{}") or {}
    else:
        ruta = os.path.join("lanzamiento", wf + ".json")
        with open(ruta, encoding="utf-8") as f:
            datos = {k: v for k, v in json.load(f).items() if not k.startswith("_")}
    desconocidas = set(datos) - set(entradas)
    if desconocidas:
        raise SystemExit(f"::error::Entradas desconocidas para {wf}: {sorted(desconocidas)}")
    for k, v in datos.items():
        if isinstance(v, bool):
            v = "true" if v else "false"
        elif isinstance(v, (list, dict)):
            v = json.dumps(v, ensure_ascii=False)
        entradas[k] = "" if v is None else str(v)
    for (w, k), permitidos in VALORES.items():
        if w == wf and entradas[k] not in permitidos:
            raise SystemExit(f"::error::{k}={entradas[k]!r} no es válido ({sorted(permitidos)})")
    salida = os.environ.get("GITHUB_OUTPUT")
    with open(salida, "a", encoding="utf-8") if salida else sys.stdout as f:
        for k, v in entradas.items():
            if "\n" in v:
                f.write(f"{k}<<FIN_ENTRADA\n{v}\nFIN_ENTRADA\n")
            else:
                f.write(f"{k}={v}\n")
    print(json.dumps(entradas, ensure_ascii=False))


if __name__ == "__main__":
    main()
