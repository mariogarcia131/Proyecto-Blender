#!/usr/bin/env bash
# Montaje del vídeo y de las fotos del render distribuido del AX620.
# Especificación: docs/ESTRATEGIA_RENDER.md, secciones j), k) y l), y «Contratos entre componentes».
#
# Dos usos:
#
# 1) En cada trabajo de render (paso «Segmentos MP4», if: always()):
#      assemble.sh --codificar-trozo --config render_config.json --frames DIR \
#        --manifiesto manifest-c007.json --salida DIR_SEGMENTOS --bordes DIR_BORDES
#    Un segmento seg_AAAAAA-BBBBBB.mp4 (H.264 4:4:4 10 bits, CRF intermedio) por cada tramo
#    contiguo de frames válidos del manifiesto, con su JSON hermano (huella, trozo, run, intento).
#    En DIR_BORDES copia los PNG originales que puede pedir la muestra de QC: los dos primeros y
#    los dos últimos de cada segmento y los frames fijos (inicio, fin y benchmark).
#
# 2) En el trabajo assemble:
#      assemble.sh --config render_config.json --segmentos DIR --manifiestos DIR --parte K \
#        [--ultima] [--parche RANGOS] [--solo-fotos] [--fotos DIR] [--bordes DIR] [--salida DIR] [--run-id N]
#    Comprueba la cobertura (plan_chunks.py --modo cobertura), concatena los segmentos sin
#    recodificar en parte-KK.mp4 (+ parte-KK.json con las fronteras de segmento) y, en la última
#    parte, hace la codificación final única, la valida con ffprobe, crea el ZIP de fotos, el
#    manifiesto final y la muestra de QC. Si GH_TOKEN y GITHUB_REPOSITORY están definidos,
#    descarga solo los artefactos bordes-* que necesita la muestra.
#
# Códigos de salida: 0 correcto · 2 faltan frames (cobertura) · 3 error de validación o de disco.
set -euo pipefail

DIR_SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLAN="$DIR_SCRIPTS/plan_chunks.py"

MODO=montaje
CONFIG="" FRAMES="" MANIFIESTO="" SALIDA="" BORDES="" SEGMENTOS="" MANIFIESTOS="" FOTOS=""
PARTE=1 ULTIMA=0 PARCHE="" SOLO_FOTOS=0 RUN_ID="${GITHUB_RUN_ID:-0}"

uso() { sed -n '2,24p' "$0"; exit "${1:-0}"; }
while [ $# -gt 0 ]; do
  case "$1" in
    --codificar-trozo) MODO=trozo ;;
    --config) CONFIG="$2"; shift ;;
    --frames) FRAMES="$2"; shift ;;
    --manifiesto) MANIFIESTO="$2"; shift ;;
    --salida) SALIDA="$2"; shift ;;
    --bordes) BORDES="$2"; shift ;;
    --segmentos) SEGMENTOS="$2"; shift ;;
    --manifiestos) MANIFIESTOS="$2"; shift ;;
    --fotos) FOTOS="$2"; shift ;;
    --parte) PARTE="$2"; shift ;;
    --ultima) ULTIMA=1 ;;
    --parche) PARCHE="$2"; shift ;;
    --solo-fotos) SOLO_FOTOS=1 ;;
    --run-id) RUN_ID="$2"; shift ;;
    -h|--help) uso 0 ;;
    *) echo "Argumento desconocido: $1" >&2; uso 3 ;;
  esac
  shift
done
[ -n "$CONFIG" ] || { echo "Falta --config" >&2; exit 3; }
CONFIG="$(realpath "$CONFIG")"

en_actions() { [ -n "${GITHUB_ACTIONS:-}" ]; }
error() { if en_actions; then echo "::error::$*" >&2; else echo "ERROR: $*" >&2; fi; }
aviso() { if en_actions; then echo "::warning::$*" >&2; else echo "AVISO: $*" >&2; fi; }
info() { echo "[assemble $(date -u +%H:%M:%S)] $*"; }
resumen() { if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then echo "$*" >> "$GITHUB_STEP_SUMMARY"; fi; }

# Lectura de la configuración (sin comentarios «_», con la misma función que el planificador)
cfg() {
  python3 -c '
import sys, json
sys.path.insert(0, sys.argv[3])
import plan_chunks as pc
c = pc.cargar_config(sys.argv[1])
v = c
for k in sys.argv[2].split("."):
    v = v[int(k)] if isinstance(v, list) else v.get(k) if isinstance(v, dict) else None
    if v is None:
        break
print(json.dumps(v) if isinstance(v, (dict, list)) else ("" if v is None else v))
' "$CONFIG" "$1" "$DIR_SCRIPTS"
}

FPS="$(cfg fps)"
HUELLA="$(python3 "$PLAN" --config "$CONFIG" --modo huella)"
ANCHO="$(cfg resolucion.ancho)"; ALTO="$(cfg resolucion.alto)"; PORC="$(cfg resolucion.porcentaje)"
ANCHO=$(( ANCHO * ${PORC:-100} / 100 )); ALTO=$(( ALTO * ${PORC:-100} / 100 ))
INI="$(cfg frames.inicio)"; FIN="$(cfg frames.fin)"
PATRON="frame_%06d.png"

pix_fmt_intermedio() {
  local p; p="$(cfg video.pix_fmt_intermedio)"; p="${p:-yuv444p10le}"
  local ayuda; ayuda="$(ffmpeg -hide_banner -h encoder=libx264 2>/dev/null || true)"
  if ! grep -q -- "$p" <<< "$ayuda"; then
    aviso "El ffmpeg del runner no admite $p en libx264: uso yuv444p."
    p=yuv444p
  fi
  echo "$p"
}

ffprobe_frames() { # número de fotogramas (paquetes) de un MP4
  ffprobe -v error -select_streams v:0 -count_packets -show_entries stream=nb_read_packets -of csv=p=0 "$1"
}

# --------------------------------------------------------------------------- 1) segmentos de un trozo
codificar_trozo() {
  [ -d "$FRAMES" ] && [ -f "$MANIFIESTO" ] && [ -n "$SALIDA" ] || {
    error "--codificar-trozo necesita --frames, --manifiesto y --salida"; exit 3; }
  mkdir -p "$SALIDA"; [ -n "$BORDES" ] && mkdir -p "$BORDES"
  local crf pix tramos
  crf="$(cfg video.crf_intermedio)"; crf="${crf:-11}"
  pix="$(pix_fmt_intermedio)"
  # tramos contiguos de frames del manifiesto cuyo PNG existe y conserva el tamaño registrado
  tramos="$(python3 - "$MANIFIESTO" "$FRAMES" "$DIR_SCRIPTS" <<'PY'
import json, os, sys
sys.path.insert(0, sys.argv[3])
import plan_chunks as pc
m = json.load(open(sys.argv[1]))
ok = [f["frame"] for f in m.get("frames_completados", [])
      if os.path.exists(os.path.join(sys.argv[2], "frame_%06d.png" % f["frame"]))
      and os.path.getsize(os.path.join(sys.argv[2], "frame_%06d.png" % f["frame"])) == f["bytes"]]
for a, b in pc.compactar(ok):
    print(a, b)
PY
)"
  if [ -z "$tramos" ]; then
    aviso "Trozo sin frames válidos: no hay segmento que codificar."
    return 0
  fi
  local trozo run intento commit fijos
  trozo="$(jq -r .trozo "$MANIFIESTO")"; run="$(jq -r '.run_id // 0' "$MANIFIESTO")"
  intento="$(jq -r '.intento // 1' "$MANIFIESTO")"; commit="$(jq -r '.commit // ""' "$MANIFIESTO")"
  fijos="$(python3 -c '
import sys; sys.path.insert(0, sys.argv[2]); import plan_chunks as pc
c = pc.cargar_config(sys.argv[1])
print(" ".join(str(x) for x in sorted({int(c["frames"]["inicio"]), int(c["frames"]["fin"])} | set(c.get("benchmark", {}).get("frames", [])))))
' "$CONFIG" "$DIR_SCRIPTS")"
  while read -r a b; do
    local n nombre
    n=$(( b - a + 1 )); nombre="$(printf 'seg_%06d-%06d' "$a" "$b")"
    info "$trozo: codificando $nombre ($n frames, CRF $crf, $pix)"
    ffmpeg -hide_banner -loglevel error -y -framerate "$FPS" -start_number "$a" -i "$FRAMES/$PATRON" \
      -frames:v "$n" -vf "scale=out_color_matrix=bt709:out_range=tv,format=$pix" \
      -c:v libx264 -preset medium -crf "$crf" -pix_fmt "$pix" \
      -color_primaries bt709 -color_trc bt709 -colorspace bt709 -color_range tv \
      -g "$FPS" -keyint_min 1 -an "$SALIDA/$nombre.mp4"
    local hechos; hechos="$(ffprobe_frames "$SALIDA/$nombre.mp4")"
    if [ "$hechos" != "$n" ]; then
      error "$nombre tiene $hechos fotogramas, se esperaban $n"; rm -f "$SALIDA/$nombre.mp4"; exit 3
    fi
    jq -n --arg h "$HUELLA" --arg t "$trozo" --argjson r "$run" --argjson i "$intento" --arg c "$commit" \
      --argjson a "$a" --argjson b "$b" --arg s "$(sha256sum "$SALIDA/$nombre.mp4" | cut -d' ' -f1)" \
      --argjson by "$(stat -c %s "$SALIDA/$nombre.mp4")" --argjson fps "$FPS" \
      '{version: 1, huella_render: $h, trozo: $t, run_id: $r, intento: $i, commit: $c, inicio: $a, fin: $b,
        frames: ($b - $a + 1), fps: $fps, bytes: $by, sha256: $s}' > "$SALIDA/$nombre.json"
    if [ -n "$BORDES" ]; then
      local f
      for f in $a $((a + 1)) $((b - 1)) $b $fijos; do
        if [ "$f" -ge "$a" ] && [ "$f" -le "$b" ] && [ -f "$FRAMES/$(printf "$PATRON" "$f")" ]; then
          [ -e "$BORDES/$(printf "$PATRON" "$f")" ] || cp "$FRAMES/$(printf "$PATRON" "$f")" "$BORDES/"
        fi
      done
    fi
  done <<< "$tramos"
  resumen "Segmentos de $trozo: $(echo "$tramos" | awk '{printf "%s%06d-%06d", (NR>1?", ":""), $1, $2}')"
}

# --------------------------------------------------------------------------- utilidades del montaje
comprobar_disco() { # bytes necesarios, directorio
  local libre; libre=$(( $(df -Pk "$2" | awk 'NR==2{print $4}') * 1024 ))
  if [ "$1" -ge "$libre" ]; then
    error "Disco insuficiente en $2: hacen falta $1 B y hay $libre B libres."; exit 3
  fi
}

descargar_artefacto() { # run_id nombre destino → 0 si lo descargó
  [ -n "${GH_TOKEN:-}" ] && [ -n "${GITHUB_REPOSITORY:-}" ] || return 1
  local id
  id="$(gh api "repos/$GITHUB_REPOSITORY/actions/runs/$1/artifacts?name=$2&per_page=1" \
        --jq '.artifacts[0] | select(.expired == false) | .id' 2>/dev/null || true)"
  [ -n "$id" ] || return 1
  mkdir -p "$3"
  gh api "repos/$GITHUB_REPOSITORY/actions/artifacts/$id/zip" > "$3/.artefacto.zip" 2>/dev/null || return 1
  unzip -oq "$3/.artefacto.zip" -d "$3" && rm -f "$3/.artefacto.zip"
}

# desmonta maestros parte-NN.mp4 en sus segmentos (corte sin recodificar: cada segmento empieza
# en fotograma clave) para el modo parche
desmontar_maestros() { # dir_relevo dir_salida
  python3 - "$CONFIG" "$1" "$DIR_SCRIPTS" <<'PY' |
import sys, json
sys.path.insert(0, sys.argv[3])
import plan_chunks as pc
cfg = pc.cargar_config(sys.argv[1])
ms, _ = pc.maestros_validos(sys.argv[2], pc.huella_render(cfg))
for m in ms:
    for s in m["segmentos"]:
        print(m["ruta"], m["inicio"], s["inicio"], s["fin"], s.get("trozo", "?"), s.get("run_id", m["run_id"]),
              s.get("intento", 1))
PY
  while read -r ruta m0 a b trozo run intento; do
    local nombre n t0
    nombre="$(printf 'seg_%06d-%06d' "$a" "$b")"; n=$(( b - a + 1 ))
    t0="$(python3 -c "print('%.6f' % (($a - $m0) / $FPS))")"
    mkdir -p "$2/r$run"
    ffmpeg -hide_banner -loglevel error -y -ss "$t0" -i "$ruta" -frames:v "$n" -c copy -an "$2/r$run/$nombre.mp4"
    [ "$(ffprobe_frames "$2/r$run/$nombre.mp4")" = "$n" ] || { error "Corte de $nombre fallido"; exit 3; }
    jq -n --arg h "$HUELLA" --arg t "$trozo" --argjson r "$run" --argjson i "$intento" \
      --argjson a "$a" --argjson b "$b" '{version: 1, huella_render: $h, trozo: $t, run_id: $r, intento: $i,
       inicio: $a, fin: $b, frames: ($b - $a + 1), desmontado: true}' > "$2/r$run/$nombre.json"
  done
}

montar_parte() { # k dir_candidatos dir_salida → parte-KK.mp4 + parte-KK.json
  local k="$1" cand="$2" out="$3" cob codigo
  cob="$out/cobertura-parte-$(printf %02d "$k").json"
  set +e
  python3 "$PLAN" --config "$CONFIG" --modo cobertura --segmentos "$cand" --parte "$k" --run-id "$RUN_ID" > "$cob"
  codigo=$?
  set -e
  if [ "$codigo" -eq 2 ]; then
    resumen "### ❌ Faltan frames en la parte $k"
    resumen "Frames: \`$(jq -r .faltan_txt "$cob")\`"
    resumen "Reanudar en < 24 h: \`$(jq -r .comando_resume "$cob")\`"
    exit 2
  elif [ "$codigo" -ne 0 ]; then
    error "Cobertura de la parte $k: código $codigo"; exit 3
  fi
  if [ "$(jq '.rango == null' "$cob")" = "true" ]; then
    info "Parte $k sin frames de vídeo (solo fotos)."
    return 0
  fi
  local suma a b nombre
  suma="$(jq -r '.elegidos[].ruta' "$cob" | xargs -r stat -c %s | awk '{s+=$1} END{print s+0}')"
  comprobar_disco $(( suma * 2 )) "$out"
  a="$(jq .rango[0] "$cob")"; b="$(jq .rango[1] "$cob")"
  nombre="$(printf 'parte-%02d' "$k")"
  jq -r '.elegidos[] | "file " + (.ruta | @sh)' "$cob" > "$out/lista-$nombre.txt"
  info "Parte $k: $(jq '.elegidos | length' "$cob") segmentos, frames $a-$b"
  ffmpeg -hide_banner -loglevel error -y -f concat -safe 0 -i "$out/lista-$nombre.txt" -c copy -an "$out/$nombre.mp4"
  local hechos; hechos="$(ffprobe_frames "$out/$nombre.mp4")"
  if [ "$hechos" != "$(( b - a + 1 ))" ]; then
    error "$nombre tiene $hechos fotogramas, se esperaban $(( b - a + 1 )) (¿segmentos solapados en la lista?)"
    exit 3
  fi
  jq --argjson k "$k" --argjson r "$RUN_ID" --argjson i "${GITHUB_RUN_ATTEMPT:-1}" --arg c "${GITHUB_SHA:-}" \
    '{version: 1, huella_render, parte: $k, run_id: $r, intento: $i, commit: $c, inicio: .rango[0], fin: .rango[1],
      segmentos: [.elegidos[] | {inicio, fin, trozo, run_id, intento}], muestra, fronteras_muestra}' \
    "$cob" > "$out/$nombre.json"
  resumen "Parte $k: \`$nombre.mp4\` con $hechos frames ($a-$b), $(jq '.elegidos | length' "$cob") segmentos."
}

# --------------------------------------------------------------------------- 2) montaje
montaje() {
  [ -d "$SEGMENTOS" ] || { error "--segmentos no es un directorio"; exit 3; }
  SALIDA="${SALIDA:-$PWD/montaje}"; mkdir -p "$SALIDA"; SALIDA="$(realpath "$SALIDA")"
  if [ "$SOLO_FOTOS" = 1 ]; then   # modo fotos (proceso sin vídeo): solo el ZIP y sus miniaturas
    fotos_zip
    mkdir -p "$SALIDA/muestra-qc/fotos_previas"
    for x in "$SALIDA"/fotos/*.png; do
      [ -e "$x" ] && ffmpeg -hide_banner -loglevel error -y -i "$x" -vf "scale=1920:-2" -q:v 2 \
        "$SALIDA/muestra-qc/fotos_previas/$(basename "${x%.png}").jpg"
    done
    return
  fi
  local cand="$SEGMENTOS"
  if [ -n "$PARCHE" ]; then
    info "Parche: desmontando los maestros relevados en segmentos"
    mkdir -p "$SALIDA/desmontados"
    desmontar_maestros "$SEGMENTOS" "$SALIDA/desmontados"
    cand="$SALIDA/candidatos"; mkdir -p "$cand"
    ln -sfn "$(realpath "$SEGMENTOS")" "$cand/relevo"; ln -sfn "$SALIDA/desmontados" "$cand/desmontados"
    # en el parche se rehacen todas las partes con los segmentos sustituidos
    local np; np="$(python3 "$PLAN" --config "$CONFIG" --modo estimar | jq .partes)"
    mkdir -p "$SALIDA/maestros_nuevos"
    for k in $(seq 1 "$np"); do montar_parte "$k" "$cand" "$SALIDA/maestros_nuevos"; done
    ULTIMA=1
    final "$SALIDA/maestros_nuevos"
    return
  fi
  montar_parte "$PARTE" "$cand" "$SALIDA"
  if [ "$ULTIMA" = 1 ]; then
    # maestros: los relevados de partes anteriores + el de esta parte
    mkdir -p "$SALIDA/maestros"
    ln -sfn "$(realpath "$SEGMENTOS")" "$SALIDA/maestros/relevo"
    for x in "$SALIDA"/parte-*.mp4 "$SALIDA"/parte-*.json; do [ -e "$x" ] && ln -sf "$x" "$SALIDA/maestros/"; done
    final "$SALIDA/maestros"
  fi
}

final() { # dir con maestros parte-NN (recursivo)
  local dirm="$1" cob nombre_video crf preset pixf perfil
  cob="$SALIDA/cobertura-video.json"
  set +e
  python3 "$PLAN" --config "$CONFIG" --modo cobertura --maestros --segmentos "$dirm" --run-id "$RUN_ID" > "$cob"
  local codigo=$?
  set -e
  if [ "$codigo" -ne 0 ]; then
    resumen "### ❌ Faltan partes del vídeo: \`$(jq -r .faltan_txt "$cob" 2>/dev/null)\`"
    error "Los maestros no cubren el vídeo completo."; exit "$codigo"
  fi
  nombre_video="$(cfg video.nombre_salida)"; crf="$(cfg video.crf_final)"; preset="$(cfg video.preset_final)"
  pixf="$(cfg video.pix_fmt_final)"; perfil="$(cfg video.perfil_final)"
  if [ "${crf:-18}" -gt 18 ]; then error "video.crf_final = $crf > 18"; exit 3; fi
  jq -r '.elegidos[] | "file " + (.ruta | @sh)' "$cob" > "$SALIDA/lista-final.txt"
  local suma; suma="$(jq -r '.elegidos[].ruta' "$cob" | xargs -r stat -L -c %s | awk '{s+=$1} END{print s+0}')"
  comprobar_disco $(( suma * 2 )) "$SALIDA"
  info "Codificación final: $(jq '.elegidos | length' "$cob") maestro(s) → $nombre_video (CRF $crf, $preset, $pixf)"
  ffmpeg -hide_banner -loglevel error -y -f concat -safe 0 -i "$SALIDA/lista-final.txt" \
    -vf "scale=in_color_matrix=bt709:out_color_matrix=bt709:in_range=tv:out_range=tv,format=$pixf" \
    -c:v libx264 -profile:v "$perfil" -preset "$preset" -crf "$crf" -pix_fmt "$pixf" \
    -color_primaries bt709 -color_trc bt709 -colorspace bt709 -color_range tv \
    -r "$FPS" -movflags +faststart -an "$SALIDA/$nombre_video"

  # validación con ffprobe (§j paso 6)
  ffprobe -v error -select_streams v:0 -count_frames \
    -show_entries stream=width,height,r_frame_rate,nb_read_frames,pix_fmt,profile,codec_name \
    -show_entries format=duration,size -of json "$SALIDA/$nombre_video" > "$SALIDA/ffprobe.json"
  python3 - "$SALIDA/ffprobe.json" "$ANCHO" "$ALTO" "$FPS" "$INI" "$FIN" "$pixf" <<'PY' || exit 3
import json, sys
d = json.load(open(sys.argv[1])); s = d["streams"][0]; f = d["format"]
ancho, alto, fps, ini, fin, pixf = int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6]), sys.argv[7]
n = fin - ini + 1
dur = float(f["duration"])
errores = []
if (s["width"], s["height"]) != (ancho, alto): errores.append(f"resolución {s['width']}x{s['height']} ≠ {ancho}x{alto}")
if s["r_frame_rate"] != f"{fps}/1": errores.append(f"r_frame_rate {s['r_frame_rate']} ≠ {fps}/1")
if int(s["nb_read_frames"]) != n: errores.append(f"nb_read_frames {s['nb_read_frames']} ≠ {n}")
if abs(dur - n / fps) > 1.0 / fps + 1e-6: errores.append(f"duración {dur:.3f} s ≠ {n / fps:.3f} s ± 1 frame")
if s["pix_fmt"] != pixf: errores.append(f"pix_fmt {s['pix_fmt']} ≠ {pixf}")
if s.get("profile") != "High": errores.append(f"perfil {s.get('profile')} ≠ High")
if int(f["size"]) >= 4 * 10**9: errores.append(f"tamaño {f['size']} B ≥ 4 GB (límite de temp.sh)")
for e in errores:
    print("::error::ffprobe: " + e, file=sys.stderr)
print(f"ffprobe: {s['width']}x{s['height']} · {s['r_frame_rate']} · {s['nb_read_frames']} frames · "
      f"{dur:.3f} s · {s['pix_fmt']} · {s.get('profile')} · {int(f['size']) / 1e6:.1f} MB")
sys.exit(1 if errores else 0)
PY
  resumen "### Vídeo final"
  resumen "\`\`\`"; resumen "$(jq -c '{stream: .streams[0], format: .format}' "$SALIDA/ffprobe.json")"; resumen "\`\`\`"

  fotos_zip
  manifiesto_final "$cob" "$nombre_video"
  muestra_qc "$cob" "$nombre_video"
  resumen "⚠️ **QC pendiente** en la nube de Claude: no se ha publicado nada fuera de GitHub."
}

fotos_zip() {
  local nfotos zipn
  nfotos="$(cfg fotos | jq 'length')"
  [ "$nfotos" -gt 0 ] || { info "Sin fotos en la configuración."; return 0; }
  [ -d "$FOTOS" ] || { error "Hay $nfotos fotos en la configuración pero falta --fotos"; exit 3; }
  zipn="$(cfg entrega.nombre_zip_fotos)"; zipn="${zipn:-Fotos.zip}"
  mkdir -p "$SALIDA/fotos"
  python3 - "$CONFIG" "$FOTOS" "$SALIDA/fotos" "$DIR_SCRIPTS" <<'PY' || exit 3
import json, os, shutil, struct, sys
sys.path.insert(0, sys.argv[4])
import plan_chunks as pc
cfg = pc.cargar_config(sys.argv[1])
hechas = pc.fotos_hechas(sys.argv[2], pc.huella_render(cfg))
errores = []
for f in cfg["fotos"]:
    ruta = hechas.get(f["id"])
    if not ruta:
        errores.append(f"falta la foto {f['id']}"); continue
    with open(ruta, "rb") as fh:
        cab = fh.read(29)
    w, h = struct.unpack(">II", cab[16:24]); bits = cab[24]
    if (w, h) != (int(f["ancho"]), int(f["alto"])) or bits != int(cfg["salida"]["profundidad_bits"]):
        errores.append(f"{f['id']}: {w}x{h} {bits} bits, se esperaba {f['ancho']}x{f['alto']} {cfg['salida']['profundidad_bits']} bits")
        continue
    shutil.copy2(ruta, os.path.join(sys.argv[3], f["id"] + ".png"))
for e in errores:
    print("::error::fotos: " + e, file=sys.stderr)
sys.exit(1 if errores else 0)
PY
  (cd "$SALIDA/fotos" && rm -f "../$zipn" && zip -0 -q "../$zipn" ./*.png)
  local dentro; dentro="$(unzip -Z1 "$SALIDA/$zipn" | wc -l)"
  [ "$dentro" = "$nfotos" ] || { error "El ZIP tiene $dentro fotos, se esperaban $nfotos"; exit 3; }
  info "Fotos: $nfotos en $zipn ($(stat -c %s "$SALIDA/$zipn") B)"
  resumen "Fotos: **$nfotos** en \`$zipn\` ($(( $(stat -c %s "$SALIDA/$zipn") / 1000000 )) MB)."
}

manifiesto_final() { # cobertura_video nombre_video
  local runs
  runs="$(find -L "$SEGMENTOS" ${FOTOS:+"$FOTOS"} -name 'manifest-*.json' -o -name 'parte-*.json' -o -name 'seg_*.json' 2>/dev/null \
          | xargs -r jq -r '.run_id // empty' 2>/dev/null | sort -un | jq -Rsc 'split("\n") | map(select(length > 0) | tonumber)')"
  jq -n --arg h "$HUELLA" --arg c "${GITHUB_SHA:-}" --argjson runs "${runs:-[]}" --argjson r "$RUN_ID" \
    --slurpfile cob "$1" --slurpfile fp "$SALIDA/ffprobe.json" \
    --arg v "$2" --arg vs "$(sha256sum "$SALIDA/$2" | cut -d' ' -f1)" --argjson vb "$(stat -c %s "$SALIDA/$2")" \
    --argjson ini "$INI" --argjson fin "$FIN" --argjson fps "$FPS" --arg res "${ANCHO}x${ALTO}" \
    --arg fecha "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    '{version: 1, fecha: $fecha, huella_render: $h, commit: $c, run_montaje: $r, runs: ($runs + [$r] | unique),
      frames: {inicio: $ini, fin: $fin}, fps: $fps, resolucion: $res,
      video: {nombre: $v, bytes: $vb, sha256: $vs, ffprobe: $fp[0]},
      partes: [$cob[0].elegidos[] | {ruta: (.ruta | split("/") | last), inicio, fin, run_id}]}' \
    > "$SALIDA/manifiesto_final.json"
  # fronteras de segmento de cada maestro
  local tmp; tmp="$(mktemp)"
  jq -r '.elegidos[].json' "$1" | xargs -r jq -s '[.[] | {parte, segmentos}]' > "$tmp"
  jq --slurpfile s "$tmp" '.fronteras_segmentos = $s[0]' "$SALIDA/manifiesto_final.json" > "$tmp.2" \
    && mv "$tmp.2" "$SALIDA/manifiesto_final.json"
  if [ -d "$SALIDA/fotos" ]; then
    (cd "$SALIDA/fotos" && sha256sum ./*.png 2>/dev/null) | jq -Rsc 'split("\n") | map(select(length > 0) | split("  ") |
      {id: (.[1] | ltrimstr("./") | rtrimstr(".png")), sha256: .[0]})' > "$tmp"
    jq --slurpfile f "$tmp" '.fotos = $f[0]' "$SALIDA/manifiesto_final.json" > "$tmp.2" \
      && mv "$tmp.2" "$SALIDA/manifiesto_final.json"
  fi
  rm -f "$tmp"
}

muestra_qc() { # cobertura_video nombre_video
  local M="$SALIDA/muestra-qc" frames video="$SALIDA/$2"
  rm -rf "$M"; mkdir -p "$M/frames" "$M/mp4" "$M/cada5s" "$M/fotos" "$M/fotos_previas"
  cp "$SALIDA/ffprobe.json" "$SALIDA/manifiesto_final.json" "$CONFIG" "$M/"
  # frames de la muestra: unión de las muestras de cada maestro (primero, último, benchmark, fronteras)
  frames="$(jq -r '.elegidos[].json' "$1" | xargs -r jq -r '.muestra[]?' | sort -un | tr '\n' ' ')"
  info "Muestra de QC: frames $frames"
  # PNG originales: bordes ya presentes o descargados de los artefactos bordes-<trozo>-a<intento>
  local f buscados=()
  for f in $frames; do buscados+=("$(printf "$PATRON" "$f")"); done
  local dir_b="${BORDES:-$SALIDA/bordes}"; mkdir -p "$dir_b"
  local faltan_png=()
  for n in "${buscados[@]}"; do [ -n "$(find -L "$dir_b" -name "$n" -print -quit)" ] || faltan_png+=("$n"); done
  if [ "${#faltan_png[@]}" -gt 0 ]; then
    # qué artefacto contiene cada frame: el segmento elegido que lo cubre
    local seg_json; seg_json="$(jq -r '.elegidos[].json' "$1" | xargs -r jq -c '.segmentos[]')"
    for n in "${faltan_png[@]}"; do
      f=$((10#${n:6:6}))
      local s; s="$(echo "$seg_json" | jq -c --argjson f "$f" 'select(.inicio <= $f and .fin >= $f)' | head -1)"
      [ -n "$s" ] || continue
      local nom="bordes-$(jq -r .trozo <<< "$s")-a$(jq -r .intento <<< "$s")" run; run="$(jq -r .run_id <<< "$s")"
      [ -d "$dir_b/$run-$nom" ] && continue
      descargar_artefacto "$run" "$nom" "$dir_b/$run-$nom" || aviso "No se pudo descargar $nom del run $run (¿caducado?)"
    done
  fi
  local lista_sel=""
  for f in $frames; do
    n="$(printf "$PATRON" "$f")"
    local p; p="$(find -L "$dir_b" -name "$n" -print -quit)"
    if [ -n "$p" ]; then cp "$p" "$M/frames/$n"; else aviso "PNG original de $f no disponible para la muestra"; fi
    lista_sel="${lista_sel:+$lista_sel+}eq(n\\,$(( f - INI )))"
  done
  # mismos frames extraídos del MP4 final (una sola pasada)
  if [ -n "$lista_sel" ]; then
    ffmpeg -hide_banner -loglevel error -y -i "$video" -vf "select='$lista_sel'" -fps_mode passthrough \
      -pix_fmt rgb48be "$M/mp4/tmp_%04d.png"
    local i=1
    for f in $frames; do
      [ -f "$M/mp4/tmp_$(printf %04d "$i").png" ] && mv "$M/mp4/tmp_$(printf %04d "$i").png" "$M/mp4/mp4_$(printf "$PATRON" "$f")"
      i=$(( i + 1 ))
    done
  fi
  # un frame cada 5 s (revisión visual completa del vídeo) y hoja de contactos (1 por segundo)
  ffmpeg -hide_banner -loglevel error -y -i "$video" -vf "select='not(mod(n\\,$(( FPS * 5 ))))'" -fps_mode passthrough \
    -q:v 2 "$M/cada5s/tmp_%04d.jpg"
  local k=0
  for x in "$M"/cada5s/tmp_*.jpg; do
    [ -e "$x" ] || continue
    mv "$x" "$M/cada5s/t$(printf %04d $(( k * 5 )))s_$(printf "frame_%06d" $(( INI + k * 5 * FPS ))).jpg"
    k=$(( k + 1 ))
  done
  local filas; filas=$(( ( FIN - INI + 1 + FPS * 10 - 1) / (FPS * 10) ))
  ffmpeg -hide_banner -loglevel error -y -i "$video" \
    -vf "fps=1,scale=320:-2,tile=10x${filas}:padding=4:color=black" -frames:v 1 -q:v 3 "$M/hoja_contactos.jpg"
  # fotos: PNG de una selección (todas si caben) y miniaturas JPG de todas
  if [ -d "$SALIDA/fotos" ]; then
    local maxf; maxf="$(cfg qc.fotos_muestra_max)"; maxf="${maxf:-10}"
    python3 - "$SALIDA/fotos" "$maxf" <<'PY' | while read -r x; do cp "$SALIDA/fotos/$x" "$M/fotos/"; done
import os, random, sys
ids = sorted(x for x in os.listdir(sys.argv[1]) if x.endswith(".png"))
n = int(sys.argv[2])
if len(ids) > n:
    ids = sorted(random.Random(620).sample(ids, n))
print("\n".join(ids))
PY
    for x in "$SALIDA"/fotos/*.png; do
      ffmpeg -hide_banner -loglevel error -y -i "$x" -vf "scale=1920:-2" -q:v 2 "$M/fotos_previas/$(basename "${x%.png}").jpg"
    done
  fi
  info "muestra-qc: $(find "$M" -type f | wc -l) archivos, $(du -sh "$M" | cut -f1)"
  resumen "Muestra de QC: $(ls "$M/frames" | wc -l) PNG originales, $(ls "$M/mp4" | wc -l) del MP4, $(ls "$M/cada5s" | wc -l) frames cada 5 s, $(ls "$M/fotos_previas" | wc -l) miniaturas de fotos."
}

if [ "$MODO" = trozo ]; then codificar_trozo; else montaje; fi
