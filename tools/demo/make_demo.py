#!/usr/bin/env python3
"""Genera el vídeo de presentación, el póster, las capturas y el GIF del README.

Ejecuta de verdad cada animación en una terminal virtual (pty + pyte), dibuja
los fotogramas con Pillow (los bloques ▀▄█ se trazan como rectángulos para que
queden nítidos) y monta una presentación a 2560x1440 con ffmpeg.

Uso (desde la raíz del repo):
    uv run --with pyte --with pillow tools/demo/make_demo.py [--lang en|es|all] [--quick]

Salida en docs/: demo-<lang>.mp4, demo-<lang>.webm, demo-poster-<lang>.webp,
demo.gif (inglés) y shots/<animación>.png. Las capturas intermedias se guardan
en ~/.cache/omarchy-screensaver-fx/demo para no repetirlas.
"""

import argparse
import fcntl
import io
import os
import pickle
import pty
import select
import shutil
import signal
import struct
import subprocess
import sys
import termios
import time
import urllib.request
import zipfile
from pathlib import Path

import pyte
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[2]
FX = ROOT / "screensaver-fx.py"
DOCS = ROOT / "docs"
CACHE = Path.home() / ".cache/omarchy-screensaver-fx/demo"
ART = Path.home() / ".config/omarchy/branding/screensaver.txt"
THEMES_DIRS = [Path.home() / ".config/omarchy/themes", Path("/usr/share/omarchy/themes")]
INTER_URL = "https://github.com/rsms/inter/releases/download/v4.1/Inter-4.1.zip"
MONO = "/usr/share/fonts/TTF/JetBrainsMonoNerdFont-Regular.ttf"

W, H, FPS = 1920, 1080, 30   # maqueta: todas las coordenadas van en estas unidades
SCALE = 4 / 3                 # salida a 2560x1440, nítida en pantallas 2K y Retina
COLS, ROWS = 100, 30          # terminal de la demo
CW, CH = 15, 30               # celda en px -> 1500x900 (capturas sueltas)
BLACK = (0, 0, 0)
WHITE = (245, 245, 247)
GRAY = (134, 134, 139)        # gris de subtítulo


def px(v):
    """Unidades de maqueta -> píxeles de salida."""
    return round(v * SCALE)


# ── Fuentes ──────────────────────────────────────────────────────────────────

def inter(weight: str, size: int) -> ImageFont.FreeTypeFont:
    d = CACHE.parent / "fonts"
    f = d / f"InterDisplay-{weight}.ttf"
    if not f.exists():
        d.mkdir(parents=True, exist_ok=True)
        print("Descargando Inter (SIL OFL)…")
        data = urllib.request.urlopen(INTER_URL, timeout=60).read()
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for n in z.namelist():
                if n.startswith("extras/ttf/InterDisplay-") and n.endswith(".ttf"):
                    (d / Path(n).name).write_bytes(z.read(n))
    return ImageFont.truetype(str(f), px(size))


def mono(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(MONO, px(size))


# ── Captura de terminal ──────────────────────────────────────────────────────

def real_ttfx() -> str:
    for d in os.environ.get("PATH", "").split(":"):
        c = Path(d) / "ttfx"
        if c.is_file() and os.access(c, os.X_OK) and not str(c.resolve()).startswith(str(ROOT)):
            # saltar el envoltorio del repo aunque esté enlazado en ~/.local/bin
            if "omarchy-screensaver-fx" not in str(c.resolve()):
                return str(c)
    sys.exit("No se encuentra ttfx")


SYNC_BEGIN, SYNC_END = b"\x1b[?2026h", b"\x1b[?2026l"


def capture(name: str, cmd: list[str], seconds: float, env: dict | None = None):
    """Ejecuta cmd en un pty COLSxROWS y guarda una instantánea por fotograma."""
    out = CACHE / f"{name}.pkl"
    if out.exists():
        return pickle.loads(out.read_bytes())
    print(f"  capturando {name} ({seconds:.1f}s)…")
    screen = pyte.Screen(COLS, ROWS)
    stream = pyte.ByteStream(screen)
    pid, fd = pty.fork()
    if pid == 0:
        fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack("HHHH", ROWS, COLS, 0, 0))
        e = dict(os.environ, TERM="xterm-256color", COLUMNS=str(COLS), LINES=str(ROWS))
        e.update(env or {})
        os.execvpe(cmd[0], cmd, e)
    screen.write_process_input = lambda data: os.write(fd, data.encode())
    frames, t0, n, pending = [], time.monotonic(), 0, b""
    alive = True
    while n < seconds * FPS:
        deadline = t0 + (n + 1) / FPS
        while alive and (wait := deadline - time.monotonic()) > 0:
            r, _, _ = select.select([fd], [], [], wait)
            if r:
                try:
                    data = os.read(fd, 65536)
                except OSError:
                    data = b""
                if not data:
                    alive = False
                    break
                pending += data
                # Con synchronized output (?2026) solo se pintan fotogramas completos.
                end = pending.rfind(SYNC_END)
                if end >= 0:
                    stream.feed(pending[:end + len(SYNC_END)])
                    pending = pending[end + len(SYNC_END):]
                if SYNC_BEGIN not in pending:
                    stream.feed(pending)
                    pending = b""
        if not alive:
            time.sleep(max(0, deadline - time.monotonic()))
        frames.append(snapshot(screen))
        n += 1
    os.close(fd)  # sin lector, ttfx no puede quedarse bloqueado escribiendo
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            break
        for _ in range(20):
            if os.waitpid(pid, os.WNOHANG)[0]:
                break
            time.sleep(0.05)
        else:
            continue
        break
    CACHE.mkdir(parents=True, exist_ok=True)
    out.write_bytes(pickle.dumps(frames))
    return frames


def color(c, default):
    if c in (None, "default"):
        return default
    if isinstance(c, str) and len(c) == 6:
        try:
            return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            pass
    named = {"black": (0, 0, 0), "red": (205, 49, 49), "green": (13, 188, 121),
             "brown": (229, 229, 16), "yellow": (229, 229, 16), "blue": (36, 114, 200),
             "magenta": (188, 63, 188), "cyan": (17, 168, 205), "white": (229, 229, 229)}
    return named.get(c, default)


def snapshot(screen):
    cells = []
    for y in range(ROWS):
        row = screen.buffer[y]
        for x in range(COLS):
            ch = row[x]
            bg = color(ch.bg, None)
            if ch.data not in (" ", "") or bg not in (None, BLACK):
                fg = color(ch.fg, (229, 229, 229))
                if ch.reverse:
                    fg, bg = (bg or BLACK), fg
                cells.append((x, y, ch.data, fg, bg))
    return cells


# ── Dibujo de la terminal ────────────────────────────────────────────────────

_glyphs: dict = {}


def glyph(ch: str, cw: int, chh: int) -> Image.Image:
    key = (ch, cw, chh)
    if key not in _glyphs:
        f = ImageFont.truetype(MONO, int(chh * 0.62))
        m = Image.new("L", (cw, chh), 0)
        ImageDraw.Draw(m).text((cw / 2, chh / 2), ch, font=f, fill=255, anchor="mm")
        _glyphs[key] = m
    return _glyphs[key]


SHADE = {"░": 0.25, "▒": 0.5, "▓": 0.75}


def render_term(cells, cw: int = CW, chh: int = CH) -> Image.Image:
    """Pinta la terminal con celdas de cw x chh px (sin reescalar después)."""
    im = Image.new("RGB", (COLS * cw, ROWS * chh), BLACK)
    d = ImageDraw.Draw(im)
    for x, y, ch, fg, bg in cells:
        px, py = x * cw, y * chh
        if bg and bg != BLACK:
            d.rectangle([px, py, px + cw - 1, py + chh - 1], fill=bg)
        if ch == "█":
            d.rectangle([px, py, px + cw - 1, py + chh - 1], fill=fg)
        elif ch == "▀":
            d.rectangle([px, py, px + cw - 1, py + chh // 2 - 1], fill=fg)
        elif ch == "▄":
            d.rectangle([px, py + chh // 2, px + cw - 1, py + chh - 1], fill=fg)
        elif ch == "▌":
            d.rectangle([px, py, px + cw // 2 - 1, py + chh - 1], fill=fg)
        elif ch == "▐":
            d.rectangle([px + cw // 2, py, px + cw - 1, py + chh - 1], fill=fg)
        elif ch in SHADE:
            k = SHADE[ch]
            base = bg or BLACK
            d.rectangle([px, py, px + cw - 1, py + chh - 1],
                        fill=tuple(round(base[i] + (fg[i] - base[i]) * k) for i in range(3)))
        elif ch.strip():
            im.paste(fg, (px, py), glyph(ch, cw, chh))
    return im


# ── Composición ──────────────────────────────────────────────────────────────

def ease(t):  # ease-out cúbica
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def text_in(canvas, xy, s, font, fill, t, delay=0.0, dur=0.7, anchor="mm", rise=24):
    """Texto que aparece subiendo y fundiéndose (estilo keynote)."""
    k = ease((t - delay) / dur)
    if k <= 0:
        return
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((xy[0] * SCALE, (xy[1] + rise * (1 - k)) * SCALE), s, font=font,
                               fill=fill + (round(255 * k),), anchor=anchor)
    canvas.alpha_composite(layer)


_masks: dict = {}


def rounded_mask(size, r):
    key = (size, r)
    if key not in _masks:
        m = Image.new("L", (size[0] * 2, size[1] * 2), 0)
        ImageDraw.Draw(m).rounded_rectangle([0, 0, m.width - 1, m.height - 1], r * 2, fill=255)
        _masks[key] = m.resize(size, Image.LANCZOS)
    return _masks[key]


_glows: dict = {}


def glow(size, rgb, strength=0.55):
    """Halo de color bajo la pantalla, precalculado una vez por escena."""
    key = (size, rgb, strength)
    if key not in _glows:
        w, h = size
        m = px(200)
        g = Image.new("RGBA", (w + 2 * m, h + 2 * m), (0, 0, 0, 0))
        ImageDraw.Draw(g).rounded_rectangle([m, px(260), w + m, h + m], px(60),
                                            fill=rgb + (round(255 * strength),))
        _glows[key] = g.filter(ImageFilter.GaussianBlur(px(110)))
    return _glows[key]


def panel(canvas, term, box, k=1.0, tint=(90, 110, 255)):
    """Pega la terminal como una pantalla con esquinas redondeadas, borde y halo.

    term son las celdas de un fotograma: se pintan ya al tamaño de la pantalla, sin
    reescalar, para que los bloques queden nítidos. box va en unidades de maqueta.
    """
    bx, by, bw, bh = (v * SCALE for v in box)
    img = render_term(term, max(1, int(bw // COLS)), max(1, int(bh // ROWS))).convert("RGBA")
    w, h = img.size
    x = round(bx + (bw - w) / 2)
    y = round(by + (bh - h) / 2 + px(40) * (1 - k))
    g = glow((w, h), tint)
    if k < 1:
        g = g.copy()
        g.putalpha(g.getchannel("A").point(lambda a: round(a * k)))
    canvas.alpha_composite(g, (x - px(200), y - px(200)))
    r = max(px(12), w // 55)
    mask = rounded_mask((w, h), r)
    if k < 1:
        mask = mask.point(lambda a: round(a * k))
    canvas.paste(img, (x, y), mask)
    border = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(border).rounded_rectangle([0, 0, w - 1, h - 1], r,
                                             outline=(255, 255, 255, round(34 * k)), width=max(1, px(2)))
    canvas.alpha_composite(border, (x, y))


class Draw:
    """ImageDraw en unidades de maqueta: escala posiciones, radios y grosores."""

    def __init__(self, canvas):
        self.d = ImageDraw.Draw(canvas)

    @staticmethod
    def _xy(xy):
        if isinstance(xy[0], (tuple, list)):
            return [(a * SCALE, b * SCALE) for a, b in xy]
        return [v * SCALE for v in xy]

    def textlength(self, s, font):
        return self.d.textlength(s, font=font) / SCALE

    def ellipse(self, xy, **kw):
        self.d.ellipse(self._xy(xy), **kw)

    def line(self, xy, width=1, **kw):
        self.d.line(self._xy(xy), width=max(1, px(width)), **kw)

    def rounded_rectangle(self, xy, r, width=1, **kw):
        self.d.rounded_rectangle(self._xy(xy), px(r), width=max(1, px(width)), **kw)

    def text(self, xy, s, **kw):
        self.d.text(tuple(self._xy(xy)), s, **kw)


def paste_logo(canvas, logo, y, k):
    """Logotipo centrado en horizontal, con su fundido; y en unidades de maqueta."""
    lg = logo.copy()
    lg.putalpha(lg.getchannel("A").point(lambda a: round(a * k)))
    canvas.alpha_composite(lg, (round(canvas.width / 2 - lg.width / 2), px(y + 10 * (1 - k))))


def frame_at(frames, t):
    return frames[min(len(frames) - 1, max(0, int(t * FPS)))]


# ── Guion ────────────────────────────────────────────────────────────────────

TEXT = {
    "en": {
        "title": "Screensaver FX", "for": "for Omarchy",
        "keep_h": "Every effect you already love.",
        "keep_s": "All of Omarchy’s ttfx effects stay in the rotation.",
        "plus": "Plus six new ones.",
        "neon": ("Neon", "Lights up like a sign."),
        "starfield": ("Starfield", "Warp in from deep space."),
        "terminal": ("Terminal", "It knows who you are."),
        "glitch": ("Glitch", "A little interference. On purpose."),
        "plasma": ("Plasma", "Color that flows through every letter."),
        "clock": ("Clock", "The time, at a glance."),
        "theme_h": "In your theme’s colors.",
        "theme_s": "Switch themes. It follows.",
        "upd_h": "Built to outlast updates.",
        "upd": ["Nothing from Omarchy is copied or edited.",
                "It checks itself after every omarchy update.",
                "If something changes, it falls back — and tells you."],
        "out_s": "Free and open source. Installs in seconds.",
    },
    "es": {
        "title": "Screensaver FX", "for": "para Omarchy",
        "keep_h": "Todos los efectos que ya te gustan.",
        "keep_s": "Los efectos ttfx de Omarchy siguen en la rotación.",
        "plus": "Y seis nuevos.",
        "neon": ("Neón", "Se enciende como un letrero."),
        "starfield": ("Estrellas", "Llega desde el espacio profundo."),
        "terminal": ("Terminal", "Sabe quién eres."),
        "glitch": ("Glitch", "Un poco de interferencia. A propósito."),
        "plasma": ("Plasma", "Color que fluye por cada letra."),
        "clock": ("Reloj", "La hora, de un vistazo."),
        "theme_h": "Con los colores de tu tema.",
        "theme_s": "Cambias de tema. Te sigue.",
        "upd_h": "Hecho para sobrevivir a las actualizaciones.",
        "upd": ["No copia ni modifica nada de Omarchy.",
                "Se revisa solo tras cada omarchy update.",
                "Si algo cambia, vuelve al original y te avisa."],
        "out_s": "Libre y de código abierto. Se instala en segundos.",
    },
}
INSTALL = ["git clone https://github.com/thealejandro/omarchy-screensaver-fx",
           "./omarchy-screensaver-fx/install.sh"]
OWN = ["neon", "starfield", "terminal", "glitch", "plasma", "clock"]
THEMES = ["tokyo-night", "rose-pine", "everforest"]
# (efecto, segundo de inicio en la captura, velocidad) para la escena de efectos originales
TTFX_KEEP = [("slide", 0.6, 1.2), ("rain", 2.6, 1.7), ("burn", 1.0, 1.4)]
TTFX_THEMED = "middleout"


def theme_file(slug):
    for d in THEMES_DIRS:
        f = d / slug / "colors.toml"
        if f.exists():
            return f
    sys.exit(f"No encuentro el tema {slug}")


def palette(slug):
    out = subprocess.run([sys.executable, "-I", str(FX), "--palette"], capture_output=True,
                         text=True, env=dict(os.environ, SCREENSAVER_FX_THEME=str(theme_file(slug))))
    return out.stdout.split()


def accent(slug):
    p = palette(slug)[0]
    return tuple(int(p[i:i + 2], 16) for i in (0, 2, 4))


_logo = {}


def brand_logo(height):
    """Logotipo de thealejandro (docs/marca, versión para fondo oscuro)."""
    height = px(height)
    if height not in _logo:
        svg = DOCS / "marca/logotipo.svg"
        try:
            png = subprocess.run(["rsvg-convert", "-h", str(height * 2), str(svg)],
                                 capture_output=True, check=True).stdout
            im = Image.open(io.BytesIO(png)).convert("RGBA")
            _logo[height] = im.resize((round(im.width / 2), height), Image.LANCZOS)
        except (OSError, subprocess.CalledProcessError):
            _logo[height] = None
    return _logo[height]


def ttfx_cmd(effect, stops=None):
    cmd = [real_ttfx(), "-i", str(ART), "--frame-rate", "60", "--canvas-width", "0",
           "--canvas-height", "0", "--anchor-canvas", "c", "--anchor-text", "c",
           "--no-eol", "--no-restore-cursor", effect]
    if stops:
        cmd += ["--final-gradient-stops", *stops, "--final-gradient-direction", "diagonal"]
    return cmd


def fx_frames(name, seconds, dur, env):
    """Capturas de una animación propia por idioma. Solo el reloj cambia (la fecha va en el idioma)."""
    def run(tag, e):
        return capture(f"fx-{tag}", [sys.executable, "-I", str(FX), name, "--seconds", str(seconds)], dur, e)
    if name != "clock":
        fr = run(name, env)
        return {"en": fr, "es": fr}
    return {L: run(f"{name}-{L}", {**env, "SCREENSAVER_FX_LANG": L}) for L in ("en", "es")}


def build_scenes(quick=False):
    """Devuelve [(duración, función(canvas, t, lang))]."""
    main_theme = THEMES[0]
    env_theme = {"SCREENSAVER_FX_THEME": str(theme_file(main_theme)), "SCREENSAVER_FX_SEED": "7"}
    tint = accent(main_theme)
    fx_len = 2.5 if quick else 4.6
    scenes = []

    # 1. Título
    def intro(c, t, L):
        T = TEXT[L]
        text_in(c, (W / 2, H / 2 - 30), T["title"], inter("Bold", 132), WHITE, t, 0.2, 0.9)
        text_in(c, (W / 2, H / 2 + 80), T["for"], inter("Medium", 46), GRAY, t, 0.8, 0.8)
    scenes.append((3.4, intro))

    # 2. Efectos originales
    keep = [(capture(f"ttfx-{e}", ttfx_cmd(e), 6.5), e, t0, v) for e, t0, v in TTFX_KEEP]
    clip = 6.0 / len(keep)

    def keep_scene(c, t, L):
        T = TEXT[L]
        text_in(c, (W / 2, 118), T["keep_h"], inter("Bold", 72), WHITE, t, 0.0)
        text_in(c, (W / 2, 196), T["keep_s"], inter("Regular", 34), GRAY, t, 0.25)
        i = min(len(keep) - 1, int(t / clip))
        fr, name, t0, v = keep[i]
        panel(c, frame_at(fr, t0 + (t - i * clip) * v), (360, 268, 1200, 720), ease(t / 0.8), (120, 120, 140))
        text_in(c, (W / 2, 1030), f"ttfx · {name}", mono(26), GRAY, t, i * clip + 0.1, 0.4, rise=8)
    scenes.append((6.0, keep_scene))

    # 3. Interludio
    def plus(c, t, L):
        text_in(c, (W / 2, H / 2), TEXT[L]["plus"], inter("Bold", 110), WHITE, t, 0.1, 0.8)
    scenes.append((2.0, plus))

    # 4. Animaciones propias
    for name in OWN:
        fr = fx_frames(name, fx_len + 1, fx_len + 0.6, env_theme)

        def own(c, t, L, fr=fr, name=name):
            fr = fr[L]
            label, line = TEXT[L][name]
            text_in(c, (W / 2, 104), label.upper(), inter("SemiBold", 30), tint, t, 0.0, 0.6, rise=12)
            text_in(c, (W / 2, 170), line, inter("Bold", 72), WHITE, t, 0.12)
            panel(c, frame_at(fr, t), (400, 262, 1120, 672), ease(t / 0.7), tint)
        scenes.append((fx_len, own))

    # 5. Colores del tema: tríptico
    tri = [capture(f"ttfx-{TTFX_THEMED}-{s}", ttfx_cmd(TTFX_THEMED, palette(s)), 6.4) for s in THEMES]
    tints = [accent(s) for s in THEMES]

    def themed(c, t, L):
        T = TEXT[L]
        text_in(c, (W / 2, 150), T["theme_h"], inter("Bold", 80), WHITE, t, 0.0)
        text_in(c, (W / 2, 232), T["theme_s"], inter("Regular", 36), GRAY, t, 0.25)
        pw, ph, gap = 560, 336, 40
        x0 = (W - (pw * 3 + gap * 2)) // 2
        for i, (fr, slug) in enumerate(zip(tri, THEMES)):
            k = ease((t - 0.25 - i * 0.15) / 0.7)
            if k <= 0:
                continue
            x = x0 + i * (pw + gap)
            panel(c, frame_at(fr, t - 0.3), (x, 360, pw, ph), k, tints[i])
            text_in(c, (x + pw / 2, 760), slug, inter("Medium", 30), GRAY, t, 0.6 + i * 0.15, 0.6, rise=10)
            dots = palette(slug) if not hasattr(themed, slug) else getattr(themed, slug)
            setattr(themed, slug, dots)
            for j, hx in enumerate(dots[:4]):
                rgb = tuple(int(hx[a:a + 2], 16) for a in (0, 2, 4))
                cx = x + pw / 2 - 45 + j * 30
                ka = ease((t - 0.8 - i * 0.15 - j * 0.05) / 0.4)
                if ka > 0:
                    Draw(c).ellipse([cx - 9, 808 - 9, cx + 9, 808 + 9], fill=rgb + (round(255 * ka),))
    scenes.append((6.2, themed))

    # 6. Actualizaciones
    def updates(c, t, L):
        T = TEXT[L]
        text_in(c, (W / 2, 330), T["upd_h"], inter("Bold", 80), WHITE, t, 0.0)
        for i, line in enumerate(T["upd"]):
            y = 500 + i * 92
            k = ease((t - 0.5 - i * 0.35) / 0.6)
            if k <= 0:
                continue
            fnt = inter("Medium", 40)
            tw = Draw(c).textlength(line, font=fnt)
            x = W / 2 - tw / 2 + 28
            Draw(c).ellipse([x - 64, y - 18, x - 28, y + 18], fill=tint + (round(255 * k),))
            Draw(c).line([(x - 55, y), (x - 48, y + 8), (x - 36, y - 8)], fill=(0, 0, 0, round(255 * k)), width=4)
            text_in(c, (x, y), line, fnt, WHITE, t, 0.5 + i * 0.35, 0.6, anchor="lm", rise=14)
    scenes.append((5.4, updates))

    # 7. Cierre
    def outro(c, t, L):
        T = TEXT[L]
        text_in(c, (W / 2, 360), T["title"], inter("Bold", 112), WHITE, t, 0.0, 0.8)
        text_in(c, (W / 2, 452), T["out_s"], inter("Regular", 38), GRAY, t, 0.3)
        k = ease((t - 0.8) / 0.7)
        if k > 0:
            fm = mono(28)
            d = Draw(c)
            tw = max(d.textlength(line, font=fm) for line in INSTALL)
            bx, by = W / 2 - tw / 2 - 40, 548 + 16 * (1 - k)
            d.rounded_rectangle([bx, by, bx + tw + 80, by + 128], 24, fill=(28, 28, 30, round(255 * k)),
                                outline=(255, 255, 255, round(28 * k)), width=2)
            for j, line in enumerate(INSTALL):
                d.text((bx + 40, by + 44 + j * 42), line, font=fm, fill=WHITE + (round(255 * k),), anchor="lm")
        text_in(c, (W / 2, 760), "github.com/thealejandro/omarchy-screensaver-fx", inter("Medium", 32), tint, t, 1.3)
        text_in(c, (W / 2, 812), "thealejandro.dev/omarchy/screensaver", inter("Regular", 30), GRAY, t, 1.5)
        k = ease((t - 1.9) / 0.7)
        if k > 0 and (logo := brand_logo(34)):
            paste_logo(c, logo, 940, k)
    scenes.append((5.6, outro))
    return scenes


def render(lang, scenes, out_mp4, fade=0.35):
    total = sum(sc[0] for sc in scenes)
    size = (px(W), px(H))
    print(f"Renderizando {lang}: {size[0]}x{size[1]}, {total:.1f}s, {round(total * FPS)} fotogramas")
    ff = subprocess.Popen([
        "ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{size[0]}x{size[1]}",
        "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", "18",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out_mp4)], stdin=subprocess.PIPE)
    n = 0
    for dur, fn, *opt in scenes:
        fd = opt[0] if opt else fade  # fundido propio de la escena (0 = corte seco)
        for i in range(round(dur * FPS)):
            t = i / FPS
            c = Image.new("RGBA", size, BLACK + (255,))
            fn(c, t, lang)
            k = min(1.0, t / fd, (dur - t) / fd) if fd else 1.0
            img = c.convert("RGB")
            if k < 1:
                img = ImageChops.multiply(img, Image.new("RGB", size, (round(255 * k),) * 3))
            ff.stdin.write(img.tobytes())
            n += 1
            if n % 150 == 0:
                print(f"  {n} fotogramas")
    ff.stdin.close()
    ff.wait()
    return total


def encode_extras(lang, mp4, scenes):
    webm = DOCS / f"demo-{lang}.webm"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(mp4), "-c:v", "libvpx-vp9", "-b:v", "0",
                    "-crf", "30", "-row-mt", "1", "-deadline", "good", "-cpu-used", "2", str(webm)], check=True)
    # Póster: el tríptico de temas a mitad de escena
    starts, acc = [], 0.0
    for d, _ in scenes:
        starts.append(acc)
        acc += d
    poster_t = starts[-3] + 4.0
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{poster_t:.2f}", "-i", str(mp4),
                    "-frames:v", "1", "-c:v", "libwebp", "-quality", "82", str(DOCS / f"demo-poster-{lang}.webp")], check=True)
    return starts


def make_gif(mp4, starts, scenes):
    """GIF corto para el README: animaciones propias + tríptico de temas."""
    segs = []
    for i in range(3, 3 + len(OWN)):
        segs.append((starts[i] + 0.5, 2.6))
    segs.append((starts[3 + len(OWN)] + 1.2, 3.6))
    parts = "".join(f"[0:v]trim={s:.2f}:{s + d:.2f},setpts=PTS-STARTPTS[v{i}];" for i, (s, d) in enumerate(segs))
    concat = "".join(f"[v{i}]" for i in range(len(segs))) + f"concat=n={len(segs)}:v=1:a=0,"
    vf = (parts + concat + "fps=12,scale=800:-1:flags=lanczos,split[a][b];"
          "[a]palettegen=max_colors=128:stats_mode=diff[p];[b][p]paletteuse=dither=sierra2_4a:diff_mode=rectangle")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(mp4), "-filter_complex", vf,
                    str(DOCS / "demo.gif")], check=True)


def shots():
    d = DOCS / "shots"
    d.mkdir(parents=True, exist_ok=True)
    when = {"neon": 3.6, "starfield": 4.2, "terminal": 3.4, "glitch": 2.0, "plasma": 3.0, "clock": 3.0}
    for name in OWN:
        fr = pickle.loads((CACHE / f"fx-{name}{'-en' if name == 'clock' else ''}.pkl").read_bytes())
        f = max(fr, key=len) if name == "glitch" else frame_at(fr, when[name])  # en plena ráfaga
        render_term(f).save(d / f"{name}.png", optimize=True)  # 1500x900, nítida en pantallas HiDPI


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default="all", choices=["en", "es", "all"])
    ap.add_argument("--quick", action="store_true", help="escenas cortas para probar")
    ap.add_argument("--fresh", action="store_true", help="repetir las capturas")
    a = ap.parse_args()
    if not ART.exists():
        sys.exit(f"Falta {ART}")
    if a.fresh and CACHE.exists():
        shutil.rmtree(CACHE)
    DOCS.mkdir(exist_ok=True)
    scenes = build_scenes(a.quick)
    for lang in (["en", "es"] if a.lang == "all" else [a.lang]):
        mp4 = DOCS / f"demo-{lang}.mp4"
        render(lang, scenes, mp4)
        starts = encode_extras(lang, mp4, scenes)
        if lang == "en":
            make_gif(mp4, starts, scenes)
    shots()
    print("Listo:", ", ".join(sorted(p.name for p in DOCS.iterdir())))


if __name__ == "__main__":
    main()
