"""Toolbar icons drawn as inline SVG (no external image files needed)."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

FG = "#e3e6ec"
ACCENT = "#4aa3ff"
RED = "#ff6b5e"
GREEN = "#5fd38a"

_HEAD = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
         f'stroke="{FG}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">')

_ICONS = {
    "open": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v1H7.5a2 2 0 0 0-1.9 1.4L3.5 18"/>'
            '<path d="M3.5 18 6 11.5h15.5L19 18.2a1.5 1.5 0 0 1-1.4.8H4.6a1.2 1.2 0 0 1-1.1-1Z"/>',
    "save": '<path d="M5 3h11l4 4v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a1 1 0 0 1 1-1Z"/>'
            '<path d="M8 3v5h7V3"/><rect x="7.5" y="13" width="9" height="6" rx="1"/>',
    "undo": '<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/>',
    "fit": '<path d="M4 9V5a1 1 0 0 1 1-1h4M15 4h4a1 1 0 0 1 1 1v4M20 15v4a1 1 0 0 1-1 1h-4M9 20H5a1 1 0 0 1-1-1v-4"/>'
           f'<rect x="8.5" y="8.5" width="7" height="7" rx="1" stroke="{ACCENT}"/>',
    "cut": '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/>'
           '<path d="M8.2 8.2 20 19M8.2 15.8 20 5M13.5 12h0"/>',
    "align": f'<rect x="3" y="9" width="10" height="10" rx="1.5" stroke="{ACCENT}"/>'
             f'<rect x="11" y="3" width="10" height="10" rx="1.5" stroke="{GREEN}" stroke-dasharray="2.5 2"/>'
             '<path d="M17 15v4.5M14.8 17.3 17 19.5l2.2-2.2"/>',
    "merge": f'<circle cx="9" cy="12" r="6" stroke="{ACCENT}"/><circle cx="15" cy="12" r="6" stroke="{GREEN}"/>'
             '<path d="M12 7.2a6 6 0 0 1 0 9.6a6 6 0 0 1 0-9.6Z" fill="#e3e6ec" fill-opacity="0.55" stroke="none"/>',
    "edges": '<path d="M3 20 12 4l9 16Z"/><path d="M7.5 12h9M12 20l-4.5-8M12 20l4.5-8"/>',
    "section": f'<path d="M4 15c0-5 3.5-9 8-9s8 4 8 9" />'
               f'<path d="M6.5 15c0-3.6 2.4-6.5 5.5-6.5s5.5 2.9 5.5 6.5" stroke="{ACCENT}"/>'
               f'<path d="M12 2.5v19" stroke="{GREEN}" stroke-dasharray="2 1.6"/>'
               '<path d="M3 19.5h18M3 18v3M21 18v3"/>',
    "eye": '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z"/><circle cx="12" cy="12" r="3"/>',
    "eye_off": '<path d="M3 3l18 18M10.6 6.1A9.6 9.6 0 0 1 12 6c6 0 9.5 6 9.5 6a17 17 0 0 1-2.9 3.6M6.4 7.4A16.5 16.5 0 0 0 2.5 12s3.5 6 9.5 6a9 9 0 0 0 4.6-1.3M9.9 9.9a3 3 0 0 0 4.2 4.2"/>',
    "scan_colors": f'<path d="M12 3 4 7.5v9L12 21l8-4.5v-9Z"/><path d="M12 12 4 7.5M12 12l8-4.5M12 12v9"/>'
                   f'<path d="M12 3 4 7.5 12 12Z" fill="{RED}" fill-opacity="0.8" stroke="none"/>'
                   f'<path d="M12 3l8 4.5L12 12Z" fill="{GREEN}" fill-opacity="0.8" stroke="none"/>'
                   f'<path d="M12 12v9l8-4.5v-9Z" fill="{ACCENT}" fill-opacity="0.8" stroke="none"/>',
    "help": '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.3a2.6 2.6 0 0 1 5 .9c0 1.8-2.5 2.3-2.5 3.8M12 17.2h0"/>',
    "remove": '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/>',
    "color": '<path d="M12 3a9 9 0 1 0 0 18c1.2 0 1.8-.8 1.8-1.7 0-1.3-1-1.6-1-2.6 0-1 .8-1.7 1.8-1.7H17a4 4 0 0 0 4-4C21 6.6 17 3 12 3Z"/>'
             f'<circle cx="7.5" cy="11" r="1.3" fill="{RED}" stroke="none"/>'
             f'<circle cx="10.5" cy="7" r="1.3" fill="{GREEN}" stroke="none"/>'
             f'<circle cx="15.5" cy="7.5" r="1.3" fill="{ACCENT}" stroke="none"/>',
}


def _cube_view_svg(face: str) -> str:
    """Isometric cube with the face seen by the given standard view filled."""
    cam = np.array([0.55, -1.0, 0.7])  # camera direction: sees front, right and top
    d = -cam / np.linalg.norm(cam)
    r = np.cross(d, [0.0, 0.0, 1.0])
    r /= np.linalg.norm(r)
    u = np.cross(r, d)
    corners = {(x, y, z): np.array([x, y, z], float) - 0.5 for x in (0, 1) for y in (0, 1) for z in (0, 1)}

    def pt(c):
        p = corners[c]
        return 12 + 10.5 * float(p @ r), 12 - 10.5 * float(p @ u)

    faces = {
        "front": [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)],
        "back": [(0, 1, 0), (1, 1, 0), (1, 1, 1), (0, 1, 1)],
        "left": [(0, 0, 0), (0, 1, 0), (0, 1, 1), (0, 0, 1)],
        "right": [(1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1)],
        "top": [(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)],
        "bottom": [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)],
    }
    hidden_face = face in ("back", "left", "bottom")
    poly = " ".join(f"{x:.2f},{y:.2f}" for x, y in map(pt, faces[face]))
    out = [f'<polygon points="{poly}" fill="{ACCENT}" fill-opacity="{0.45 if hidden_face else 0.9}" stroke="none"/>']
    hidden_corner = (0, 1, 0)
    edges = set()
    for c in corners:
        for k in range(3):
            if c[k] == 0:
                d = list(c)
                d[k] = 1
                edges.add((c, tuple(d)))
    for a, b in edges:
        (x1, y1), (x2, y2) = pt(a), pt(b)
        dash = ' stroke-dasharray="1.6 1.6" stroke-opacity="0.6"' if hidden_corner in (a, b) else ""
        out.append(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}"{dash}/>')
    return "".join(out)


def svg(name: str) -> str:
    body = _ICONS.get(name)
    if body is None and name.startswith("view_"):
        body = _cube_view_svg(name[5:])
    return _HEAD + (body or "") + "</svg>"


_cache: dict[str, QIcon] = {}


def icon(name: str) -> QIcon:
    if name not in _cache:
        renderer = QSvgRenderer(QByteArray(svg(name).encode()))
        ic = QIcon()
        for size in (24, 32, 48, 64):
            pm = QPixmap(size, size)
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing)
            renderer.render(p)
            p.end()
            ic.addPixmap(pm)
        _cache[name] = ic
    return _cache[name]


APP_ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#1b2a4a"/>
      <stop offset="1" stop-color="#0a1222"/>
    </linearGradient>
    <linearGradient id="tooth" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#ffffff"/>
      <stop offset="1" stop-color="#cfe3f7"/>
    </linearGradient>
    <linearGradient id="ring" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#2fd4c6"/>
      <stop offset="1" stop-color="#3b82f6"/>
    </linearGradient>
  </defs>
  <rect x="8" y="8" width="240" height="240" rx="56" fill="url(#bg)"/>
  <rect x="8.5" y="8.5" width="239" height="239" rx="55.5" fill="none" stroke="#ffffff" stroke-opacity="0.10" stroke-width="2"/>
  <ellipse cx="128" cy="134" rx="98" ry="34" fill="none" stroke="url(#ring)" stroke-width="9"
           stroke-linecap="round" stroke-dasharray="420 200" transform="rotate(-18 128 134)"/>
  <path d="M92 52c-22 0-35 17-35 40 0 25 11 40 18 68 4 17 8 40 22 40 13 0 13-26 20-44 3-8 6-11 11-11s8 3 11 11c7 18 7 44 20 44 14 0 18-23 22-40 7-28 18-43 18-68 0-23-13-40-35-40-15 0-24 8-36 8s-21-8-36-8z"
        fill="url(#tooth)"/>
  <path d="M92 52c-22 0-35 17-35 40 0 25 11 40 18 68 4 17 8 40 22 40 13 0 13-26 20-44 3-8 6-11 11-11s8 3 11 11c7 18 7 44 20 44 14 0 18-23 22-40 7-28 18-43 18-68 0-23-13-40-35-40-15 0-24 8-36 8s-21-8-36-8z"
        fill="none" stroke="#0a1222" stroke-opacity="0.25" stroke-width="3"/>
  <ellipse cx="128" cy="134" rx="98" ry="34" fill="none" stroke="url(#ring)" stroke-width="9"
           stroke-linecap="round" stroke-dasharray="0 250 170 200" transform="rotate(-18 128 134)"/>
  <circle cx="214" cy="96" r="9" fill="#2fd4c6"/>
</svg>"""


def app_icon() -> QIcon:
    if "__app__" not in _cache:
        renderer = QSvgRenderer(QByteArray(APP_ICON_SVG.encode()))
        ic = QIcon()
        for size in (16, 24, 32, 48, 64, 128, 256):
            pm = QPixmap(size, size)
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing)
            renderer.render(p)
            p.end()
            ic.addPixmap(pm)
        _cache["__app__"] = ic
    return _cache["__app__"]
