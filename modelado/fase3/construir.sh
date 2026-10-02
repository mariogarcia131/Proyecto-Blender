#!/bin/bash
# Reconstruye la Fase 3 encadenando las fases desde un hito. Uso: construir.sh [desde] [hasta]
set -eo pipefail
cd "$(dirname "$(readlink -f "$0")")"
FASES=(f01_base f02_overhead f03_panel f04_pedestal f05_cabina f06_morro f07_funcional f08_presentacion)
HITOS=(h01_base h02_overhead h03_panel h04_pedestal h05_cabina h06_morro h07_funcional h08_presentacion)
DESDE=${1:-1}; HASTA=${2:-${#FASES[@]}}
for ((i=DESDE; i<=HASTA; i++)); do
  f=${FASES[$((i-1))]}; [ -f fases/$f.py ] || { echo "falta fases/$f.py, me detengo"; break; }
  if [ $i -eq 1 ]; then ent=hitos/h00_inicial.blend; else ent=hitos/${HITOS[$((i-2))]}.blend; fi
  sal=hitos/${HITOS[$((i-1))]}.blend
  echo "== $f: $ent -> $sal"; rm -f "$sal"
  blender -b "$ent" -P fases/$f.py -- --salida "$PWD/$sal" 2>&1 | grep -E "^\[|Error|rror|Traceback|line [0-9]" | grep -v CUEW
  [ -f "$sal" ] || { echo "ERROR: no se generó $sal"; exit 1; }
done
