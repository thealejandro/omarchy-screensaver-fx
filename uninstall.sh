#!/bin/bash
# Quita los enlaces de omarchy-screensaver-fx. El salvapantallas vuelve a ser el de Omarchy.
set -euo pipefail
REPO=$(dirname "$(realpath "$0")")
for dst in ~/.local/bin/ttfx ~/.local/bin/omarchy-screensaver \
  ~/.config/omarchy/branding/screensaver-fx.py \
  ~/.config/omarchy/branding/generate-screensaver.py \
  ~/.config/omarchy/hooks/post-update.d/screensaver-fx-check; do
  if [[ -L $dst && $(realpath "$dst") == "$REPO"/* ]]; then
    rm "$dst" && echo "  quitado $dst"
  fi
done
echo "Listo. Tu screensaver.txt no se toca."
