"""Section view: slice the models with a plane (display only) and measure gaps in 2D."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)
from scipy.spatial import cKDTree
from vtkmodules.vtkCommonCore import vtkPoints
from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPlane, vtkPolyData
from vtkmodules.vtkRenderingCore import vtkActor, vtkPolyDataMapper

from .i18n import tr
from .section import SegmentSet, gap_analysis, plane_basis, plane_section, to_plane_2d
from .selection import focal_plane_point
from .viewer import Overlay2D

GAP_OK = QColor(70, 205, 100)
GAP_WARN = QColor(245, 200, 50)
GAP_BAD = QColor(240, 75, 65)


def _qcolor(rgb, factor=1.0):
    return QColor(*[int(max(0, min(255, c * 255 * factor))) for c in rgb])


class SectionController:
    """Holds the section plane, clips the models and builds the section curves."""

    def __init__(self, viewer, on_change):
        self.viewer = viewer
        self.on_change = on_change
        self.active = False
        self.base_origin = None
        self.normal = None
        self.u = self.v = None
        self.offset = 0.0
        self.flip = False
        self.clip = True
        self.curves = []  # (model, segs2d)
        self._actors = []
        self.overlay = Overlay2D(viewer.ren, color=(0.3, 0.85, 1.0), width=2.0)
        self.overlay.set_visible(False)
        self.tool = _LineTool(self)

    # ------------------------------------------------------------ lifecycle
    def activate(self):
        self.active = True
        self.viewer.style.tool = self.tool
        self.overlay.set_visible(True)
        self.update()

    def deactivate(self):
        self.active = False
        if self.viewer.style.tool is self.tool:
            self.viewer.style.tool = None
        self.overlay.clear()
        self.overlay.set_visible(False)
        self._remove_section()
        self.viewer.render()

    @property
    def origin(self):
        return None if self.base_origin is None else self.base_origin + self.normal * self.offset

    # ------------------------------------------------------------ plane
    def set_line(self, d0, d1):
        """Plane through the drawn screen line, parallel to the viewing direction."""
        ren = self.viewer.ren
        p0 = focal_plane_point(ren, *d0)
        p1 = focal_plane_point(ren, *d1)
        dop = np.array(ren.GetActiveCamera().GetDirectionOfProjection())
        along = p1 - p0
        if np.linalg.norm(along) < 1e-9:
            return
        n = np.cross(along, dop)
        n /= np.linalg.norm(n)
        self.base_origin = p0
        self.normal = n
        self.offset = 0.0
        # 2D axes: u along the drawn line, v towards the viewer (what was "up" on screen)
        self.u = along / np.linalg.norm(along)
        self.v = -dop - n * (-dop @ n)
        self.v /= np.linalg.norm(self.v)
        self.update()

    def clear(self):
        self.base_origin = None
        self._remove_section()
        self.viewer.render()
        self.on_change()

    def _remove_section(self):
        for m in self.viewer.models:
            m.mapper.RemoveAllClippingPlanes()
        for a in self._actors:
            self.viewer.ren.RemoveActor(a)
        self._actors = []
        self.curves = []

    def size_hint(self):
        lo, hi = [], []
        for m in self.viewer.models:
            if m.visible:
                a, b = m.world_bounds()
                lo.append(a)
                hi.append(b)
        if not lo:
            return 10.0
        return float(np.linalg.norm(np.max(hi, 0) - np.min(lo, 0)))

    # ------------------------------------------------------------ build
    def update(self):
        self._remove_section()
        if not self.active or self.base_origin is None:
            self.viewer.render()
            self.on_change()
            return
        origin = self.origin
        normal = -self.normal if self.flip else self.normal
        for m in self.viewer.models:
            if not m.visible:
                continue
            if self.clip:
                plane = vtkPlane()
                plane.SetOrigin(*origin)
                plane.SetNormal(*normal)
                m.mapper.AddClippingPlane(plane)
            wv = m.world_geometry()[0]
            segs = plane_section(wv, m.mesh.faces, origin, self.normal)
            if len(segs) == 0:
                continue
            self._actors.append(self._line_actor(segs, m.color))
            s2 = to_plane_2d(segs.reshape(-1, 3), origin, self.u, self.v).reshape(-1, 2, 2)
            self.curves.append((m, s2))
        for a in self._actors:
            self.viewer.ren.AddActor(a)
        self.viewer.render()
        self.on_change()

    @staticmethod
    def _line_actor(segs, color):
        pts = vtkPoints()
        cells = vtkCellArray()
        for i, (a, b) in enumerate(segs):
            pts.InsertNextPoint(*a)
            pts.InsertNextPoint(*b)
            cells.InsertNextCell(2)
            cells.InsertCellPoint(2 * i)
            cells.InsertCellPoint(2 * i + 1)
        pd = vtkPolyData()
        pd.SetPoints(pts)
        pd.SetLines(cells)
        mapper = vtkPolyDataMapper()
        mapper.SetInputData(pd)
        mapper.SetResolveCoincidentTopologyToPolygonOffset()
        mapper.SetRelativeCoincidentTopologyLineOffsetParameters(-2, -2)
        actor = vtkActor()
        actor.SetMapper(mapper)
        p = actor.GetProperty()
        p.SetColor(*[min(1.0, c * 0.55) for c in color])
        p.SetLineWidth(3.0)
        p.SetLighting(False)
        actor.PickableOff()
        return actor


class _LineTool:
    """Left drag draws the section line; right drag still rotates."""

    def __init__(self, ctrl: SectionController):
        self.c = ctrl
        self._start = None

    def on_press(self, x, y, ctrl, shift, repeat):
        self._start = (x, y)
        return True

    def on_move(self, x, y, ctrl, shift):
        if self._start is None:
            return False
        self.c.overlay.set([self._start, (x, y)])
        self.c.viewer.render()
        return True

    def on_release(self, x, y, ctrl, shift):
        start, self._start = self._start, None
        self.c.overlay.clear()
        if start is not None and np.hypot(x - start[0], y - start[1]) > 8:
            self.c.set_line(start, (x, y))
        else:
            self.c.viewer.render()
        return True

    def on_wheel(self, direction):
        return False


class SectionView(QWidget):
    """2D drawing of the section curves with zoom/pan, click-to-measure and gap colouring."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(260)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.ClickFocus)
        self.curves = []  # (name, QColor, segs2d)
        self.gap = None
        self.cmp_seg_dist = None
        self.cmp_index = -1
        self.ok = 0.05
        self.warn = 0.15
        self.scale = 10.0  # pixels per mm
        self.center = np.zeros(2)
        self.measure = []
        self.hover = None
        self._pan = None
        self._snap_tree = None
        self._snap_pts = None

    # ------------------------------------------------------------ data
    def set_data(self, curves, gap=None, cmp_index=-1, cmp_seg_dist=None, refit=False):
        self.curves = curves
        self.gap = gap
        self.cmp_index = cmp_index
        self.cmp_seg_dist = cmp_seg_dist
        pts = [c[2].reshape(-1, 2) for c in curves if len(c[2])]
        if pts:
            self._snap_pts = np.vstack(pts)
            self._snap_tree = cKDTree(self._snap_pts)
        else:
            self._snap_pts = self._snap_tree = None
        if refit:
            self.measure = []
            self.fit()
        self.update()

    def fit(self):
        pts = [c[2].reshape(-1, 2) for c in self.curves if len(c[2])]
        if not pts:
            self.update()
            return
        p = np.vstack(pts)
        lo, hi = p.min(0), p.max(0)
        self.center = (lo + hi) / 2
        span = np.maximum(hi - lo, 1e-3)
        self.scale = 0.85 * min(self.width() / span[0], self.height() / span[1])
        self.update()

    # ------------------------------------------------------------ mapping
    def to_screen(self, p):
        p = np.asarray(p, float)
        x = (p[..., 0] - self.center[0]) * self.scale + self.width() / 2
        y = -(p[..., 1] - self.center[1]) * self.scale + self.height() / 2
        return np.stack([x, y], -1)

    def to_world(self, x, y):
        return np.array([(x - self.width() / 2) / self.scale + self.center[0],
                         -(y - self.height() / 2) / self.scale + self.center[1]])

    def _snap(self, x, y, radius_px=12):
        w = self.to_world(x, y)
        if self._snap_tree is not None:
            d, i = self._snap_tree.query(w)
            if d * self.scale <= radius_px:
                return self._snap_pts[i]
        return w

    def gap_color(self, d):
        return GAP_OK if d <= self.ok else GAP_WARN if d <= self.warn else GAP_BAD

    # ------------------------------------------------------------ painting
    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(22, 24, 28))
        self._draw_grid(p)
        for i, (name, color, segs) in enumerate(self.curves):
            if not len(segs):
                continue
            s = self.to_screen(segs)
            if i == self.cmp_index and self.cmp_seg_dist is not None:
                for k, (a, b) in enumerate(s):
                    p.setPen(QPen(self.gap_color(self.cmp_seg_dist[k]), 2.4))
                    p.drawLine(QPointF(*a), QPointF(*b))
            else:
                p.setPen(QPen(color, 2.0))
                p.drawLines([QPointF(*a) for pair in s for a in pair])
        self._draw_max_gap(p)
        self._draw_measure(p)
        self._draw_legend(p)
        self._draw_hover(p)
        p.end()

    def _draw_grid(self, p):
        if self.scale <= 0:
            return
        step = 1.0
        for s in (0.1, 0.5, 1, 2, 5, 10, 20, 50):
            if s * self.scale >= 28:
                step = s
                break
        lo = self.to_world(0, self.height())
        hi = self.to_world(self.width(), 0)
        p.setPen(QPen(QColor(40, 44, 52), 1))
        for x in np.arange(np.floor(lo[0] / step) * step, hi[0] + step, step):
            sx = self.to_screen([x, 0])[0]
            p.drawLine(QPointF(sx, 0), QPointF(sx, self.height()))
        for y in np.arange(np.floor(lo[1] / step) * step, hi[1] + step, step):
            sy = self.to_screen([0, y])[1]
            p.drawLine(QPointF(0, sy), QPointF(self.width(), sy))
        # scale bar
        bar = step * self.scale
        y0 = self.height() - 14
        p.setPen(QPen(QColor(220, 224, 230), 2))
        p.drawLine(QPointF(12, y0), QPointF(12 + bar, y0))
        p.setFont(QFont(p.font().family(), 8))
        p.drawText(QPointF(16 + bar, y0 + 4), f"{step:g} mm")

    def _draw_max_gap(self, p):
        g = self.gap
        if g is None or g.max_index < 0:
            return
        a = self.to_screen(g.points[g.max_index])
        b = self.to_screen(g.nearest[g.max_index])
        pen = QPen(QColor(255, 255, 255), 1.5, Qt.DashLine)
        p.setPen(pen)
        p.drawLine(QPointF(*a), QPointF(*b))
        p.setBrush(self.gap_color(g.max))
        p.drawEllipse(QPointF(*a), 4, 4)
        p.setBrush(Qt.NoBrush)
        self._label(p, (a + b) / 2 + [8, -8], f"max {g.max:.3f} mm", self.gap_color(g.max))

    def _draw_measure(self, p):
        if not self.measure:
            return
        pts = [self.to_screen(m) for m in self.measure]
        p.setPen(QPen(QColor(90, 190, 255), 2))
        p.setBrush(QColor(90, 190, 255))
        for s in pts:
            p.drawEllipse(QPointF(*s), 3.5, 3.5)
        p.setBrush(Qt.NoBrush)
        if len(pts) == 2:
            p.drawLine(QPointF(*pts[0]), QPointF(*pts[1]))
            d = float(np.linalg.norm(self.measure[1] - self.measure[0]))
            self._label(p, (pts[0] + pts[1]) / 2 + [8, 14], f"{d:.3f} mm", QColor(90, 190, 255))

    def _draw_legend(self, p):
        y = 16
        p.setFont(QFont(p.font().family(), 9))
        for i, (name, color, _) in enumerate(self.curves):
            p.setPen(QPen(color, 3))
            p.drawLine(QPointF(10, y - 4), QPointF(28, y - 4))
            p.setPen(QColor(225, 228, 234))
            suffix = f"  ({tr('gap_compared')})" if i == self.cmp_index else ""
            p.drawText(QPointF(34, y), name[:40] + suffix)
            y += 16

    def _draw_hover(self, p):
        if self.hover is None:
            return
        pos, d = self.hover
        s = self.to_screen(pos)
        p.setPen(QPen(self.gap_color(d), 2))
        p.drawEllipse(QPointF(*s), 5, 5)
        self._label(p, s + [10, -10], f"{d:.3f} mm", self.gap_color(d))

    def _label(self, p, pos, text, color):
        p.setFont(QFont(p.font().family(), 9, QFont.Bold))
        fm = p.fontMetrics()
        w, h = fm.horizontalAdvance(text) + 10, fm.height() + 4
        x = min(max(float(pos[0]), 4.0), self.width() - w - 4.0)
        y = min(max(float(pos[1]) - h + 4, 4.0), self.height() - h - 4.0)
        if x < float(pos[0]) - 8:  # pushed left by the edge: put it on the other side of the point
            x = max(4.0, float(pos[0]) - w - 20)
        r = QRectF(x, y, w, h)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(15, 16, 20, 220))
        p.drawRoundedRect(r, 4, 4)
        p.setBrush(Qt.NoBrush)
        p.setPen(color)
        p.drawText(r, Qt.AlignCenter, text)

    # ------------------------------------------------------------ mouse
    def wheelEvent(self, ev):
        pos = ev.position()
        before = self.to_world(pos.x(), pos.y())
        self.scale *= 1.2 if ev.angleDelta().y() > 0 else 1 / 1.2
        after = self.to_world(pos.x(), pos.y())
        self.center += before - after
        self.update()

    def mousePressEvent(self, ev):
        if ev.button() in (Qt.RightButton, Qt.MiddleButton):
            self._pan = (ev.position().x(), ev.position().y(), self.center.copy())
        elif ev.button() == Qt.LeftButton:
            pt = self._snap(ev.position().x(), ev.position().y())
            if len(self.measure) >= 2:
                self.measure = []
            self.measure.append(np.asarray(pt, float))
            self.update()

    def mouseMoveEvent(self, ev):
        x, y = ev.position().x(), ev.position().y()
        if self._pan is not None:
            x0, y0, c0 = self._pan
            self.center = c0 - np.array([x - x0, -(y - y0)]) / self.scale
            self.update()
            return
        hover = None
        g = self.gap
        if g is not None and len(g.points):
            sp = self.to_screen(g.points)
            d = np.hypot(sp[:, 0] - x, sp[:, 1] - y)
            i = int(np.argmin(d))
            if d[i] < 14:
                hover = (g.points[i], float(g.distance[i]))
        if (hover is None) != (self.hover is None) or hover is not None:
            self.hover = hover
            self.update()

    def mouseReleaseEvent(self, ev):
        self._pan = None

    def mouseDoubleClickEvent(self, ev):
        self.measure = []
        self.fit()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self.update()


class SectionPanel(QWidget):
    def __init__(self, ctrl: SectionController, models_getter, parent=None):
        super().__init__(parent)
        self.c = ctrl
        self.models_getter = models_getter
        self._last_plane = None
        lay = QVBoxLayout(self)

        help_lbl = QLabel(tr("section_help"))
        help_lbl.setWordWrap(True)
        help_lbl.setStyleSheet("color: gray; font-size: 11px;")
        lay.addWidget(help_lbl)

        row = QHBoxLayout()
        row.addWidget(QLabel(tr("section_offset")))
        self.offset = QSlider(Qt.Horizontal)
        self.offset.setRange(-500, 500)
        self.offset.valueChanged.connect(lambda v: self._offset_changed(v))
        row.addWidget(self.offset, 1)
        self.offset_lbl = QLabel("0.00 mm")
        self.offset_lbl.setFixedWidth(70)
        row.addWidget(self.offset_lbl)
        lay.addLayout(row)

        row = QHBoxLayout()
        self.clip_cb = QCheckBox(tr("section_clip"))
        self.clip_cb.setChecked(True)
        self.clip_cb.toggled.connect(lambda on: self._set_clip(on))
        row.addWidget(self.clip_cb)
        b = QPushButton(tr("section_flip"))
        b.clicked.connect(lambda _=False: self._flip())
        row.addWidget(b)
        b = QPushButton(tr("section_clear"))
        b.clicked.connect(lambda _=False: self.c.clear())
        row.addWidget(b)
        lay.addLayout(row)

        form = QFormLayout()
        self.ref_cb = QComboBox()
        self.cmp_cb = QComboBox()
        self.ref_cb.currentIndexChanged.connect(lambda i: self.refresh_view())
        self.cmp_cb.currentIndexChanged.connect(lambda i: self.refresh_view())
        form.addRow(tr("gap_reference"), self.ref_cb)
        form.addRow(tr("gap_compared"), self.cmp_cb)
        thr = QHBoxLayout()
        self.ok_sb = QDoubleSpinBox()
        self.warn_sb = QDoubleSpinBox()
        for sb, val in ((self.ok_sb, 0.05), (self.warn_sb, 0.15)):
            sb.setDecimals(3)
            sb.setSingleStep(0.01)
            sb.setRange(0.0, 10.0)
            sb.setValue(val)
            sb.setSuffix(" mm")
            sb.valueChanged.connect(lambda _v: self.refresh_view())
        thr.addWidget(QLabel("●"))
        thr.itemAt(0).widget().setStyleSheet(f"color:{GAP_OK.name()}; font-size:14px;")
        thr.addWidget(self.ok_sb)
        lbl = QLabel("●")
        lbl.setStyleSheet(f"color:{GAP_WARN.name()}; font-size:14px;")
        thr.addWidget(lbl)
        thr.addWidget(self.warn_sb)
        lbl = QLabel("● >")
        lbl.setStyleSheet(f"color:{GAP_BAD.name()}; font-size:14px;")
        thr.addWidget(lbl)
        form.addRow(tr("gap_limits"), thr)
        lay.addLayout(form)

        self.stats = QLabel("")
        self.stats.setWordWrap(True)
        self.stats.setStyleSheet("font-weight:bold;")
        lay.addWidget(self.stats)

        self.view = SectionView()
        lay.addWidget(self.view, 1)
        tip = QLabel(tr("section_view_help"))
        tip.setWordWrap(True)
        tip.setStyleSheet("color: gray; font-size: 11px;")
        lay.addWidget(tip)

        self._offset_timer = QTimer(self)
        self._offset_timer.setSingleShot(True)
        self._offset_timer.timeout.connect(lambda: self.c.update())

    # ------------------------------------------------------------ models
    def refresh_models(self):
        models = self.models_getter()
        for cb, default in ((self.ref_cb, 0), (self.cmp_cb, 1)):
            current = cb.currentData()
            cb.blockSignals(True)
            cb.clear()
            cb.addItem("—", None)
            for m in models:
                cb.addItem(m.name, m)
            idx = next((i + 1 for i, m in enumerate(models) if m is current), None)
            if idx is None:
                idx = default + 1 if len(models) > default else 0
            cb.setCurrentIndex(idx)
            cb.blockSignals(False)

    # ------------------------------------------------------------ actions
    def _offset_changed(self, v):
        size = self.c.size_hint()
        self.c.offset = v / 1000.0 * size
        self.offset_lbl.setText(f"{self.c.offset:+.2f} mm")
        self._offset_timer.start(40)

    def _set_clip(self, on):
        self.c.clip = on
        self.c.update()

    def _flip(self):
        self.c.flip = not self.c.flip
        self.c.update()

    def reset_offset(self):
        self.offset.blockSignals(True)
        self.offset.setValue(0)
        self.offset.blockSignals(False)
        self.offset_lbl.setText("+0.00 mm")

    def refresh_view(self):
        """Rebuild the 2D view and the gap statistics from the controller's curves."""
        plane_key = None if self.c.base_origin is None else (tuple(self.c.base_origin), tuple(self.c.normal))
        new_plane = plane_key != self._last_plane
        if new_plane:
            self._last_plane = plane_key
            if self.c.offset == 0.0:
                self.reset_offset()
        curves = [(m.name, _qcolor(m.color, 0.9 if i else 1.0), s) for i, (m, s) in enumerate(self.c.curves)]
        ref, cmp_ = self.ref_cb.currentData(), self.cmp_cb.currentData()
        models = [m for m, _ in self.c.curves]
        self.view.ok, self.view.warn = self.ok_sb.value(), self.warn_sb.value()
        gap, seg_dist, cmp_index = None, None, -1
        if ref is not None and cmp_ is not None and ref is not cmp_ and ref in models and cmp_ in models:
            rs = self.c.curves[models.index(ref)][1]
            cs = self.c.curves[models.index(cmp_)][1]
            gap = gap_analysis(rs, cs, spacing=0.05)
            d_ends, _ = SegmentSet(rs).nearest(cs.reshape(-1, 2))
            seg_dist = d_ends.reshape(-1, 2).mean(1)
            cmp_index = models.index(cmp_)
            self.stats.setText(tr("gap_stats", max=gap.max, mean=gap.mean))
        elif self.c.base_origin is None:
            self.stats.setText(tr("section_none"))
        else:
            self.stats.setText(tr("gap_choose"))
        self.view.set_data(curves, gap, cmp_index, seg_dist, refit=new_plane)
