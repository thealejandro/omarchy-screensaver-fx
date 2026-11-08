#!/bin/bash
# Quita los enlaces de omarchy-screensaver-fx. El salvapantallas vuelve a ser el de Omarchy.
set -euo pipefail

# Mensaje en el idioma de Omarchy: msg "texto en español" "text in English"
msg() {
  local l=
  read -r l _ <"${XDG_CONFIG_HOME:-$HOME/.config}/omarchy/language" 2>/dev/null || true
  l=${l:-${LC_ALL:-${LC_TIME:-${LANG:-}}}}
  l=${l,,}
  if [[ ${l:0:2} == es ]]; then printf '%s' "$1"; else printf '%s' "$2"; fi
}
REPO=$(dirname "$(realpath "$0")")
for dst in ~/.local/bin/ttfx ~/.local/bin/omarchy-screensaver \
  ~/.config/omarchy/branding/screensaver-fx.py \
  ~/.config/omarchy/branding/generate-screensaver.py \
  ~/.config/omarchy/hooks/post-update.d/screensaver-fx-check; do
  if [[ -L $dst && $(realpath "$dst") == "$REPO"/* ]]; then
    rm "$dst" && echo "  $(msg "quitado" "removed") $dst"
  fi
done
echo "$(msg "Listo. Tu screensaver.txt no se toca." "Done. Your screensaver.txt is left untouched.")"
