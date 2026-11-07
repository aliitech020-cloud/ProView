"""Panel for the model builder (scan -> printable, optionally hollow honeycomb model) and scan repair."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .i18n import tr
from .model_builder import BuildError, BuildOptions, base_frame, boundary_loops, build_models
from .repair import fill_holes, loop_size

QUALITY = [("quality_fine", 0.15), ("quality_normal", 0.2), ("quality_fast", 0.3)]

# defaults (the values the lab uses); the last used values are remembered
DEFAULTS = dict(hole_max=10.0, auto=True, trim=True, trim_offset=0.0, base=3.0, edge=1.0, hollow=True,
                wall=2.5, inner=5.0, honey=False, cell=6.0, rib=1.0, quality=0)


class TrimPreview:
    """Orange translucent plane showing where the scan will be trimmed / the base starts."""

    def __init__(self, viewer):
        from vtkmodules.vtkFiltersSources import vtkPlaneSource
        from vtkmodules.vtkRenderingCore import vtkActor, vtkPolyDataMapper

        self.viewer = viewer
        self.src = vtkPlaneSource()
        mapper = vtkPolyDataMapper()
        mapper.SetInputConnection(self.src.GetOutputPort())
        self.actor = vtkActor()
        self.actor.SetMapper(mapper)
        p = self.actor.GetProperty()
        p.SetColor(1.0, 0.55, 0.15)
        p.SetOpacity(0.35)
        p.SetLighting(False)
        self.actor.PickableOff()
        self.shown = False
        self._cache = {}

    def show(self, models, opts):
        planes = []
        for m in models:
            key = (id(m.mesh), m.matrix.tobytes(), opts.auto_orient)
            if key not in self._cache:
                scan = m.mesh.transformed(m.matrix)
                try:
                    R, main, _ = base_frame(scan, BuildOptions(auto_orient=opts.auto_orient, trim=False))
                except Exception:  # noqa: BLE001
                    continue
                vl = scan.vertices @ R.T
                self._cache = {key: (R, vl[main][:, 2], vl.min(0), vl.max(0))}
            R, edge_h, lo, hi = self._cache[key]
            z = float(np.quantile(edge_h, 0.2)) + opts.trim_offset
            pad = 0.08 * float(np.linalg.norm(hi[:2] - lo[:2]))
            corners = np.array([[lo[0] - pad, lo[1] - pad, z], [hi[0] + pad, lo[1] - pad, z],
                                [lo[0] - pad, hi[1] + pad, z]]) @ R  # back to world
            planes.append(corners)
            break  # one preview plane (the first selected model)
        if not planes:
            self.hide()
            return
        o, p1, p2 = planes[0]
        self.src.SetOrigin(*o)
        self.src.SetPoint1(*p1)
        self.src.SetPoint2(*p2)
        self.src.Modified()
        if not self.shown:
            self.viewer.ren.AddActor(self.actor)
            self.shown = True
        self.viewer.render()

    def hide(self):
        if self.shown:
            self.viewer.ren.RemoveActor(self.actor)
            self.shown = False
            self.viewer.render()


def _spin(value, lo, hi, step, suffix=" mm", decimals=1):
    sb = QDoubleSpinBox()
    sb.setRange(lo, hi)
    sb.setSingleStep(step)
    sb.setDecimals(decimals)
    sb.setValue(value)
    sb.setSuffix(suffix)
    return sb


class BuilderPanel(QWidget):
    def __init__(self, get_models, add_result, status, push_undo, on_change, viewer=None, settings=None,
                 parent=None):
        super().__init__(parent)
        self.settings = settings
        self.preview = TrimPreview(viewer) if viewer is not None else None
        self.active = False
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(lambda: self.update_preview())
        self.get_models = get_models  # selected models (or the active one)
        self.add_result = add_result
        self.status = status
        self.push_undo = push_undo
        self.on_change = on_change
        lay = QVBoxLayout(self)
        self.model_lbl = QLabel("")
        self.model_lbl.setWordWrap(True)
        self.model_lbl.setStyleSheet("font-weight:bold;")
        lay.addWidget(self.model_lbl)

        # ---------------- repair
        rep = QGroupBox(tr("repair_title"))
        rl = QVBoxLayout(rep)
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("repair_max")))
        self.hole_max = _spin(self._saved("hole_max"), 0.5, 200, 1.0)
        row.addWidget(self.hole_max)
        rl.addLayout(row)
        self.holes_lbl = QLabel("")
        self.holes_lbl.setStyleSheet("color:#aab0bb; font-size:11px;")
        self.holes_lbl.setWordWrap(True)
        rl.addWidget(self.holes_lbl)
        b = QPushButton(tr("repair_go"))
        b.clicked.connect(lambda _=False: self.fill())
        rl.addWidget(b)
        self.hole_max.valueChanged.connect(lambda _v: self.refresh())
        lay.addWidget(rep)

        # ---------------- builder
        box = QGroupBox(tr("builder_title"))
        bl = QVBoxLayout(box)
        help_lbl = QLabel(tr("builder_help"))
        help_lbl.setWordWrap(True)
        help_lbl.setStyleSheet("color: gray; font-size: 11px;")
        bl.addWidget(help_lbl)
        form = QFormLayout()
        self.auto = QCheckBox(tr("builder_auto"))
        self.auto.setChecked(self._saved("auto"))
        form.addRow(self.auto)
        self.trim = QCheckBox(tr("builder_trim"))
        self.trim.setChecked(self._saved("trim"))
        self.trim.setToolTip(tr("builder_trim_tip"))
        form.addRow(self.trim)
        self.trim_off = _spin(self._saved("trim_offset"), -20, 30, 0.5)
        self.trim_off.setToolTip(tr("builder_trim_tip"))
        form.addRow(tr("builder_trim_level"), self.trim_off)
        self.trim.toggled.connect(lambda on: (self.trim_off.setEnabled(on), self._schedule_preview()))
        self.trim_off.setEnabled(self.trim.isChecked())
        self.trim_off.valueChanged.connect(lambda _v: self._schedule_preview())
        self.auto.toggled.connect(lambda _on: self._schedule_preview())
        self.base = _spin(self._saved("base"), 0.5, 40, 0.5)
        form.addRow(tr("builder_base"), self.base)
        self.edge = _spin(self._saved("edge"), 0.0, 10, 0.5)
        form.addRow(tr("builder_edge"), self.edge)
        self.hollow = QCheckBox(tr("builder_hollow"))
        self.hollow.setChecked(self._saved("hollow"))
        form.addRow(self.hollow)
        self.wall = _spin(self._saved("wall"), 0.8, 10, 0.1)
        form.addRow(tr("builder_wall"), self.wall)
        self.inner = _spin(self._saved("inner"), 0.0, 15, 0.5)
        form.addRow(tr("builder_inner"), self.inner)
        self.honey = QCheckBox(tr("builder_honeycomb"))
        self.honey.setChecked(self._saved("honey"))
        form.addRow(self.honey)
        self.cell = _spin(self._saved("cell"), 2, 30, 0.5)
        form.addRow(tr("builder_cell"), self.cell)
        self.rib = _spin(self._saved("rib"), 0.4, 5, 0.1)
        form.addRow(tr("builder_rib"), self.rib)
        self.quality = QComboBox()
        for key, h in QUALITY:
            self.quality.addItem(f"{tr(key)}  ({h:g} mm)", h)
        self.quality.setCurrentIndex(int(self._saved("quality")))
        form.addRow(tr("builder_quality"), self.quality)
        bl.addLayout(form)
        self.hollow.toggled.connect(lambda _on: self._enable())
        self.honey.toggled.connect(lambda _on: self._enable())
        self._enable()

        self.go = QPushButton(tr("builder_go"))
        self.go.setStyleSheet("QPushButton { background:#2c6ed5; color:white; font-weight:bold; padding:8px; }")
        self.go.clicked.connect(lambda _=False: self.build())
        bl.addWidget(self.go)
        lay.addWidget(box)
        self.result_lbl = QLabel("")
        self.result_lbl.setWordWrap(True)
        lay.addWidget(self.result_lbl)
        lay.addStretch(1)

    # ------------------------------------------------------------------ settings
    def _saved(self, key):
        default = DEFAULTS[key]
        if self.settings is None:
            return default
        value = self.settings.value(f"builder/{key}", default)
        if isinstance(default, bool):
            return value in (True, "true", "1", 1)
        if isinstance(default, int):
            return int(value)
        return float(value)

    def _save(self):
        if self.settings is None:
            return
        values = dict(hole_max=self.hole_max.value(), auto=self.auto.isChecked(), trim=self.trim.isChecked(),
                      trim_offset=self.trim_off.value(), base=self.base.value(), edge=self.edge.value(),
                      hollow=self.hollow.isChecked(), wall=self.wall.value(), inner=self.inner.value(),
                      honey=self.honey.isChecked(), cell=self.cell.value(), rib=self.rib.value(),
                      quality=self.quality.currentIndex())
        for k, v in values.items():
            self.settings.setValue(f"builder/{k}", v)

    # ------------------------------------------------------------------ preview
    def set_active(self, on):
        self.active = on
        if on:
            self._schedule_preview()
        elif self.preview is not None:
            self.preview.hide()

    def _schedule_preview(self):
        if self.active:
            self._preview_timer.start(250)

    def update_preview(self):
        if self.preview is None or not self.active:
            return
        models = self.get_models()
        if not models or not self.trim.isChecked():
            self.preview.hide()
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.preview.show(models, self.options())
        finally:
            QApplication.restoreOverrideCursor()

    def _enable(self):
        h = self.hollow.isChecked()
        for w in (self.wall, self.inner, self.honey):
            w.setEnabled(h)
        for w in (self.cell, self.rib):
            w.setEnabled(h and self.honey.isChecked())

    def refresh(self):
        models = self.get_models()
        if not models:
            self.model_lbl.setText(tr("select_model_first"))
            self.holes_lbl.setText("")
        else:
            names = ", ".join(m.name for m in models)
            self.model_lbl.setText(tr("orient_model", name=names))
            small = big = 0
            for m in models:
                loops = boundary_loops(m.mesh.faces) if m.mesh.n_faces else []
                if loops:
                    main = max(loops, key=len)
                    for lp in loops:
                        if lp is main:
                            continue
                        if loop_size(m.mesh.vertices, lp) <= self.hole_max.value():
                            small += 1
                        else:
                            big += 1
            self.holes_lbl.setText(tr("repair_found", small=small, big=big))
        self.go.setEnabled(bool(models))
        self._schedule_preview()

    def options(self) -> BuildOptions:
        return BuildOptions(
            base_height=self.base.value(), hollow=self.hollow.isChecked(), wall=self.wall.value(),
            honeycomb=self.honey.isChecked(), cell=self.cell.value(), rib=self.rib.value(),
            voxel=float(self.quality.currentData()), edge_smooth=self.edge.value(),
            inner_smooth=self.inner.value(), auto_orient=self.auto.isChecked(),
            trim=self.trim.isChecked(), trim_offset=self.trim_off.value())

    # ------------------------------------------------------------------ repair
    def fill(self):
        models = self.get_models()
        if not models:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        total = 0
        try:
            for m in models:
                loops = boundary_loops(m.mesh.faces)
                keep = max(loops, key=len) if loops else None
                fixed, filled, _ = fill_holes(m.mesh, self.hole_max.value(), keep=keep)
                if filled:
                    self.push_undo(m)
                    m.set_mesh(fixed)
                    total += filled
        finally:
            QApplication.restoreOverrideCursor()
        self.result_lbl.setText(tr("repair_done", n=total))
        self.status(tr("repair_done", n=total))
        self.on_change()
        self.refresh()

    # ------------------------------------------------------------------ build
    def build(self):
        models = self.get_models()
        if not models:
            return

        warnings = []

        def progress(text):
            if text.startswith("!"):
                warnings.append(text[1:].strip())
                return
            self.status(f"{tr('builder_title')}: {text}...")
            self.result_lbl.setText(f"{text}...")
            QApplication.processEvents()

        self._save()
        if self.preview is not None:
            self.preview.hide()

        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.go.setEnabled(False)
        made = 0
        faces = 0
        try:
            for m in models:
                scan = m.mesh.transformed(m.matrix)
                prefix = f"{m.name}: " if len(models) > 1 else ""
                results = build_models(scan, self.options(), lambda t, p=prefix: progress(p + t))
                for i, r in enumerate(results):
                    self.add_result(m, r, i + 1 if len(results) > 1 else None)
                    made += 1
                    faces += r.n_faces
        except BuildError as exc:
            self.result_lbl.setText("")
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, tr("builder_title"), str(exc))
            QApplication.setOverrideCursor(Qt.WaitCursor)
        except MemoryError:
            self.result_lbl.setText("")
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, tr("builder_title"), tr("builder_memory"))
            QApplication.setOverrideCursor(Qt.WaitCursor)
        except Exception as exc:  # noqa: BLE001
            import traceback

            from .diagnostics import log

            log("model builder failed\n" + traceback.format_exc())
            self.result_lbl.setText("")
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, tr("builder_title"), f"{type(exc).__name__}: {exc}")
            QApplication.setOverrideCursor(Qt.WaitCursor)
        finally:
            QApplication.restoreOverrideCursor()
            self.go.setEnabled(True)
        if made:
            text = tr("builder_done", n=made, faces=faces)
            if warnings:
                text += "\n\n⚠ " + "\n⚠ ".join(dict.fromkeys(warnings))
            self.result_lbl.setText(text)
            self.status(tr("builder_done", n=made, faces=faces))
            if warnings:
                QMessageBox.warning(self, tr("builder_title"), "\n".join(dict.fromkeys(warnings)))
        self.refresh()
