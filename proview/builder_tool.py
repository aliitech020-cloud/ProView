"""Panel for the model builder (scan -> printable, optionally hollow honeycomb model) and scan repair."""
from __future__ import annotations

from PySide6.QtCore import Qt
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
from .model_builder import BuildError, BuildOptions, boundary_loops, build_models
from .repair import fill_holes, loop_size

QUALITY = [("quality_fine", 0.15), ("quality_normal", 0.2), ("quality_fast", 0.3)]


def _spin(value, lo, hi, step, suffix=" mm", decimals=1):
    sb = QDoubleSpinBox()
    sb.setRange(lo, hi)
    sb.setSingleStep(step)
    sb.setDecimals(decimals)
    sb.setValue(value)
    sb.setSuffix(suffix)
    return sb


class BuilderPanel(QWidget):
    def __init__(self, get_models, add_result, status, push_undo, on_change, parent=None):
        super().__init__(parent)
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
        self.hole_max = _spin(10.0, 0.5, 200, 1.0)
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
        d = BuildOptions()
        self.auto = QCheckBox(tr("builder_auto"))
        self.auto.setChecked(d.auto_orient)
        form.addRow(self.auto)
        self.trim = QCheckBox(tr("builder_trim"))
        self.trim.setChecked(d.trim)
        self.trim.setToolTip(tr("builder_trim_tip"))
        form.addRow(self.trim)
        self.trim_off = _spin(d.trim_offset, -20, 30, 0.5)
        self.trim_off.setToolTip(tr("builder_trim_tip"))
        form.addRow(tr("builder_trim_level"), self.trim_off)
        self.trim.toggled.connect(lambda on: self.trim_off.setEnabled(on))
        self.base = _spin(d.base_height, 0.5, 40, 0.5)
        form.addRow(tr("builder_base"), self.base)
        self.edge = _spin(d.edge_smooth, 0.0, 10, 0.5)
        form.addRow(tr("builder_edge"), self.edge)
        self.hollow = QCheckBox(tr("builder_hollow"))
        self.hollow.setChecked(d.hollow)
        form.addRow(self.hollow)
        self.wall = _spin(d.wall, 0.8, 10, 0.1)
        form.addRow(tr("builder_wall"), self.wall)
        self.inner = _spin(d.inner_smooth, 0.0, 15, 0.5)
        form.addRow(tr("builder_inner"), self.inner)
        self.honey = QCheckBox(tr("builder_honeycomb"))
        self.honey.setChecked(d.honeycomb)
        form.addRow(self.honey)
        self.cell = _spin(d.cell, 2, 30, 0.5)
        form.addRow(tr("builder_cell"), self.cell)
        self.rib = _spin(d.rib, 0.4, 5, 0.1)
        form.addRow(tr("builder_rib"), self.rib)
        self.quality = QComboBox()
        for key, h in QUALITY:
            self.quality.addItem(f"{tr(key)}  ({h:g} mm)", h)
        self.quality.setCurrentIndex(1)
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

        def progress(text):
            self.status(f"{tr('builder_title')}: {text}...")
            self.result_lbl.setText(f"{text}...")
            QApplication.processEvents()

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
            self.result_lbl.setText(tr("builder_done", n=made, faces=faces))
            self.status(tr("builder_done", n=made, faces=faces))
        self.refresh()
