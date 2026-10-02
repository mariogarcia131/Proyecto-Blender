#!/usr/bin/env bash
# Limpieza del repositorio (docs/ESTRATEGIA_RENDER.md, secciones j) paso 10 y n).
#
#   limpieza.sh                       limpieza final: 0 Releases, 0 tags, 0 artefactos, 0 cachés
#                                     y ningún binario en Git; código ≠ 0 si queda algo.
#   limpieza.sh --intermedios RUNS    solo borra los artefactos intermedios (frames-*, segmento-*,
#                                     manifest-*, foto-*, bordes-*, relevo-*, benchmark) de las
#                                     ejecuciones indicadas (IDs separados por comas, o «todos»).
#   limpieza.sh --release TAG         borra una Release y su tag (transporte del .blend).
#
# Necesita GH_TOKEN (o GITHUB_TOKEN) y GITHUB_REPOSITORY. Permisos: actions: write, contents: write.
set -euo pipefail

export GH_TOKEN="${GH_TOKEN:-${GITHUB_TOKEN:-}}"
REPO="${GITHUB_REPOSITORY:?Falta GITHUB_REPOSITORY}"
[ -n "$GH_TOKEN" ] || { echo "Falta GH_TOKEN o GITHUB_TOKEN" >&2; exit 3; }

info() { echo "[limpieza $(date -u +%H:%M:%S)] $*"; }
error() { if [ -n "${GITHUB_ACTIONS:-}" ]; then echo "::error::$*" >&2; else echo "ERROR: $*" >&2; fi; }
resumen() { if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then echo "$*" >> "$GITHUB_STEP_SUMMARY"; else echo "$*"; fi; }

borrar_release() { # tag
  if gh api "repos/$REPO/releases/tags/$1" --jq .id > /dev/null 2>&1; then
    local id; id="$(gh api "repos/$REPO/releases/tags/$1" --jq .id)"
    gh api -X DELETE "repos/$REPO/releases/$id" > /dev/null && info "Release $1 borrada"
  fi
  if gh api "repos/$REPO/git/refs/tags/$1" > /dev/null 2>&1; then
    gh api -X DELETE "repos/$REPO/git/refs/tags/$1" > /dev/null && info "Tag $1 borrado"
  fi
}

borrar_artefactos() { # filtro jq sobre .artifacts[] → borra los que cumplan
  local ids
  ids="$(gh api --paginate "repos/$REPO/actions/artifacts?per_page=100" --jq ".artifacts[] | select($1) | .id")"
  for id in $ids; do
    gh api -X DELETE "repos/$REPO/actions/artifacts/$id" > /dev/null && info "Artefacto $id borrado"
  done
}

case "${1:-}" in
  --release)
    borrar_release "${2:?Falta el tag}"
    exit 0 ;;
  --intermedios)
    RUNS="${2:?Faltan los run IDs (o «todos»)}"
    if [ "$RUNS" = todos ]; then
      borrar_artefactos '.name | test("^(frames|segmento|manifest|foto|bordes|relevo)-|^benchmark$")'
      exit 0
    fi
    filtro_runs="$(echo "$RUNS" | tr ',' '\n' | grep -E '^[0-9]+$' | sed 's/.*/.workflow_run.id == &/' | paste -sd'|' | sed 's/|/ or /g')"
    [ -n "$filtro_runs" ] || { error "Lista de runs vacía"; exit 3; }
    borrar_artefactos "($filtro_runs) and (.name | test(\"^(frames|segmento|manifest|foto|bordes|relevo)-|^benchmark$\"))"
    exit 0 ;;
  "") ;;
  *) echo "Uso: limpieza.sh [--intermedios RUNS | --release TAG]" >&2; exit 3 ;;
esac

# 1) Releases y tags
for tag in $(gh api --paginate "repos/$REPO/releases?per_page=100" --jq '.[].tag_name'); do
  borrar_release "$tag"
done
for ref in $(gh api --paginate "repos/$REPO/git/matching-refs/tags" --jq '.[].ref' 2>/dev/null); do
  gh api -X DELETE "repos/$REPO/git/$ref" > /dev/null && info "Tag suelto ${ref#refs/tags/} borrado"
done
# 2) artefactos
borrar_artefactos "true"
# 3) cachés de Actions
for id in $(gh api --paginate "repos/$REPO/actions/caches?per_page=100" --jq '.actions_caches[].id'); do
  gh api -X DELETE "repos/$REPO/actions/caches/$id" > /dev/null && info "Caché $id borrada"
done
# 4) binarios en Git (árbol del commit actual)
binarios=""
if git rev-parse --is-inside-work-tree > /dev/null 2>&1; then
  binarios="$(git ls-files -z | xargs -0 -r -I{} sh -c 'case "{}" in *.blend|*.blend1|*.png|*.exr|*.mp4|*.zip|*.jpg|*.tar*) echo "{}";; *) [ "$(stat -c %s "{}")" -gt 1048576 ] && echo "{}";; esac; true')"
fi

# 5) verificación
sleep 5
n_rel="$(gh api --paginate "repos/$REPO/releases?per_page=100" --jq '.[].id' | wc -l)"
n_tag="$(gh api --paginate "repos/$REPO/git/matching-refs/tags" --jq '.[].ref' 2>/dev/null | wc -l)"
n_art="$(gh api "repos/$REPO/actions/artifacts?per_page=1" --jq .total_count)"
n_cache="$(gh api "repos/$REPO/actions/caches?per_page=1" --jq .total_count)"
n_bin="$(printf '%s' "$binarios" | grep -c . || true)"
resumen "## 🧹 Limpieza"
resumen ""
resumen "| Elemento | Quedan |"
resumen "|---|---|"
resumen "| Releases | $n_rel |"
resumen "| Tags | $n_tag |"
resumen "| Artefactos | $n_art |"
resumen "| Cachés | $n_cache |"
resumen "| Binarios en Git | $n_bin |"
if [ "$n_rel$n_tag$n_art$n_cache$n_bin" = "00000" ]; then
  resumen ""
  resumen "**Repositorio limpio ✔**"
  info "Repositorio limpio: 0 Releases, 0 tags, 0 artefactos, 0 cachés, 0 binarios."
else
  [ -n "$binarios" ] && error "Binarios en Git: $binarios"
  error "La limpieza no está completa (Releases $n_rel, tags $n_tag, artefactos $n_art, cachés $n_cache, binarios $n_bin)."
  exit 1
fi
