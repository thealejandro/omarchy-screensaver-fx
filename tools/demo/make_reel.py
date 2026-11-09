#!/usr/bin/env python3
"""Vídeo vertical (1080x1920) para reels, historias y estados.

Reutiliza las capturas y el dibujo de make_demo.py. Deja el contenido dentro
de la zona segura que no tapan los botones de Instagram, Facebook y WhatsApp
(unos 250 px arriba y 320 px abajo) y lleva una pista de audio en silencio
para poder añadir música desde la propia app.

Uso (desde la raíz del repo):
    uv run --with pyte --with pillow tools/demo/make_reel.py [--lang en|es|all] [--out DIR]

Salida: reel-<lang>.mp4 y reel-cover-<lang>.jpg en DIR (por defecto docs/social).
"""

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import make_demo as m  # noqa: E402

m.W, m.H = W, H = 1080, 1920
m.SCALE = 1                       # 1080x1920 es el máximo de reels e historias
FPS = m.FPS
WHITE, GRAY = m.WHITE, m.GRAY

TEXT = {
    "en": {
        "hook": "Your screensaver,\nbut alive.", "title": "Screensaver FX", "for": "for Omarchy",
        "keep": "Every Omarchy effect.", "plus": "Plus six new ones.",
        "theme": "In your theme’s colors.", "free": "Free and open source.",
        "names": {"neon": "Neon", "starfield": "Starfield", "terminal": "Terminal",
                  "glitch": "Glitch", "plasma": "Plasma", "clock": "Clock"},
    },
    "es": {
        "hook": "Tu salvapantallas,\npero vivo.", "title": "Screensaver FX", "for": "para Omarchy",
        "keep": "Todos los efectos de Omarchy.", "plus": "Y seis nuevos.",
        "theme": "Con los colores de tu tema.", "free": "Libre y de código abierto.",
        "names": {"neon": "Neón", "starfield": "Estrellas", "terminal": "Terminal",
                  "glitch": "Glitch", "plasma": "Plasma", "clock": "Reloj"},
    },
}
PANEL = (60, 640, 960, 576)       # x, y, ancho, alto (5:3, como la terminal)


def multiline_in(c, xy, s, font, fill, t, delay=0.0, gap=1.15):
    lines = s.split("\n")
    size = font.size / m.SCALE * gap
    y0 = xy[1] - size * (len(lines) - 1) / 2
    for i, line in enumerate(lines):
        m.text_in(c, (xy[0], y0 + i * size), line, font, fill, t, delay + i * 0.12)


def chip(c, xy, s, rgb, k):
    """Etiqueta redondeada con el nombre de la animación."""
    if k <= 0:
        return
    f = m.inter("SemiBold", 34)
    d = m.Draw(c)
    tw = d.textlength(s, font=f)
    x, y = xy[0] - tw / 2 - 28, xy[1] - 30 + 10 * (1 - k)
    d.rounded_rectangle([x, y, x + tw + 56, y + 60], 30, fill=rgb + (round(56 * k),),
                        outline=rgb + (round(150 * k),), width=2)
    d.text((xy[0], y + 30), s, font=f, fill=WHITE + (round(255 * k),), anchor="mm")


def build(quick=False):
    main_theme = m.THEMES[0]
    env = {"SCREENSAVER_FX_THEME": str(m.theme_file(main_theme)), "SCREENSAVER_FX_SEED": "7"}
    tint = m.accent(main_theme)
    fx = {n: m.fx_frames(n, 5.6, 5.2, env) for n in m.OWN}
    keep = [(m.capture(f"ttfx-{e}", m.ttfx_cmd(e), 6.5), e, t0, v) for e, t0, v in m.TTFX_KEEP]
    tri = [m.capture(f"ttfx-{m.TTFX_THEMED}-{s}", m.ttfx_cmd(m.TTFX_THEMED, m.palette(s)), 6.4)
           for s in m.THEMES]
    tints = [m.accent(s) for s in m.THEMES]
    scenes = []

    # 1. Gancho: el plasma ya en marcha desde el primer fotograma
    def hook(c, t, L):
        T = TEXT[L]
        multiline_in(c, (W / 2, 400), T["hook"], m.inter("Bold", 92), WHITE, t, 0.0)
        m.panel(c, m.frame_at(fx["plasma"][L], 1.6 + t), PANEL, 1.0, tint)
        m.text_in(c, (W / 2, 1360), T["title"], m.inter("Bold", 64), WHITE, t, 0.7)
        m.text_in(c, (W / 2, 1430), T["for"], m.inter("Medium", 36), GRAY, t, 0.9)
    scenes.append((3.0, hook))

    # 2. Tres efectos de ttfx, medio segundo largo cada uno
    clip = 1.5

    def keep_scene(c, t, L):
        m.text_in(c, (W / 2, 420), TEXT[L]["keep"], m.inter("Bold", 64), WHITE, t, 0.0)
        i = min(len(keep) - 1, int(t / clip))
        fr, name, t0, v = keep[i]
        m.panel(c, m.frame_at(fr, t0 + 0.8 + (t - i * clip) * v * 1.4), PANEL, 1.0, (120, 120, 140))
        m.text_in(c, (W / 2, 1290), f"ttfx · {name}", m.mono(32), GRAY, t,
                  i * clip + 0.05, 0.3, rise=6)
    scenes.append((clip * len(keep), keep_scene, 0))

    # 3. Las seis propias, con el titular fijo
    per = 1.6 if quick else 2.4
    for j, name in enumerate(m.OWN):
        start = {"neon": 1.6, "starfield": 2.0, "terminal": 1.4, "glitch": 2.4, "plasma": 2.2, "clock": 1.6}[name]

        def own(c, t, L, name=name, start=start, j=j):
            T = TEXT[L]
            m.text_in(c, (W / 2, 420), T["plus"], m.inter("Bold", 72), WHITE, t, 0.0 if j == 0 else -1)
            m.panel(c, m.frame_at(fx[name][L], start + t), PANEL, 1.0, tint)
            chip(c, (W / 2, 1320), T["names"][name], tint, m.ease(t / 0.35))
            # puntos de progreso
            d = m.Draw(c)
            for k in range(len(m.OWN)):
                cx = W / 2 + (k - (len(m.OWN) - 1) / 2) * 30
                on = k == j
                d.ellipse([cx - 6, 1440 - 6, cx + 6, 1440 + 6],
                          fill=(tint if on else (70, 70, 74)) + (255,))
        scenes.append((per, own, 0))

    # 4. Temas, apilados
    def themed(c, t, L):
        m.text_in(c, (W / 2, 340), TEXT[L]["theme"], m.inter("Bold", 68), WHITE, t, 0.0)
        pw, ph = 600, 360
        for i, (fr, slug) in enumerate(zip(tri, m.THEMES)):
            k = m.ease((t - 0.15 - i * 0.18) / 0.6)
            if k <= 0:
                continue
            y = 450 + i * 400
            m.panel(c, m.frame_at(fr, 1.0 + t * 1.3), (90, y, pw, ph), k, tints[i])
            m.text_in(c, (720, y + ph / 2 - 24), slug, m.inter("SemiBold", 38), WHITE, t, 0.4 + i * 0.18,
                      0.5, anchor="lm", rise=8)
            d = m.Draw(c)
            for jj, hx in enumerate(m.palette(slug)[:4] if not hasattr(themed, slug) else getattr(themed, slug)):
                rgb = tuple(int(hx[a:a + 2], 16) for a in (0, 2, 4))
                cx, cy = 734 + jj * 40, y + ph / 2 + 34
                d.ellipse([cx - 13, cy - 13, cx + 13, cy + 13], fill=rgb + (round(255 * k),))
            if not hasattr(themed, slug):
                setattr(themed, slug, m.palette(slug)[:4])
    scenes.append((4.6, themed))

    # 5. Cierre
    def outro(c, t, L):
        T = TEXT[L]
        m.text_in(c, (W / 2, 640), T["title"], m.inter("Bold", 104), WHITE, t, 0.0, 0.8)
        m.text_in(c, (W / 2, 740), T["for"], m.inter("Medium", 44), GRAY, t, 0.2)
        m.text_in(c, (W / 2, 900), T["free"], m.inter("Regular", 40), WHITE, t, 0.5)
        m.text_in(c, (W / 2, 1010), "github.com/thealejandro", m.inter("Medium", 38), tint, t, 0.8)
        m.text_in(c, (W / 2, 1060), "omarchy-screensaver-fx", m.inter("Medium", 38), tint, t, 0.85)
        m.text_in(c, (W / 2, 1150), "thealejandro.dev/omarchy/screensaver", m.inter("Regular", 34), GRAY, t, 1.1)
        k = m.ease((t - 1.4) / 0.7)
        if k > 0 and (logo := m.brand_logo(46)):
            m.paste_logo(c, logo, 1380, k)
    scenes.append((4.4, outro))
    return scenes


def encode(lang, scenes, out):
    silent = out.with_suffix(".video.mp4")
    m.render(lang, scenes, silent, fade=0.2)
    # Pista de audio en silencio: algunas apps tratan mal los vídeos sin audio.
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(silent), "-f", "lavfi", "-i",
                    "anullsrc=channel_layout=stereo:sample_rate=48000", "-shortest", "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(out)], check=True)
    silent.unlink()
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "2.2", "-i", str(out), "-frames:v", "1",
                    "-q:v", "2", str(out.with_name(f"reel-cover-{lang}.jpg"))], check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default="all", choices=["en", "es", "all"])
    ap.add_argument("--out", type=Path, default=m.DOCS / "social")
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    scenes = build(a.quick)
    for lang in (["es", "en"] if a.lang == "all" else [a.lang]):
        encode(lang, scenes, a.out / f"reel-{lang}.mp4")
    print("Listo:", ", ".join(sorted(p.name for p in a.out.iterdir())))


if __name__ == "__main__":
    main()
