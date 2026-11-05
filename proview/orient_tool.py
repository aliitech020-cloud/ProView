"""Orientation tool: rotate / move a model with an on-screen gizmo against a reference plane."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from vtkmodules.vtkCommonCore import vtkPoints
from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData
from vtkmodules.vtkCommonTransforms import vtkTransform
from vtkmodules.vtkFiltersCore import vtkTubeFilter
from vtkmodules.vtkFiltersGeneral import vtkTransformPolyDataFilter
from vtkmodules.vtkFiltersSources import vtkArrowSource, vtkPlaneSource
from vtkmodules.vtkRenderingCore import vtkActor, vtkPolyDataMapper, vtkRenderer

from .i18n import tr
from .selection import project, segment_distance

AXES = np.eye(3)
AXIS_COLORS = [(0.93, 0.3, 0.3), (0.35, 0.82, 0.4), (0.3, 0.55, 0.98)]
HOVER_COLOR = (1.0, 0.85, 0.2)


def rotation_about(axis, angle_rad, pivot) -> np.ndarray:
    axis = np.asarray(axis, float)
    axis = axis / np.linalg.norm(axis)
    K = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    R = np.eye(3) + np.sin(angle_rad) * K + (1 - np.cos(angle_rad)) * K @ K
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = pivot - R @ pivot
    return T


def translation(vec) -> np.ndarray:
    T = np.eye(4)
    T[:3, 3] = vec
    return T


def _ring_points(center, axis, radius, n=96):
    a = np.cross(axis, [0.0, 0.0, 1.0] if abs(axis[2]) < 0.9 else [1.0, 0.0, 0.0])
    a /= np.linalg.norm(a)
    b = np.cross(axis, a)
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return center + radius * (np.cos(t)[:, None] * a + np.sin(t)[:, None] * b)


def _polyline_actor(points, closed, color, tube_radius):
    pts = vtkPoints()
    for p in points:
        pts.InsertNextPoint(*p)
    cells = vtkCellArray()
    n = len(points)
    cells.InsertNextCell(n + (1 if closed else 0))
    for i in range(n):
        cells.InsertCellPoint(i)
    if closed:
        cells.InsertCellPoint(0)
    pd = vtkPolyData()
    pd.SetPoints(pts)
    pd.SetLines(cells)
    tube = vtkTubeFilter()
    tube.SetInputData(pd)
    tube.SetRadius(tube_radius)
    tube.SetNumberOfSides(12)
    mapper = vtkPolyDataMapper()
    mapper.SetInputConnection(tube.GetOutputPort())
    actor = vtkActor()
    actor.SetMapper(mapper)
    actor.GetProperty().SetColor(*color)
    actor.GetProperty().SetAmbient(0.35)
    actor.PickableOff()
    return actor


def _arrow_actor(start, direction, length, color):
    src = vtkArrowSource()
    src.SetShaftRadius(0.035)
    src.SetTipRadius(0.09)
    src.SetTipLength(0.25)
    src.SetShaftResolution(16)
    src.SetTipResolution(24)
    d = np.asarray(direction, float)
    # rotate +X onto d
    x = np.array([1.0, 0.0, 0.0])
    axis = np.cross(x, d)
    ang = np.degrees(np.arccos(np.clip(x @ d, -1, 1)))
    t = vtkTransform()
    t.Translate(*start)
    if np.linalg.norm(axis) > 1e-9:
        t.RotateWXYZ(ang, *axis)
    elif ang > 90:
        t.RotateWXYZ(180, 0, 0, 1)
    t.Scale(length, length, length)
    f = vtkTransformPolyDataFilter()
    f.SetInputConnection(src.GetOutputPort())
    f.SetTransform(t)
    mapper = vtkPolyDataMapper()
    mapper.SetInputConnection(f.GetOutputPort())
    actor = vtkActor()
    actor.SetMapper(mapper)
    actor.GetProperty().SetColor(*color)
    actor.GetProperty().SetAmbient(0.35)
    actor.PickableOff()
    return actor


class OrientController:
    def __init__(self, viewer, get_model, push_undo, on_change):
        self.viewer = viewer
        self.get_model = get_model
        self.push_undo = push_undo
        self.on_change = on_change
        self.active = False
        self.model = None
        self.start_matrix = None
        self.show_plane = True
        # gizmo is drawn on top of the models (own layer, shared camera)
        self.gren = vtkRenderer()
        self.gren.SetLayer(1)
        self.gren.InteractiveOff()
        self.gren.SetActiveCamera(viewer.ren.GetActiveCamera())
        self.gren.AddObserver("StartEvent", lambda *a: self.gren.ResetCameraClippingRange())
        self.handles = []  # (kind, axis index, actor, screen geometry helper)
        self.plane_actors = []
        self.center = np.zeros(3)
        self.radius = 10.0
        self.tool = _GizmoTool(self)

    # ------------------------------------------------------------ lifecycle
    def activate(self):
        self.active = True
        self.viewer.rw.AddRenderer(self.gren)
        self.viewer.style.tool = self.tool
        self.set_model(self.get_model())

    def deactivate(self):
        self.active = False
        if self.viewer.style.tool is self.tool:
            self.viewer.style.tool = None
        self._clear_actors()
        self.viewer.rw.RemoveRenderer(self.gren)
        self.model = None
        self.viewer.render()

    def set_model(self, model):
        if not self.active:
            return
        self.model = model
        self.start_matrix = None if model is None else model.matrix.copy()
        self.rebuild(reset_plane=True)
        self.on_change()

    # ------------------------------------------------------------ drawing
    def _clear_actors(self):
        for _, _, a in self.handles:
            self.gren.RemoveActor(a)
        self.handles = []
        for a in self.plane_actors:
            self.viewer.ren.RemoveActor(a)
        self.plane_actors = []

    def rebuild(self, reset_plane=False, keep_center=False):
        self._clear_actors()
        m = self.model
        if m is None or not self.active:
            self.viewer.render()
            return
        if not keep_center:  # while dragging the pivot must not drift
            lo, hi = m.world_bounds()
            self.center = (lo + hi) / 2
            self.radius = max(float(np.linalg.norm(hi - lo)) * 0.42, 1e-3)
        else:
            lo = self.center - self.radius
        r = self.radius
        for i in range(3):
            ring = _ring_points(self.center, AXES[i], r)
            actor = _polyline_actor(ring, True, AXIS_COLORS[i], r * 0.012)
            self.handles.append(("ring", i, actor))
            for sign in (1, -1):
                arrow = _arrow_actor(self.center + AXES[i] * r * 1.08 * sign, AXES[i] * sign, r * 0.32,
                                     AXIS_COLORS[i])
                self.handles.append(("arrow" if sign > 0 else "arrow_neg", i, arrow))
        for _, _, a in self.handles:
            self.gren.AddActor(a)
        if reset_plane or not hasattr(self, "plane_z"):
            self.plane_z = float(m.world_bounds()[0][2])
        if self.show_plane:
            self._make_plane(r)
        self.viewer.render()

    def _make_plane(self, r):
        size = r * 3.0
        c = self.center
        z = self.plane_z
        src = vtkPlaneSource()
        src.SetOrigin(c[0] - size / 2, c[1] - size / 2, z)
        src.SetPoint1(c[0] + size / 2, c[1] - size / 2, z)
        src.SetPoint2(c[0] - size / 2, c[1] + size / 2, z)
        mapper = vtkPolyDataMapper()
        mapper.SetInputConnection(src.GetOutputPort())
        plane = vtkActor()
        plane.SetMapper(mapper)
        p = plane.GetProperty()
        p.SetColor(0.35, 0.6, 0.95)
        p.SetOpacity(0.18)
        p.SetLighting(False)
        plane.PickableOff()
        # grid lines every ~1/10 of the plane
        step = 10 ** np.floor(np.log10(size / 10))
        pts = vtkPoints()
        cells = vtkCellArray()
        k = 0
        for x in np.arange(np.ceil((c[0] - size / 2) / step) * step, c[0] + size / 2, step):
            for a, b in (((x, c[1] - size / 2), (x, c[1] + size / 2)),):
                pts.InsertNextPoint(a[0], a[1], z)
                pts.InsertNextPoint(b[0], b[1], z)
                cells.InsertNextCell(2)
                cells.InsertCellPoint(k)
                cells.InsertCellPoint(k + 1)
                k += 2
        for y in np.arange(np.ceil((c[1] - size / 2) / step) * step, c[1] + size / 2, step):
            pts.InsertNextPoint(c[0] - size / 2, y, z)
            pts.InsertNextPoint(c[0] + size / 2, y, z)
            cells.InsertNextCell(2)
            cells.InsertCellPoint(k)
            cells.InsertCellPoint(k + 1)
            k += 2
        pd = vtkPolyData()
        pd.SetPoints(pts)
        pd.SetLines(cells)
        gm = vtkPolyDataMapper()
        gm.SetInputData(pd)
        grid = vtkActor()
        grid.SetMapper(gm)
        g = grid.GetProperty()
        g.SetColor(0.55, 0.75, 1.0)
        g.SetOpacity(0.45)
        g.SetLighting(False)
        grid.PickableOff()
        self.plane_actors = [plane, grid]
        for a in self.plane_actors:
            self.viewer.ren.AddActor(a)

    def set_show_plane(self, on):
        self.show_plane = on
        self.rebuild()

    # ------------------------------------------------------------ hit testing
    def hit(self, x, y, tol=9.0):
        """(kind, axis) of the handle under the cursor, arrows first."""
        if self.model is None:
            return None
        ren = self.viewer.ren
        best = None
        r = self.radius
        for i in range(3):
            for sign, kind in ((1, "arrow"), (-1, "arrow_neg")):
                a = self.center + AXES[i] * r * 1.08 * sign
                b = self.center + AXES[i] * r * 1.40 * sign
                pa, pb = project(ren, np.array([a, b]))[:, :2]
                d = float(segment_distance(np.array([[x, y]]), pa, pb)[0])
                if d < tol and (best is None or d < best[0]):
                    best = (d, kind, i)
        if best is not None:
            return best[1], best[2]
        for i in range(3):
            ring = project(ren, _ring_points(self.center, AXES[i], r, 72))[:, :2]
            nxt = np.roll(ring, -1, axis=0)
            ab = nxt - ring
            ap = np.array([x, y]) - ring
            t = np.clip((ap * ab).sum(1) / np.maximum((ab * ab).sum(1), 1e-12), 0, 1)
            d = float(np.min(np.linalg.norm(ring + ab * t[:, None] - [x, y], axis=1)))
            if d < tol and (best is None or d < best[0]):
                best = (d, "ring", i)
        return None if best is None else (best[1], best[2])

    def highlight(self, handle):
        for kind, i, actor in self.handles:
            on = handle is not None and handle[1] == i and (handle[0] == kind or
                                                            (handle[0].startswith("arrow") and kind.startswith("arrow")))
            actor.GetProperty().SetColor(*(HOVER_COLOR if on else AXIS_COLORS[i]))

    # ------------------------------------------------------------ transforms
    def apply(self, T):
        m = self.model
        if m is None:
            return
        m.set_matrix(T @ m.matrix)

    def rotate_step(self, axis_index, degrees):
        if self.model is None:
            return
        self.push_undo(self.model)
        self.apply(rotation_about(AXES[axis_index], np.radians(degrees), self.center))
        self.rebuild()
        self.on_change()

    def reset_original(self):
        """Back to the orientation stored in the file."""
        if self.model is None:
            return
        self.push_undo(self.model)
        self.model.set_matrix(np.eye(4))
        self.rebuild(reset_plane=True)
        self.on_change()

    def cancel(self):
        """Undo everything done since the tool was opened for this model."""
        if self.model is None or self.start_matrix is None:
            return
        self.push_undo(self.model)
        self.model.set_matrix(self.start_matrix)
        self.rebuild(reset_plane=True)
        self.on_change()

    def drop_to_plane(self):
        """Move the model so its lowest point touches the reference plane."""
        if self.model is None:
            return
        lo, _ = self.model.world_bounds()
        self.push_undo(self.model)
        self.apply(translation([0, 0, self.plane_z - lo[2]]))
        self.rebuild()
        self.on_change()


class _GizmoTool:
    """Drag a ring to rotate, an arrow to move; elsewhere the camera rotates as usual."""

    def __init__(self, c: OrientController):
        self.c = c
        self.drag = None  # (kind, axis, last mouse)
        self.hover = None

    def on_press(self, x, y, ctrl, shift, repeat):
        h = self.c.hit(x, y)
        if h is None:
            return False  # rotate the camera
        self.c.push_undo(self.c.model)
        self.drag = (h[0], h[1], (x, y))
        return True

    def on_move(self, x, y, ctrl, shift):
        c = self.c
        if self.drag is None:
            h = c.hit(x, y)
            if h != self.hover:
                self.hover = h
                c.highlight(h)
                c.viewer.render()
            return False
        kind, i, (px, py) = self.drag
        ren = c.viewer.ren
        axis = AXES[i]
        if kind == "ring":
            cs = project(ren, c.center[None])[0, :2]
            a0 = np.arctan2(py - cs[1], px - cs[0])
            a1 = np.arctan2(y - cs[1], x - cs[0])
            delta = (a1 - a0 + np.pi) % (2 * np.pi) - np.pi
            cam = ren.GetActiveCamera()
            to_cam = np.array(cam.GetPosition()) - c.center
            sign = 1.0 if axis @ to_cam >= 0 else -1.0
            if shift:  # fine control
                delta *= 0.2
            c.apply(rotation_about(axis, delta * sign, c.center))
        else:
            direction = axis if kind == "arrow" else -axis
            p0, p1 = project(ren, np.array([c.center, c.center + direction * c.radius]))[:, :2]
            s = p1 - p0
            ls = float(np.linalg.norm(s))
            if ls > 1e-6:
                move = ((x - px) * s[0] + (y - py) * s[1]) / ls  # pixels along the arrow
                dist = move * c.radius / ls
                if shift:
                    dist *= 0.2
                c.apply(translation(direction * dist))
                c.center = c.center + direction * dist
        self.drag = (kind, i, (x, y))
        c.rebuild(keep_center=True)
        c.highlight((kind, i))
        c.viewer.render()
        return True

    def on_release(self, x, y, ctrl, shift):
        if self.drag is None:
            return False
        self.drag = None
        self.c.on_change()
        return True

    def on_wheel(self, direction):
        return False


class OrientPanel(QWidget):
    def __init__(self, ctrl: OrientController, parent=None):
        super().__init__(parent)
        self.c = ctrl
        lay = QVBoxLayout(self)
        self.model_lbl = QLabel("")
        self.model_lbl.setStyleSheet("font-weight:bold;")
        lay.addWidget(self.model_lbl)
        help_lbl = QLabel(tr("orient_help"))
        help_lbl.setWordWrap(True)
        help_lbl.setStyleSheet("color: gray; font-size: 11px;")
        lay.addWidget(help_lbl)

        self.plane_cb = QCheckBox(tr("orient_plane"))
        self.plane_cb.setChecked(True)
        self.plane_cb.toggled.connect(lambda on: self.c.set_show_plane(on))
        lay.addWidget(self.plane_cb)

        step_row = QHBoxLayout()
        step_row.addWidget(QLabel(tr("orient_step")))
        self.step = QSpinBox()
        self.step.setRange(1, 180)
        self.step.setValue(5)
        self.step.setSuffix("°")
        step_row.addWidget(self.step)
        step_row.addStretch(1)
        lay.addLayout(step_row)

        grid = QGridLayout()
        for i, (name, color) in enumerate(zip("XYZ", ("#ee4d4d", "#59d166", "#4d8cfa"))):
            lbl = QLabel(tr("orient_rotate_axis", axis=name))
            lbl.setStyleSheet(f"color:{color}; font-weight:bold;")
            grid.addWidget(lbl, i, 0)
            for col, (text, sign, ninety) in enumerate((("−90°", -1, True), ("−", -1, False),
                                                       ("+", 1, False), ("+90°", 1, True))):
                b = QPushButton(text)
                b.setFixedWidth(52)
                b.clicked.connect(lambda _=False, a=i, s=sign, n=ninety:
                                  self.c.rotate_step(a, s * (90 if n else self.step.value())))
                grid.addWidget(b, i, col + 1)
        lay.addLayout(grid)

        b = QPushButton(tr("orient_drop"))
        b.clicked.connect(lambda _=False: self.c.drop_to_plane())
        lay.addWidget(b)
        row = QHBoxLayout()
        b = QPushButton(tr("orient_cancel"))
        b.setToolTip(tr("orient_cancel_tip"))
        b.clicked.connect(lambda _=False: self.c.cancel())
        row.addWidget(b)
        b = QPushButton(tr("orient_reset"))
        b.setToolTip(tr("orient_reset_tip"))
        b.clicked.connect(lambda _=False: self.c.reset_original())
        row.addWidget(b)
        lay.addLayout(row)
        lay.addStretch(1)

    def refresh(self):
        m = self.c.model
        self.model_lbl.setText(tr("orient_model", name=m.name) if m is not None else tr("select_model_first"))
