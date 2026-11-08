#!/usr/bin/env python3
"""Animaciones propias para el salvapantallas de Omarchy.

Uso:  screensaver-fx.py [efecto] [--seconds N]
      screensaver-fx.py --list | --palette
Lo lanza el envoltorio bin/ttfx cuando corre el salvapantallas.
Sin efecto elige uno al azar. Lee el rótulo de
~/.config/omarchy/branding/screensaver.txt y los colores del tema activo,
y deja el rótulo siempre centrado en pantalla.
https://github.com/thealejandro/omarchy-screensaver-fx
"""

import math
import os
import random
import re
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

ART = Path.home() / ".config/omarchy/branding/screensaver.txt"
THEME = Path.home() / ".local/state/omarchy/current/theme/colors.toml"
FPS = 30
CSI = "\x1b["
WHITE = (255, 255, 255)


# ── Colores ──────────────────────────────────────────────────────────────────

def hex2rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def luminance(rgb):
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = map(lin, rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def mix(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def scale(c, k):
    return tuple(max(0, min(255, round(v * k))) for v in c)


def palette():
    """Colores del tema, aclarados lo justo para leerse sobre fondo negro."""
    keys = ["accent", "bright_blue", "bright_cyan", "bright_magenta",
            "magenta", "cyan", "blue", "bright_green"]
    found = {}
    try:
        for k, v in re.findall(r'^(\w+)\s*=\s*"(#[0-9a-fA-F]{6})"',
                               THEME.read_text(), re.M):
            found[k] = hex2rgb(v)
    except OSError:
        pass
    out = []
    for k in keys:
        if k not in found:
            continue
        c, t = found[k], 0.0
        while luminance(c) < 0.22 and t < 1:
            t += 0.05
            c = mix(found[k], WHITE, t)
        if all(sum(abs(a - b) for a, b in zip(c, o)) > 60 for o in out):
            out.append(c)
        if len(out) == 4:
            break
    if len(out) < 2:
        out = [hex2rgb("8A008A"), hex2rgb("00D1FF")]
    return out


def gradient(pal, t):
    """Gradiente cíclico sobre la paleta, t en cualquier rango."""
    t = (t % 1.0) * len(pal)
    i = int(t)
    return mix(pal[i % len(pal)], pal[(i + 1) % len(pal)], t - i)


# ── Pantalla ─────────────────────────────────────────────────────────────────

class Screen:
    def __init__(self):
        try:
            self.cols, self.rows = os.get_terminal_size(sys.stdout.fileno())
        except OSError:
            self.cols, self.rows = 120, 40
        lines = ART.read_text().rstrip("\n").split("\n")
        self.h = len(lines)
        self.w = max(len(l) for l in lines)
        self.x0 = max(0, (self.cols - self.w) // 2)
        self.y0 = max(0, (self.rows - self.h) // 2)
        self.cells = [(x, y, ch) for y, l in enumerate(lines)
                      for x, ch in enumerate(l) if ch != " "]
        self.occupied = {(self.x0 + x, self.y0 + y) for x, y, _ in self.cells}
        self.buf = []

    def put(self, x, y, ch, rgb):
        if 0 <= x < self.cols and 0 <= y < self.rows:
            r, g, b = rgb
            self.buf.append(f"{CSI}{y + 1};{x + 1}H{CSI}38;2;{r};{g};{b}m{ch}")

    def text(self, x, y, s, rgb):
        for i, ch in enumerate(s):
            self.put(x + i, y, ch, rgb)

    def clear_rect(self, x, y, w, h):
        for row in range(max(0, y), min(self.rows, y + h)):
            x1, x2 = max(0, x), min(self.cols, x + w)
            if x2 > x1:
                self.buf.append(f"{CSI}{row + 1};{x1 + 1}H{CSI}0m" + " " * (x2 - x1))

    def clear(self):
        self.buf.append(f"{CSI}0m{CSI}2J")

    def logo(self, color_fn):
        """Dibuja el rótulo; color_fn(x, y) devuelve el color o None."""
        for x, y, ch in self.cells:
            c = color_fn(x, y)
            if c is not None:
                self.put(self.x0 + x, self.y0 + y, ch, c)

    def flush(self):
        if self.buf:
            sys.stdout.write("".join(self.buf))
            sys.stdout.flush()
            self.buf = []


def frames(seconds):
    """Itera a FPS fijos devolviendo el tiempo transcurrido."""
    t0 = time.monotonic()
    n = 0
    while (t := time.monotonic() - t0) < seconds:
        yield t
        n += 1
        wait = t0 + n / FPS - time.monotonic()
        if wait > 0:
            time.sleep(wait)


def base_color(s, pal, shift=0.0):
    """Gradiente diagonal suave del rótulo."""
    return lambda x, y: gradient(pal, (x / max(1, s.w) + y / max(1, s.h) * 0.3) * 0.5 + shift)


# ── Efectos ──────────────────────────────────────────────────────────────────

def fx_neon(s, pal, secs):
    """Los trazos se encienden como tubos de neón y luego respiran con un brillo que barre."""
    on_at = {(x, y): random.uniform(0.2, 2.2) for x, y, _ in s.cells}
    flick = {(x, y): random.random() < 0.35 for x, y, _ in s.cells}
    s.clear()
    for t in frames(secs):
        breath = 0.78 + 0.22 * math.sin(t * 2.2)
        band = ((t - 3) % 3.2) / 3.2 * (s.w + s.h + 20) - 10

        def color(x, y):
            start = on_at[(x, y)]
            if t < start:
                return (18, 18, 22)
            if flick[(x, y)] and t < start + 0.5 and int((t - start) * 20) % 3 == 0:
                return (40, 40, 48)
            c = scale(gradient(pal, x / s.w * 0.6 + t * 0.03), breath)
            d = abs((x + y * 2) - band)
            if t > 3 and d < 4:
                c = mix(c, WHITE, (1 - d / 4) * 0.85)
            return c
        s.logo(color)
        s.flush()


def fx_starfield(s, pal, secs):
    """Viaje entre estrellas; el rótulo aparece en el centro."""
    n = max(80, s.cols * s.rows // 25)
    stars = [[random.uniform(-1, 1), random.uniform(-1, 1), random.uniform(0.1, 1)]
             for _ in range(n)]
    prev = []
    cx, cy = s.cols / 2, s.rows / 2
    s.clear()
    for t in frames(secs):
        for x, y in prev:
            s.put(x, y, " ", (0, 0, 0))
        prev = []
        for st in stars:
            st[2] -= 0.012
            if st[2] <= 0.02:
                st[:] = [random.uniform(-1, 1), random.uniform(-1, 1), 1.0]
            x = int(cx + st[0] / st[2] * cx * 0.5)
            y = int(cy + st[1] / st[2] * cy * 0.5)
            if not (0 <= x < s.cols and 0 <= y < s.rows):
                st[:] = [random.uniform(-1, 1), random.uniform(-1, 1), 1.0]
                continue
            if s.x0 - 2 <= x < s.x0 + s.w + 2 and s.y0 - 1 <= y < s.y0 + s.h + 1:
                continue  # el rótulo queda limpio, las estrellas pasan por fuera
            z = st[2]
            ch = "·" if z > 0.66 else "•" if z > 0.33 else "✦"
            s.put(x, y, ch, scale(WHITE, 1.15 - z))
            prev.append((x, y))
        fade = min(1.0, max(0.0, (t - 1.5) / 2.5))
        if fade > 0:
            s.logo(lambda x, y: scale(gradient(pal, x / s.w * 0.6 + t * 0.04), fade))
        s.flush()


def fx_terminal(s, pal, secs):
    """Una terminal escribe «whoami» y responde imprimiendo el rótulo."""
    px, py = s.x0, max(0, s.y0 - 3)
    prompt_c, cmd_c = pal[0], (220, 220, 220)
    cmd = "whoami"
    s.clear()
    s.text(px, py, "❯ ", prompt_c)
    typed, printed = 0, 0
    t_typing, t_print = 0.8, 0.8 + len(cmd) * 0.13 + 0.4
    rows_done = 0
    for t in frames(secs):
        if typed < len(cmd) and t >= t_typing + typed * 0.13:
            s.put(px + 2 + typed, py, cmd[typed], cmd_c)
            typed += 1
        if t < t_print:
            cursor_x = px + 2 + typed
            on = int(t * 2.5) % 2 == 0
            s.put(cursor_x, py, "█" if on else " ", cmd_c)
        elif rows_done < s.h:
            s.put(px + 2 + typed, py, " ", cmd_c)
            target = min(s.h, int((t - t_print) / 0.07) + 1)
            while rows_done < target:
                y = rows_done
                s.logo(lambda x, yy: gradient(pal, x / s.w * 0.6) if yy == y else None)
                rows_done += 1
        else:
            end_y = min(s.rows - 1, s.y0 + s.h + 2)
            s.text(px, end_y, "❯ ", prompt_c)
            on = int(t * 2.5) % 2 == 0
            s.put(px + 2, end_y, "█" if on else " ", cmd_c)
        s.flush()


GLITCH = "░▒▓█▀▄▌▐"


def fx_glitch(s, pal, secs):
    """Rótulo estable con ráfagas de interferencia digital (desfase RGB y ruido)."""
    pad = 4
    burst_until, next_burst = 0.0, 1.0
    s.clear()
    for t in frames(secs):
        if t >= next_burst:
            burst_until = t + random.uniform(0.15, 0.5)
            next_burst = burst_until + random.uniform(0.6, 2.2)
        s.clear_rect(s.x0 - pad, s.y0 - 1, s.w + pad * 2, s.h + 2)
        base = base_color(s, pal, t * 0.02)
        if t < burst_until:
            shifts = {y: (random.choice((-3, -2, -1, 1, 2, 3)) if random.random() < 0.35 else 0)
                      for y in range(s.h)}
            for x, y, ch in s.cells:
                s.put(s.x0 + x - 1, s.y0 + y, ch, (200, 0, 60))
                s.put(s.x0 + x + 1, s.y0 + y, ch, (0, 200, 220))
            for x, y, ch in s.cells:
                ch2 = random.choice(GLITCH) if random.random() < 0.06 else ch
                s.put(s.x0 + x + shifts[y], s.y0 + y, ch2, mix(base(x, y), WHITE, 0.3))
        else:
            s.logo(base)
        s.flush()


def fx_plasma(s, pal, secs):
    """Un plasma de los colores del tema fluye dentro de las letras."""
    s.clear()
    for t in frames(secs):
        fade = min(1.0, t / 1.5)

        def color(x, y):
            v = (math.sin(x * 0.12 + t * 1.1) + math.sin(y * 0.45 - t * 1.4)
                 + math.sin((x + y * 2) * 0.08 + t * 0.7)
                 + math.sin(math.hypot(x - s.w / 2, (y - s.h / 2) * 2) * 0.2 - t * 1.6))
            return scale(gradient(pal, v / 8 + 0.5 + t * 0.02), fade)
        s.logo(color)
        s.flush()


DIGITS = {
    "0": ["▄████▄", "██  ██", "██  ██", "▀████▀"],
    "1": ["▄███  ", "  ██  ", "  ██  ", "██████"],
    "2": ["▄████▄", "    ██", "▄█▀▀▀▀", "██████"],
    "3": ["▄████▄", "  ▄▄█▀", "  ▀▀█▄", "▀████▀"],
    "4": ["██  ██", "██  ██", "▀▀▀▀██", "    ██"],
    "5": ["██████", "██▄▄▄▄", "▀▀▀▀██", "▀████▀"],
    "6": ["▄████▄", "██▄▄▄▄", "██▀▀██", "▀████▀"],
    "7": ["██████", "    ██", "   ██ ", "  ██  "],
    "8": ["▄████▄", "▀█▄▄█▀", "▄█▀▀█▄", "▀████▀"],
    "9": ["▄████▄", "██▄▄██", "▀▀▀▀██", "▀████▀"],
    ":": ["  ", "▀▀", "▄▄", "  "],
}
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]


def language():
    """Idioma de Omarchy (omarchy language); si no hay, el del locale."""
    f = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "omarchy/language"
    try:
        code = f.read_text().split()[0]
    except (OSError, IndexError):
        code = os.environ.get("LC_ALL") or os.environ.get("LC_TIME") or os.environ.get("LANG", "")
    return code[:2].lower()


def long_date(now):
    """Fecha larga en español si Omarchy está en español; si no, en inglés."""
    if language() == "es":
        return f"{DIAS[now.weekday()]}, {now.day} de {MESES[now.month - 1]} de {now.year}"
    return f"{DAYS[now.weekday()]}, {MONTHS[now.month - 1]} {now.day}, {now.year}"


def fx_clock(s, pal, secs):
    """Rótulo con la hora y la fecha debajo; el conjunto queda centrado."""
    clock_h = 4 + 2  # dígitos + línea de fecha
    gap = 3
    total = s.h + gap + clock_h
    s.y0 = max(0, (s.rows - total) // 2)
    s.occupied = {(s.x0 + x, s.y0 + y) for x, y, _ in s.cells}
    cy = s.y0 + s.h + gap
    s.clear()
    last = None
    for t in frames(secs):
        fade = min(1.0, t / 1.2)
        s.logo(lambda x, y: scale(gradient(pal, x / s.w * 0.6 + t * 0.03), fade))
        now = datetime.now()
        key = (now.strftime("%H:%M"), now.second % 2, round(fade, 1))
        if key != last:
            last = key
            hhmm = now.strftime("%H:%M")
            glyphs = [DIGITS[c] for c in hhmm]
            width = sum(len(g[0]) for g in glyphs) + 2 * (len(glyphs) - 1)
            x = (s.cols - width) // 2
            s.clear_rect(0, cy, s.cols, clock_h)
            for ch, g in zip(hhmm, glyphs):
                visible = ch != ":" or now.second % 2 == 0
                for r, row in enumerate(g):
                    for i, c in enumerate(row):
                        if c != " " and visible:
                            s.put(x + i, cy + r, c, scale((235, 235, 235), fade))
                x += len(g[0]) + 2
            fecha = long_date(now)
            s.text((s.cols - len(fecha)) // 2, cy + 5, fecha, scale(pal[0], fade))
        s.flush()


EFFECTS = {
    "neon": (fx_neon, 14),
    "starfield": (fx_starfield, 16),
    "terminal": (fx_terminal, 10),
    "glitch": (fx_glitch, 12),
    "plasma": (fx_plasma, 15),
    "clock": (fx_clock, 20),
}


def main():
    args = sys.argv[1:]
    if "--list" in args:
        print("\n".join(EFFECTS))
        return
    if "--palette" in args:
        print(" ".join("%02x%02x%02x" % c for c in palette()))
        return
    secs = None
    if "--seconds" in args:
        i = args.index("--seconds")
        secs = float(args[i + 1])
        del args[i:i + 2]
    name = args[0] if args else random.choice(list(EFFECTS))
    if name not in EFFECTS:
        sys.exit(f"Efecto desconocido: {name}. Disponibles: {', '.join(EFFECTS)}")
    fn, default = EFFECTS[name]

    def restore(*_):
        sys.stdout.write(f"{CSI}0m{CSI}?25h")
        sys.stdout.flush()
        os._exit(0)

    try:  # morir junto con el envoltorio que nos lanzó (Linux)
        import ctypes
        ctypes.CDLL("libc.so.6", use_errno=True).prctl(1, signal.SIGTERM)  # PR_SET_PDEATHSIG
        if os.getppid() == 1:
            os._exit(0)
    except (OSError, AttributeError):
        pass
    signal.signal(signal.SIGTERM, restore)
    signal.signal(signal.SIGINT, restore)
    sys.stdout.write(f"{CSI}?25l")
    try:
        fn(Screen(), palette(), secs or default)
    except BrokenPipeError:
        pass
    finally:
        sys.stdout.write(f"{CSI}0m")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
