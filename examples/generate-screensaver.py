#!/usr/bin/env python3
# Genera ~/.config/omarchy/branding/screensaver.txt con JACC + XACODE.
# Letras dibujadas a mano al estilo del logo de Omarchy (trazos gruesos,
# esquinas redondeadas con ▄ ▀). Sin dependencias: python3 generate-screensaver.py

from pathlib import Path

OUT = Path.home() / ".config/omarchy/branding/screensaver.txt"

# Rótulo principal: 9 filas x 11 columnas, trazo de 4
BIG = {
    "J": [
        "       ████",
        "       ████",
        "       ████",
        "       ████",
        "       ████",
        "       ████",
        "████   ████",
        "████   ████",
        " ▀███████▀ ",
    ],
    "A": [
        " ▄███████▄ ",
        "████   ████",
        "████   ████",
        "████   ████",
        "████▄▄▄████",
        "████▀▀▀████",
        "████   ████",
        "████   ████",
        "████   ████",
    ],
    "C": [
        " ▄███████▄ ",
        "████   ████",
        "████   ▀▀▀▀",
        "████       ",
        "████       ",
        "████       ",
        "████   ▄▄▄▄",
        "████   ████",
        " ▀███████▀ ",
    ],
}

# Subtítulo: 4 filas x 6 columnas, trazo de 2
SMALL = {
    "X": [
        "██  ██",
        " ▀██▀ ",
        " ▄██▄ ",
        "██  ██",
    ],
    "A": [
        "▄████▄",
        "██  ██",
        "██▀▀██",
        "██  ██",
    ],
    "C": [
        "▄████▄",
        "██  ▀▀",
        "██  ▄▄",
        "▀████▀",
    ],
    "O": [
        "▄████▄",
        "██  ██",
        "██  ██",
        "▀████▀",
    ],
    "D": [
        "█████▄",
        "██  ██",
        "██  ██",
        "█████▀",
    ],
    "E": [
        "██████",
        "██▄▄  ",
        "██▀▀  ",
        "██████",
    ],
}


def render(text: str, font: dict, gap: int) -> list[str]:
    rows = len(next(iter(font.values())))
    return [(" " * gap).join(font[c][r] for c in text) for r in range(rows)]


name = render("JACC", BIG, 3)
logo = render("XACODE", SMALL, 2)
width = max(len(name[0]), len(logo[0]))


def center(lines: list[str]) -> list[str]:
    pad = " " * ((width - len(lines[0])) // 2)
    return [(pad + l).rstrip() for l in lines]


OUT.write_text("\n".join(center(name) + ["", ""] + center(logo)) + "\n")
print(f"{OUT} actualizado ({width} columnas)")
