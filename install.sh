#!/bin/bash
# Instala omarchy-screensaver-fx enlazando los archivos de este repo, de modo
# que `git pull` lo actualiza todo. No modifica nada de Omarchy.
# Uso: ./install.sh [--with-generator]
#   --with-generator  enlaza también examples/generate-screensaver.py
set -euo pipefail

REPO=$(dirname "$(realpath "$0")")
BRANDING=~/.config/omarchy/branding
HOOKS=~/.config/omarchy/hooks/post-update.d

# Mensaje en el idioma de Omarchy: msg "texto en español" "text in English"
msg() {
  local l=
  read -r l _ <"${XDG_CONFIG_HOME:-$HOME/.config}/omarchy/language" 2>/dev/null || true
  l=${l:-${LC_ALL:-${LC_TIME:-${LANG:-}}}}
  l=${l,,}
  if [[ ${l:0:2} == es ]]; then printf '%s' "$1"; else printf '%s' "$2"; fi
}

for cmd in ttfx python3 omarchy; do
  command -v "$cmd" >/dev/null || { echo "$(msg "Falta '$cmd': esto necesita Omarchy con ttfx." "Missing '$cmd': this needs Omarchy with ttfx.")" >&2; exit 1; }
done

link() { # enlaza $1 en $2, guardando antes lo que hubiera si no era un enlace
  local src=$1 dst=$2
  mkdir -p "$(dirname "$dst")"
  if [[ -e $dst && ! -L $dst ]]; then
    mv "$dst" "$dst.bak-$(date +%Y%m%d-%H%M%S)"
    echo "  $(msg "copia de seguridad" "backup"): $dst.bak-*"
  fi
  ln -sfn "$src" "$dst"
  echo "  $dst -> $src"
}

echo "$(msg "Enlazando:" "Linking:")"
chmod +x "$REPO"/bin/* "$REPO"/screensaver-check.sh "$REPO"/screensaver-fx.py
link "$REPO/bin/ttfx" ~/.local/bin/ttfx
link "$REPO/bin/omarchy-screensaver" ~/.local/bin/omarchy-screensaver
link "$REPO/screensaver-fx.py" "$BRANDING/screensaver-fx.py"
link "$REPO/screensaver-check.sh" "$HOOKS/screensaver-fx-check"
[[ ${1:-} == "--with-generator" ]] && link "$REPO/examples/generate-screensaver.py" "$BRANDING/generate-screensaver.py"

# ~/.local/bin debe ir antes que /usr/bin en el PATH de Hyprland
hypr_pid=$(pgrep -x Hyprland | head -1 || true)
if [[ -n $hypr_pid ]]; then
  path=$(tr '\0' '\n' <"/proc/$hypr_pid/environ" | sed -n 's/^PATH=//p')
  local_i=$(tr ':' '\n' <<<"$path" | grep -nxF "$HOME/.local/bin" | head -1 | cut -d: -f1)
  usr_i=$(tr ':' '\n' <<<"$path" | grep -nxF /usr/bin | head -1 | cut -d: -f1)
  if [[ -z $local_i || ( -n $usr_i && $local_i -gt $usr_i ) ]]; then
    echo "$(msg "Aviso: en el PATH de Hyprland ~/.local/bin no va antes que /usr/bin; los envoltorios no se usarán." "Warning: in the Hyprland PATH ~/.local/bin does not come before /usr/bin; the wrappers will not be used.")" >&2
  fi
fi

echo
bash "$REPO/screensaver-check.sh"
echo "$(msg "Pruébalo con" "Try it with"): omarchy-launch-screensaver force"
