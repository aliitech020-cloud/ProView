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
