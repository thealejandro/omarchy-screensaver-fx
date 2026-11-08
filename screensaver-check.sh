#!/bin/bash
# Comprueba que omarchy-screensaver-fx sigue encajando con la versión actual de
# Omarchy y ttfx. Se ejecuta tras cada `omarchy update` (hook post-update
# screensaver-fx-check) y también a mano: bash <repo>/screensaver-check.sh
#
# Nunca rompe nada: si algo deja de encajar, el envoltorio de ttfx cede al
# comportamiento original de Omarchy y aquí se avisa de qué hay que adaptar.

BRANDING=~/.config/omarchy/branding
FX=$BRANDING/screensaver-fx.py
WRAP=~/.local/bin/ttfx
LOG=~/.local/state/omarchy/screensaver-check.log
problems=()
warn() { problems+=("$1"); }

# 1. Script original de Omarchy y cómo llama a ttfx
orig="${OMARCHY_PATH:-/usr/share/omarchy}/bin/omarchy-screensaver"
[[ -f $orig ]] || orig=$(type -ap omarchy-screensaver | grep -v "^$HOME/" | head -1)
if [[ ! -f $orig ]]; then
  warn "No se encuentra el script original omarchy-screensaver (¿Omarchy lo movió o renombró?)."
else
  grep -q 'ttfx' "$orig" || warn "El salvapantallas de Omarchy ya no usa ttfx: las animaciones propias no se aplican."
  grep -q -- '--random-effect' "$orig" || warn "Omarchy ya no pasa --random-effect a ttfx: el envoltorio deja pasar la llamada sin cambios."
  grep -q 'branding/screensaver.txt' "$orig" || warn "Omarchy cambió la ruta del texto del salvapantallas (antes branding/screensaver.txt)."
  grep -qE 'pgrep[^#]*-x ttfx|pkill -x ttfx' "$orig" || warn "Omarchy ya no vigila el proceso por el nombre ttfx: revisar cómo se cierran las animaciones propias."
fi

# 2. El envoltorio de ttfx tiene prioridad en el PATH
first=$(type -ap ttfx | head -1)
[[ $(realpath "$first" 2>/dev/null) == $(realpath "$WRAP" 2>/dev/null) ]] ||
  warn "El ttfx que se usa es $first y no el envoltorio $WRAP (orden del PATH)."

# 3. ttfx real: efectos y opciones de color
real=$(type -ap ttfx | while read -r c; do [[ $(realpath "$c") != $(realpath "$WRAP") ]] && { echo "$c"; break; }; done)
if [[ -z $real ]]; then
  warn "No está instalado ttfx."
else
  n=$("$real" --help 2>/dev/null | awk '/^Commands:/{f=1;next} /^Options:/{f=0} f && $1!="help"' | wc -l)
  ((n > 0)) || warn "No se pudo leer la lista de efectos de ttfx (cambió el formato de --help)."
  "$real" wipe --help 2>/dev/null | grep -q -- '--final-gradient-stops' ||
    warn "ttfx ya no admite --final-gradient-stops: los efectos saldrán solo con sus colores originales."
fi

# 4. Animaciones propias y colores del tema
if ! python3 -I "$FX" --list >/dev/null 2>&1; then
  warn "screensaver-fx.py no arranca con el Python actual."
else
  [[ -f ~/.local/state/omarchy/current/theme/colors.toml ]] ||
    warn "Omarchy movió colors.toml del tema: las animaciones usan colores por defecto."
  for e in $(python3 -I "$FX" --list); do
    script -qec "stty cols 120 rows 40; python3 -I '$FX' $e --seconds 0.5" /dev/null >/dev/null 2>&1 ||
      warn "La animación propia «$e» falla."
  done
fi

# 5. Texto del salvapantallas
if [[ ! -s $BRANDING/screensaver.txt ]]; then
  warn "Falta $BRANDING/screensaver.txt o está vacío."
elif [[ -f $BRANDING/generate-screensaver.py ]] &&
  cmp -s "$BRANDING/screensaver.txt" "${OMARCHY_PATH:-/usr/share/omarchy}/logo.txt"; then
  warn "screensaver.txt volvió al logo de Omarchy. Regenerar: python3 $BRANDING/generate-screensaver.py"
fi

mkdir -p "$(dirname "$LOG")"
{
  echo "== $(date '+%F %T') · omarchy $(omarchy version 2>/dev/null) · $("${real:-ttfx}" --version 2>/dev/null)"
  if ((${#problems[@]})); then printf -- '- %s\n' "${problems[@]}"; else echo "OK"; fi
} >>"$LOG"

if ((${#problems[@]})); then
  echo "omarchy-screensaver-fx: ${#problems[@]} aviso(s), detalle en $LOG"
  printf -- '  - %s\n' "${problems[@]}"
  omarchy-notification-send -u normal "Salvapantallas: revisar tras la actualización" \
    "${problems[0]} (detalle en ~/.local/state/omarchy/screensaver-check.log)" >/dev/null 2>&1 || true
else
  echo "omarchy-screensaver-fx: todo encaja con esta versión de Omarchy."
fi
exit 0
