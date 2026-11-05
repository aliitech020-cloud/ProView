"""Cut tool: select surface regions with a brush, a lasso or connected points and delete them."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QGridLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QRadioButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from .i18n import tr
from .selection import focal_plane_point, pick_mesh, points_in_polygon, project, segment_distance, visible_mask
from .viewer import Overlay2D

BRUSH, LASSO, POLYGON = "brush", "lasso", "polygon"


class CutTool:
    def __init__(self, viewer, get_model, push_undo, on_change, push_selection_undo=None):
        self.viewer = viewer
        self.push_selection_undo = push_selection_undo or (lambda m: None)
        self.get_model = get_model
        self.push_undo = push_undo
        self.on_change = on_change
        self.mode = BRUSH
        self.radius = 25.0
        self.through = False
        self.active = False

        ren = viewer.ren
        self.line = Overlay2D(ren, color=(1.0, 0.85, 0.1), width=2.0)
        self.points = Overlay2D(ren, color=(1.0, 0.95, 0.3), point_size=9)
        self.first_point = Overlay2D(ren, color=(0.2, 1.0, 0.4), point_size=13)
        self.rubber = Overlay2D(ren, color=(1.0, 0.85, 0.1), width=1.0)
        self.cursor = Overlay2D(ren, color=(1.0, 1.0, 1.0), width=1.5)
        self._overlays = [self.line, self.points, self.first_point, self.rubber, self.cursor]
        for o in self._overlays:
            o.set_visible(False)

        self._cache = None
        self._dragging = False
        self._subtract = False
        self._last = None
        self._lasso: list[tuple[float, float]] = []
        self.poly3d: list[np.ndarray] = []
        self._press = None
        self._rotating = False
        self._ignore_release = False
        self._mouse = None
        ren.AddObserver("StartEvent", self._before_render)

    # ------------------------------------------------------------ lifecycle
    def activate(self):
        self.active = True
        self.viewer.style.tool = self
        for o in self._overlays:
            o.set_visible(True)
        self.viewer.render()

    def deactivate(self):
        self.cancel()
        self.active = False
        if self.viewer.style.tool is self:
            self.viewer.style.tool = None
        for o in self._overlays:
            o.clear()
            o.set_visible(False)
        for m in self.viewer.models:
            if m.selection.any():
                m.clear_selection()
        self.viewer.render()
        self.on_change()

    def set_mode(self, mode):
        self.cancel()
        self.mode = mode
        if mode != BRUSH:
            self.cursor.clear()
        self.viewer.render()

    def cancel(self):
        """Abort the polyline / lasso in progress."""
        self.poly3d = []
        self._lasso = []
        self._dragging = False
        self._press = None
        if self._rotating:
            self._rotating = False
            self.viewer.style.end_rotate()
        for o in (self.line, self.points, self.first_point, self.rubber):
            o.clear()

    # --------------------------------------------------------------- helpers
    def _prepare(self, model):
        ren = self.viewer.ren
        _, cen, nrm = model.world_geometry()
        zbuf = None
        if not self.through:
            zbuf = self.viewer.capture_zbuffer(ren, hide=[o.actor for o in self._overlays])
        disp = project(ren, cen)
        if self.through:
            vis = np.ones(len(cen), dtype=bool)
        else:
            tol = max(model.mesh.diagonal() * 0.002, 1e-6)
            vis = visible_mask(ren, cen, nrm, disp, zbuf, tol)
        idx = np.nonzero(vis)[0]
        self._cache = (model, idx, disp[idx, :2])

    def _apply(self, hit_idx, subtract):
        model = self._cache[0]
        sel = model.selection.copy()
        sel[hit_idx] = not subtract
        model.set_selection(sel)
        self.on_change()

    def _brush(self, a, b):
        if self._cache is None:
            return
        _, idx, pts = self._cache
        if len(idx) == 0:
            return
        d = segment_distance(pts, np.asarray(a, float), np.asarray(b, float))
        self._apply(idx[d <= self.radius], self._subtract)

    def _circle(self, x, y):
        t = np.linspace(0, 2 * np.pi, 48, endpoint=False)
        return np.stack([x + self.radius * np.cos(t), y + self.radius * np.sin(t)], 1)

    def _before_render(self, *_):
        """Re-project the 3D polyline every frame so it follows the camera."""
        if not self.active or self.mode != POLYGON:
            return
        if not self.poly3d:
            self.line.clear()
            self.points.clear()
            self.first_point.clear()
            self.rubber.clear()
            return
        d = project(self.viewer.ren, np.array(self.poly3d))[:, :2]
        self.line.set(d)
        self.points.set(d)
        self.first_point.set(d[:1])
        if self._mouse is not None and not self._rotating:
            self.rubber.set(np.array([d[-1], self._mouse, d[0]]))
        else:
            self.rubber.clear()

    def _pick_point(self, x, y):
        ren = self.viewer.ren
        best = None
        for m in self.viewer.models:
            if not m.visible:
                continue
            wv = m.world_geometry()[0]
            hit = pick_mesh(ren, x, y, wv, m.mesh.faces)
            if hit is not None and (best is None or hit[0] < best[0]):
                best = hit
        return best[1] if best is not None else focal_plane_point(ren, x, y)

    def close_polygon(self):
        model = self.get_model()
        if model is None or len(self.poly3d) < 3:
            return
        self.push_selection_undo(model)
        self._prepare(model)
        poly = project(self.viewer.ren, np.array(self.poly3d))[:, :2]
        _, idx, pts = self._cache
        self._apply(idx[points_in_polygon(pts, poly)], self._subtract)
        self.cancel()
        self.viewer.render()

    def remove_last_point(self):
        if self.poly3d:
            self.poly3d.pop()
            self.viewer.render()

    # ---------------------------------------------------------- mouse events
    def on_press(self, x, y, ctrl, shift, repeat):
        model = self.get_model()
        if model is None:
            return False
        self._mouse = (x, y)
        if self.mode == BRUSH:
            self._subtract = ctrl
            self.push_selection_undo(model)
            self._prepare(model)
            self._dragging = True
            self._last = (x, y)
            self._brush((x, y), (x, y))
            self.viewer.render()
            return True
        if self.mode == LASSO:
            self._subtract = ctrl
            self._prepare(model)
            self._dragging = True
            self._lasso = [(x, y)]
            return True
        # POLYGON
        if repeat and len(self.poly3d) >= 3:
            self._ignore_release = True
            self.close_polygon()
            return True
        if not self.poly3d:
            self._subtract = ctrl
        self._press = (x, y)
        self._rotating = False
        return True

    def on_move(self, x, y, ctrl, shift):
        self._mouse = (x, y)
        if self.mode == BRUSH:
            self.cursor.set(self._circle(x, y), closed=True)
            if self._dragging:
                self._brush(self._last, (x, y))
                self._last = (x, y)
            self.viewer.render()
            return self._dragging
        if self.mode == LASSO:
            if self._dragging:
                lx, ly = self._lasso[-1]
                if abs(x - lx) + abs(y - ly) >= 2:
                    self._lasso.append((x, y))
                    self.line.set(self._lasso, closed=True)
                    self.viewer.render()
                return True
            return False
        # POLYGON: a left drag rotates the camera, a click adds a point
        if self._press is not None and not self._rotating:
            if abs(x - self._press[0]) + abs(y - self._press[1]) > 5:
                self._rotating = True
                self.viewer.style.start_rotate()
                return False
        if self._rotating:
            return False
        if self.poly3d:
            self.viewer.render()
        return False

    def on_release(self, x, y, ctrl, shift):
        if self.mode == BRUSH:
            self._dragging = False
            return True
        if self.mode == LASSO:
            if self._dragging and len(self._lasso) >= 3 and self._cache is not None:
                self.push_selection_undo(self._cache[0])
                _, idx, pts = self._cache
                self._apply(idx[points_in_polygon(pts, np.array(self._lasso))], self._subtract)
            self._dragging = False
            self._lasso = []
            self.line.clear()
            self.viewer.render()
            return True
        # POLYGON
        if self._ignore_release:
            self._ignore_release = False
            self._press = None
            return True
        if self._rotating:
            self._rotating = False
            self._press = None
            self.viewer.style.end_rotate()
            return True
        if self._press is None:
            return True
        self._press = None
        if len(self.poly3d) >= 3:
            first = project(self.viewer.ren, np.array(self.poly3d[:1]))[0, :2]
            if np.hypot(first[0] - x, first[1] - y) <= 10:
                self.close_polygon()
                return True
        self.poly3d.append(self._pick_point(x, y))
        self.viewer.render()
        return True

    def on_wheel(self, direction):
        if self.mode != BRUSH:
            return False
        self.set_radius(self.radius * (1.15 if direction > 0 else 1 / 1.15))
        if self._mouse:
            self.cursor.set(self._circle(*self._mouse), closed=True)
        self.viewer.render()
        return True

    def set_radius(self, r):
        self.radius = float(np.clip(r, 3, 400))
        self.on_change()

    # ------------------------------------------------------------- commands
    def _model_with_selection(self):
        m = self.get_model()
        if m is not None and m.selection.any():
            return m
        return None

    def delete_selection(self):
        m = self._model_with_selection()
        if m is None:
            return False
        self.push_undo(m)
        m.set_mesh(m.mesh.remove_faces(m.selection))
        self.viewer.render()
        self.on_change()
        return True

    def keep_selection(self):
        m = self._model_with_selection()
        if m is None:
            return False
        self.push_undo(m)
        m.set_mesh(m.mesh.keep_faces(m.selection))
        self.viewer.render()
        self.on_change()
        return True

    def invert(self):
        m = self.get_model()
        if m is not None:
            self.push_selection_undo(m)
            m.set_selection(~m.selection)
            self.viewer.render()
            self.on_change()

    def clear(self):
        m = self.get_model()
        if m is not None and m.selection.any():
            self.push_selection_undo(m)
            m.clear_selection()
            self.viewer.render()
            self.on_change()

    def grow(self, shrink=False):
        m = self.get_model()
        if m is None or not m.selection.any():
            return
        self.push_selection_undo(m)
        sel = ~m.selection if shrink else m.selection
        vmask = np.zeros(m.mesh.n_vertices, dtype=bool)
        vmask[m.mesh.faces[sel].ravel()] = True
        grown = vmask[m.mesh.faces].any(axis=1)
        m.set_selection(~grown if shrink else grown)
        self.viewer.render()
        self.on_change()

    def remove_islands(self, ratio=0.05):
        """Delete connected parts smaller than ``ratio`` of the largest part."""
        m = self.get_model()
        if m is None:
            return 0
        count, labels = m.mesh.connected_components()
        if count <= 1:
            return 0
        sizes = np.bincount(labels, minlength=count)
        small = sizes < ratio * sizes.max()
        if not small.any():
            return 0
        self.push_undo(m)
        m.set_mesh(m.mesh.remove_faces(small[labels]))
        self.viewer.render()
        self.on_change()
        return int(small.sum())


class CutPanel(QWidget):
    def __init__(self, tool: CutTool, parent=None):
        super().__init__(parent)
        self.tool = tool
        lay = QVBoxLayout(self)

        box = QGroupBox(tr("cut_mode"))
        bl = QVBoxLayout(box)
        self.mode_group = QButtonGroup(self)
        self.mode_buttons = {}
        for mode, key in ((BRUSH, "mode_brush"), (LASSO, "mode_lasso"), (POLYGON, "mode_polygon")):
            rb = QRadioButton(tr(key))
            self.mode_group.addButton(rb)
            self.mode_buttons[mode] = rb
            rb.toggled.connect(lambda on, m=mode: on and self.tool.set_mode(m))
            bl.addWidget(rb)
        self.mode_buttons[BRUSH].setChecked(True)
        lay.addWidget(box)

        lay.addWidget(QLabel(tr("brush_size")))
        self.size = QSlider(Qt.Horizontal)
        self.size.setRange(3, 400)
        self.size.setValue(int(tool.radius))
        self.size.valueChanged.connect(lambda v: self.tool.set_radius(v))
        lay.addWidget(self.size)

        clear_btn = QPushButton(tr("clear_sel"))
        clear_btn.clicked.connect(lambda _=False: self.tool.clear())
        lay.addWidget(clear_btn)

        self.through = QCheckBox(tr("through"))
        self.through.toggled.connect(lambda on: setattr(self.tool, "through", on))
        lay.addWidget(self.through)

        self.sel_label = QLabel(tr("selected_count", n=0))
        lay.addWidget(self.sel_label)

        grid = QGridLayout()
        buttons = [
            ("delete_sel", self.tool.delete_selection, 0, 0, 1, 2),
            ("keep_sel", self.tool.keep_selection, 1, 0, 1, 2),
            ("invert_sel", self.tool.invert, 2, 0, 1, 2),
            ("grow_sel", lambda: self.tool.grow(False), 3, 0, 1, 1),
            ("shrink_sel", lambda: self.tool.grow(True), 3, 1, 1, 1),
            ("remove_islands", self.tool.remove_islands, 4, 0, 1, 2),
        ]
        for key, fn, r, c, rs, cs in buttons:
            b = QPushButton(tr(key))
            b.clicked.connect(lambda _=False, f=fn: f())
            if key == "delete_sel":
                b.setStyleSheet("QPushButton { background:#b8322c; color:white; font-weight:bold; padding:6px; }")
            grid.addWidget(b, r, c, rs, cs)
        lay.addLayout(grid)

        help_lbl = QLabel(tr("cut_help"))
        help_lbl.setWordWrap(True)
        help_lbl.setStyleSheet("color: gray; font-size: 11px;")
        lay.addWidget(help_lbl)
        lay.addStretch(1)

    def set_mode(self, mode):
        self.mode_buttons[mode].setChecked(True)

    def refresh(self):
        m = self.tool.get_model()
        n = int(m.selection.sum()) if m is not None else 0
        self.sel_label.setText(tr("selected_count", n=n))
        if self.size.value() != int(self.tool.radius):
            self.size.blockSignals(True)
            self.size.setValue(int(self.tool.radius))
            self.size.blockSignals(False)
