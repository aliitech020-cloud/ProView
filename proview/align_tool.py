"""Alignment tool: point pairs, best-fit (ICP) and automatic alignment."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from vtkmodules.vtkFiltersSources import vtkSphereSource
from vtkmodules.vtkRenderingCore import vtkActor, vtkPolyDataMapper, vtkTextActor

from . import alignment
from .i18n import tr
from .selection import pick_mesh

PAIR_COLORS = [
    (1.0, 0.25, 0.25), (0.25, 0.85, 0.3), (0.3, 0.55, 1.0), (1.0, 0.8, 0.1),
    (0.9, 0.35, 0.95), (0.1, 0.9, 0.9), (1.0, 0.55, 0.15), (0.6, 0.6, 0.6),
]


class Marker:
    def __init__(self, renderer, pos, radius, index):
        color = PAIR_COLORS[index % len(PAIR_COLORS)]
        src = vtkSphereSource()
        src.SetCenter(*pos)
        src.SetRadius(radius)
        src.SetThetaResolution(16)
        src.SetPhiResolution(16)
        mapper = vtkPolyDataMapper()
        mapper.SetInputConnection(src.GetOutputPort())
        self.sphere = vtkActor()
        self.sphere.SetMapper(mapper)
        self.sphere.GetProperty().SetColor(*color)
        self.sphere.PickableOff()
        self.label = vtkTextActor()
        self.label.SetInput(str(index + 1))
        coord = self.label.GetPositionCoordinate()
        coord.SetCoordinateSystemToWorld()
        coord.SetValue(*pos)
        tp = self.label.GetTextProperty()
        tp.SetFontSize(22)
        tp.SetBold(True)
        tp.SetColor(*color)
        tp.SetShadow(True)
        self.label.PickableOff()
        self.renderer = renderer
        renderer.AddActor(self.sphere)
        renderer.AddActor(self.label)

    def remove(self):
        self.renderer.RemoveActor(self.sphere)
        self.renderer.RemoveActor(self.label)


class PointPickTool:
    """Style tool active in split view: click = add a point, drag = rotate."""

    def __init__(self, controller):
        self.c = controller
        self._press = None
        self._rotating = False

    def on_press(self, x, y, ctrl, shift, repeat):
        self._press = (x, y)
        self._rotating = False
        return True

    def on_move(self, x, y, ctrl, shift):
        if self._press is not None and not self._rotating:
            if abs(x - self._press[0]) + abs(y - self._press[1]) > 5:
                self._rotating = True
                self.c.viewer.style.start_rotate()
        return False

    def on_release(self, x, y, ctrl, shift):
        if self._rotating:
            self._rotating = False
            self._press = None
            self.c.viewer.style.end_rotate()
            return True
        if self._press is not None:
            self._press = None
            self.c.pick(x, y)
        return True

    def on_wheel(self, direction):
        return False


class AlignController:
    def __init__(self, viewer, push_undo, on_change, status):
        self.viewer = viewer
        self.push_undo = push_undo
        self.on_change = on_change
        self.status = status
        self.fixed = None
        self.floating = None
        self.pts_fixed: list[np.ndarray] = []
        self.pts_float: list[np.ndarray] = []
        self.markers: list[tuple[str, Marker]] = []
        self.picking = False
        self.pick_tool = PointPickTool(self)
        self.left = self.right = None

    # -------------------------------------------------------------- picking
    def start_picking(self):
        if self.fixed is None or self.floating is None or self.fixed is self.floating:
            return False
        self.clear_points()
        self.left, self.right = self.viewer.enter_split([self.fixed], [self.floating])
        self.viewer.style.tool = self.pick_tool
        self.picking = True
        self.on_change()
        return True

    def stop_picking(self):
        if not self.picking:
            return
        self.clear_points()
        self.picking = False
        if self.viewer.style.tool is self.pick_tool:
            self.viewer.style.tool = None
        self.viewer.exit_split()
        self.on_change()

    def pick(self, x, y):
        ren = self.viewer.poked_renderer(x, y)
        if ren is self.left:
            model, pts, side = self.fixed, self.pts_fixed, "fixed"
        elif ren is self.right:
            model, pts, side = self.floating, self.pts_float, "float"
        else:
            return
        wv = model.world_geometry()[0]
        hit = pick_mesh(ren, x, y, wv, model.mesh.faces)
        if hit is None:
            return
        pos = hit[1]
        pts.append(pos)
        radius = max(model.mesh.diagonal() * 0.012, 1e-3)
        self.markers.append((side, Marker(ren, pos, radius, len(pts) - 1)))
        self.viewer.render()
        self.on_change()

    def undo_point(self):
        if not self.markers:
            return
        side, mk = self.markers.pop()
        mk.remove()
        (self.pts_fixed if side == "fixed" else self.pts_float).pop()
        self.viewer.render()
        self.on_change()

    def clear_points(self):
        for _, mk in self.markers:
            mk.remove()
        self.markers.clear()
        self.pts_fixed.clear()
        self.pts_float.clear()
        if self.viewer.is_split:
            self.viewer.render()
        self.on_change()

    # ---------------------------------------------------------- alignment
    def _target(self):
        f = self.fixed
        wv = f.world_geometry()[0]
        return alignment.FixedTarget(wv, f.world_vertex_normals())

    def _apply(self, model, res: alignment.AlignResult):
        model.set_matrix(res.matrix @ model.matrix)

    def align_by_points(self, refine=True, iterations=80):
        n = len(self.pts_fixed)
        if n < 3 or n != len(self.pts_float):
            return None
        self.push_undo(self.floating)
        T = alignment.kabsch(np.array(self.pts_float), np.array(self.pts_fixed))
        res = None
        if refine:
            wv = self.floating.world_geometry()[0]
            res = alignment.best_fit(wv, self.floating.world_vertex_normals(), self._target(), init=T,
                                     iterations=iterations)
            # keep the point based result if the refinement made the point pairs much worse
            moved = alignment.transform_points(res.matrix, np.array(self.pts_float))
            err_ref = np.linalg.norm(moved - np.array(self.pts_fixed), axis=1).mean()
            moved0 = alignment.transform_points(T, np.array(self.pts_float))
            err_pts = np.linalg.norm(moved0 - np.array(self.pts_fixed), axis=1).mean()
            if err_ref > 3 * err_pts + 0.02 * self.fixed.mesh.diagonal():
                res = None
        if res is None:
            moved = alignment.transform_points(T, np.array(self.pts_float))
            rms = float(np.sqrt(np.mean(np.sum((moved - np.array(self.pts_fixed)) ** 2, axis=1))))
            res = alignment.AlignResult(T, rms, 1.0)
        self._apply(self.floating, res)
        self.stop_picking()
        return res

    def best_fit(self, iterations=80):
        wv = self.floating.world_geometry()[0]
        self.push_undo(self.floating)
        res = alignment.best_fit(wv, self.floating.world_vertex_normals(), self._target(), iterations=iterations)
        self._apply(self.floating, res)
        self.stop_picking()
        return res

    def auto_align(self, model=None, target=None):
        model = model or self.floating
        target = target or self._target()
        wv = model.world_geometry()[0]
        self.push_undo(model)
        res = alignment.auto_align(wv, model.world_vertex_normals(), target)
        self._apply(model, res)
        return res


class AlignPanel(QWidget):
    def __init__(self, controller: AlignController, models_getter, parent=None):
        super().__init__(parent)
        self.c = controller
        self.models_getter = models_getter
        lay = QVBoxLayout(self)

        form = QFormLayout()
        self.fixed_cb = QComboBox()
        self.float_cb = QComboBox()
        self.fixed_cb.currentIndexChanged.connect(self._combo_changed)
        self.float_cb.currentIndexChanged.connect(self._combo_changed)
        form.addRow(tr("fixed_model"), self.fixed_cb)
        form.addRow(tr("floating_model"), self.float_cb)
        lay.addLayout(form)

        self.pick_btn = QPushButton(tr("pick_points"))
        self.pick_btn.setCheckable(True)
        self.pick_btn.toggled.connect(self._toggle_pick)
        lay.addWidget(self.pick_btn)
        help_lbl = QLabel(tr("pick_help"))
        help_lbl.setWordWrap(True)
        help_lbl.setStyleSheet("color: gray; font-size: 11px;")
        lay.addWidget(help_lbl)
        self.points_lbl = QLabel(tr("points_status", a=0, b=0))
        lay.addWidget(self.points_lbl)
        row = QHBoxLayout()
        b = QPushButton(tr("undo_point"))
        b.clicked.connect(self.c.undo_point)
        row.addWidget(b)
        b = QPushButton(tr("clear_points"))
        b.clicked.connect(self.c.clear_points)
        row.addWidget(b)
        lay.addLayout(row)

        self.refine = QCheckBox(tr("refine"))
        self.refine.setChecked(True)
        lay.addWidget(self.refine)
        self.align_pts_btn = QPushButton(tr("align_points"))
        self.align_pts_btn.clicked.connect(self._align_points)
        lay.addWidget(self.align_pts_btn)

        lay.addSpacing(10)
        it_row = QHBoxLayout()
        it_row.addWidget(QLabel(tr("iterations")))
        self.iters = QSpinBox()
        self.iters.setRange(5, 500)
        self.iters.setValue(80)
        it_row.addWidget(self.iters)
        lay.addLayout(it_row)
        b = QPushButton(tr("best_fit"))
        b.clicked.connect(self._best_fit)
        lay.addWidget(b)
        b = QPushButton(tr("auto_align"))
        b.clicked.connect(self._auto)
        lay.addWidget(b)
        b = QPushButton(tr("auto_all"))
        b.clicked.connect(self._auto_all)
        lay.addWidget(b)

        self.result_lbl = QLabel("")
        self.result_lbl.setWordWrap(True)
        self.result_lbl.setStyleSheet("font-weight: bold;")
        lay.addWidget(self.result_lbl)
        lay.addStretch(1)

    # ----------------------------------------------------------- model lists
    def refresh_models(self):
        models = self.models_getter()
        for cb, default in ((self.fixed_cb, 0), (self.float_cb, 1)):
            current = cb.currentData()
            cb.blockSignals(True)
            cb.clear()
            for m in models:
                cb.addItem(m.name, m)
            idx = next((i for i, m in enumerate(models) if m is current), None)
            if idx is None:
                idx = min(default, len(models) - 1)
            cb.setCurrentIndex(idx)
            cb.blockSignals(False)
        self._combo_changed()

    def _combo_changed(self, *_):
        new_fixed = self.fixed_cb.currentData()
        new_float = self.float_cb.currentData()
        if self.c.picking and (new_fixed is not self.c.fixed or new_float is not self.c.floating):
            self.pick_btn.setChecked(False)
        self.c.fixed, self.c.floating = new_fixed, new_float

    def refresh(self):
        self.points_lbl.setText(tr("points_status", a=len(self.c.pts_fixed), b=len(self.c.pts_float)))
        if self.pick_btn.isChecked() != self.c.picking:
            self.pick_btn.blockSignals(True)
            self.pick_btn.setChecked(self.c.picking)
            self.pick_btn.blockSignals(False)

    # -------------------------------------------------------------- actions
    def _check_pair(self):
        if self.c.fixed is None or self.c.floating is None or self.c.fixed is self.c.floating:
            QMessageBox.information(self, tr("align_title"), tr("need_two"))
            return False
        return True

    def _toggle_pick(self, on):
        if on:
            if not self._check_pair() or not self.c.start_picking():
                self.pick_btn.blockSignals(True)
                self.pick_btn.setChecked(False)
                self.pick_btn.blockSignals(False)
        else:
            self.c.stop_picking()

    def _run(self, fn):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.result_lbl.setText(tr("working"))
        QApplication.processEvents()
        try:
            res = fn()
        finally:
            QApplication.restoreOverrideCursor()
        if res is not None:
            self.result_lbl.setText(tr("align_result", rms=res.rms, frac=res.inlier_fraction))
        else:
            self.result_lbl.setText("")
        self.c.viewer.render()
        return res

    def _align_points(self):
        if not self._check_pair():
            return
        n = len(self.c.pts_fixed)
        if n < 3 or n != len(self.c.pts_float):
            QMessageBox.information(self, tr("align_title"), tr("need_pairs"))
            return
        self._run(lambda: self.c.align_by_points(self.refine.isChecked(), self.iters.value()))

    def _best_fit(self):
        if self._check_pair():
            self._run(lambda: self.c.best_fit(self.iters.value()))

    def _auto(self):
        if self._check_pair():
            def go():
                self.c.stop_picking()
                return self.c.auto_align()
            self._run(go)

    def _auto_all(self):
        fixed = self.c.fixed
        if fixed is None:
            return
        others = [m for m in self.models_getter() if m is not fixed and m.visible]
        if not others:
            QMessageBox.information(self, tr("align_title"), tr("need_two"))
            return

        def go():
            self.c.stop_picking()
            target = self.c._target()
            res = None
            for m in others:
                res = self.c.auto_align(m, target)
            return res
        self._run(go)
