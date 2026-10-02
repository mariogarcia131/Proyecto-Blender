#!/usr/bin/env bash
# Entrega por servicio de descarga externo (docs/ESTRATEGIA_RENDER.md, sección m).
#
#   entrega.sh --config render_config.json --servicio temp.sh|litterbox --archivos DIR \
#     --qc-resumen "texto" [--salida entrega.json]
#
# Sube el MP4 final, el ZIP de fotos y el .blend final (3 intentos con espera creciente),
# verifica cada subida descargándola de nuevo y comparando el SHA-256, genera entrega.json, lo
# sube también y escribe la tabla de enlaces en $GITHUB_STEP_SUMMARY. Sin credenciales: temp.sh y
# Litterbox no las necesitan (si algún día un servicio las pide, van en GitHub Secrets).
set -euo pipefail

DIR_SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="" SERVICIO="" ARCHIVOS="" QC_RESUMEN="" SALIDA="entrega.json"
while [ $# -gt 0 ]; do
  case "$1" in
    --config) CONFIG="$2"; shift ;;
    --servicio) SERVICIO="$2"; shift ;;
    --archivos) ARCHIVOS="$2"; shift ;;
    --qc-resumen) QC_RESUMEN="$2"; shift ;;
    --salida) SALIDA="$2"; shift ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "Argumento desconocido: $1" >&2; exit 3 ;;
  esac
  shift
done
[ -f "$CONFIG" ] && [ -d "$ARCHIVOS" ] || { echo "Uso: entrega.sh --config C --servicio S --archivos DIR --qc-resumen T" >&2; exit 3; }

error() { if [ -n "${GITHUB_ACTIONS:-}" ]; then echo "::error::$*" >&2; else echo "ERROR: $*" >&2; fi; }
info() { echo "[entrega $(date -u +%H:%M:%S)] $*"; }
resumen() { if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then echo "$*" >> "$GITHUB_STEP_SUMMARY"; else echo "$*"; fi; }
cfg() {
  python3 -c '
import sys, json
sys.path.insert(0, sys.argv[3])
import plan_chunks as pc
v = pc.cargar_config(sys.argv[1])
for k in sys.argv[2].split("."):
    v = v.get(k) if isinstance(v, dict) else None
print("" if v is None else (json.dumps(v) if isinstance(v, (dict, list)) else v))
' "$CONFIG" "$1" "$DIR_SCRIPTS"
}

SERVICIO="${SERVICIO:-$(cfg entrega.servicio)}"; SERVICIO="${SERVICIO:-temp.sh}"
case "$SERVICIO" in
  temp.sh) LIMITE=$(( 4 * 1000 * 1000 * 1000 )); DIAS=3 ;;
  litterbox) LIMITE=$(( 1000 * 1000 * 1000 )); DIAS=3 ;;
  *) error "Servicio desconocido: $SERVICIO (temp.sh | litterbox)"; exit 3 ;;
esac
LB_TIEMPO="$(cfg entrega.litterbox_tiempo)"; LB_TIEMPO="${LB_TIEMPO:-72h}"

VIDEO="$(cfg video.nombre_salida)"; ZIPF="$(cfg entrega.nombre_zip_fotos)"; BLEND="$(cfg entrega.nombre_blend)"
LISTA=()
for n in "$VIDEO" "$ZIPF" "$BLEND"; do
  [ -n "$n" ] || continue
  p="$(find -L "$ARCHIVOS" -type f -name "$n" -print -quit)"
  [ -n "$p" ] || { error "No encuentro $n en $ARCHIVOS"; exit 3; }
  tam="$(stat -L -c %s "$p")"
  if [ "$tam" -ge "$LIMITE" ]; then
    otro=$([ "$SERVICIO" = temp.sh ] && echo litterbox || echo temp.sh)
    error "$n ocupa $tam B: supera el límite de $SERVICIO. Usa servicio=$otro si cabe."
    exit 3
  fi
  LISTA+=("$p")
done

subir() { # ruta → URL
  local r="$1"
  if [ "$SERVICIO" = temp.sh ]; then
    curl -fsS --retry 3 --retry-delay 5 --max-time 3600 -F "file=@$r" https://temp.sh/upload
  else
    curl -fsS --retry 3 --retry-delay 5 --max-time 3600 -F reqtype=fileupload -F "time=$LB_TIEMPO" \
      -F "fileToUpload=@$r" https://litterbox.catbox.moe/resources/internals/api.php
  fi
}
bajar() { # URL destino
  if [ "$SERVICIO" = temp.sh ]; then
    curl -fsS --retry 3 --retry-delay 5 --max-time 3600 -X POST -o "$2" "$1"
  else
    curl -fsSL --retry 3 --retry-delay 5 --max-time 3600 -o "$2" "$1"
  fi
}
cli() { # URL nombre → comando de descarga
  if [ "$SERVICIO" = temp.sh ]; then echo "curl -X POST -o $2 $1"; else echo "curl -L -o $2 $1"; fi
}

subir_verificado() { # ruta → URL verificada por SHA-256
  local r="$1" sha url espera=10 i
  sha="$(sha256sum "$r" | cut -d' ' -f1)"
  for i in 1 2 3; do
    info "Subiendo $(basename "$r") a $SERVICIO (intento $i)…" >&2
    url="$(subir "$r" | tr -d '[:space:]' || true)"
    if [[ "$url" == https://* ]]; then
      local tmp; tmp="$(mktemp)"
      if bajar "$url" "$tmp" && [ "$(sha256sum "$tmp" | cut -d' ' -f1)" = "$sha" ]; then
        rm -f "$tmp"; echo "$url"; return 0
      fi
      rm -f "$tmp"
      info "La verificación SHA-256 de $(basename "$r") no coincide; repito la subida." >&2
    else
      info "Respuesta inesperada del servicio: ${url:0:200}" >&2
    fi
    sleep "$espera"; espera=$(( espera * 3 ))
  done
  return 1
}

GENERADO="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
CADUCA="$(date -u -d "+$DIAS days" +%Y-%m-%dT%H:%M:%SZ)"
ARCH_JSON="[]"
for r in "${LISTA[@]}"; do
  url="$(subir_verificado "$r")" || { error "No se pudo subir y verificar $(basename "$r") tras 3 intentos."; exit 1; }
  n="$(basename "$r")"
  ARCH_JSON="$(jq --arg n "$n" --argjson b "$(stat -L -c %s "$r")" --arg s "$(sha256sum "$r" | cut -d' ' -f1)" \
    --arg u "$url" --arg c "$(cli "$url" "$n")" '. + [{nombre: $n, bytes: $b, sha256: $s, url: $u, descarga_cli: $c}]' <<< "$ARCH_JSON")"
  info "$n → $url"
done

MF="$(find -L "$ARCHIVOS" -type f -name manifiesto_final.json -print -quit)"
HUELLA="$( [ -n "$MF" ] && jq -r .huella_render "$MF" || python3 "$DIR_SCRIPTS/plan_chunks.py" --config "$CONFIG" --modo huella)"
COMMIT="$( [ -n "$MF" ] && jq -r '.commit // ""' "$MF" || echo "${GITHUB_SHA:-}")"
RUNS="$( [ -n "$MF" ] && jq -c '.runs // []' "$MF" || echo '[]')"
jq -n --arg t "$(cfg video.titulo)" --arg g "$GENERADO" --arg s "$SERVICIO" --arg c "$CADUCA" \
  --argjson a "$ARCH_JSON" --arg q "$QC_RESUMEN" --arg h "$HUELLA" --arg co "$COMMIT" --argjson r "$RUNS" \
  '{proyecto: "AX620", titulo: $t, generado: $g, servicio: $s, caduca: $c, archivos: $a,
    qc: {aprobado: true, revisado_por: "nube de Claude", resumen: $q}, huella_render: $h, commit: $co, runs: $r}' \
  > "$SALIDA"
url_json="$(subir_verificado "$SALIDA")" || { error "No se pudo subir entrega.json."; exit 1; }
jq --arg u "$url_json" '.entrega_json_url = $u' "$SALIDA" > "$SALIDA.tmp" && mv "$SALIDA.tmp" "$SALIDA"

resumen "## 📦 Entrega — $(cfg video.titulo)"
resumen ""
resumen "Servicio: **$SERVICIO** · generado $GENERADO · **caduca $CADUCA** (3 días)."
resumen ""
resumen "| Archivo | Tamaño | SHA-256 | Enlace | Descarga por consola |"
resumen "|---|---|---|---|---|"
jq -r '.archivos[] | "| \(.nombre) | \((.bytes / 1000000 * 10 | floor) / 10) MB | `\(.sha256[0:16])…` | \(.url) | `\(.descarga_cli)` |"' "$SALIDA" \
  | while read -r l; do resumen "$l"; done
resumen ""
resumen "entrega.json: $url_json"
resumen ""
resumen "QC: $QC_RESUMEN"
info "entrega.json → $url_json"
