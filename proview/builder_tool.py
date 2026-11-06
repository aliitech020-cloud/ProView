"""Panel for the model builder (scan -> printable, optionally hollow honeycomb model)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .i18n import tr
from .model_builder import BuildError, BuildOptions, build_model

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
    def __init__(self, get_model, add_result, status, parent=None):
        super().__init__(parent)
        self.get_model = get_model
        self.add_result = add_result
        self.status = status
        lay = QVBoxLayout(self)
        self.model_lbl = QLabel("")
        self.model_lbl.setStyleSheet("font-weight:bold;")
        lay.addWidget(self.model_lbl)
        help_lbl = QLabel(tr("builder_help"))
        help_lbl.setWordWrap(True)
        help_lbl.setStyleSheet("color: gray; font-size: 11px;")
        lay.addWidget(help_lbl)

        form = QFormLayout()
        d = BuildOptions()
        self.base = _spin(d.base_height, 0.5, 40, 0.5)
        form.addRow(tr("builder_base"), self.base)
        self.hollow = QCheckBox(tr("builder_hollow"))
        self.hollow.setChecked(d.hollow)
        form.addRow(self.hollow)
        self.wall = _spin(d.wall, 0.8, 10, 0.1)
        form.addRow(tr("builder_wall"), self.wall)
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
        lay.addLayout(form)

        self.hollow.toggled.connect(lambda _on: self._enable())
        self.honey.toggled.connect(lambda _on: self._enable())
        self._enable()

        self.go = QPushButton(tr("builder_go"))
        self.go.setStyleSheet("QPushButton { background:#2c6ed5; color:white; font-weight:bold; padding:8px; }")
        self.go.clicked.connect(lambda _=False: self.build())
        lay.addWidget(self.go)
        self.result_lbl = QLabel("")
        self.result_lbl.setWordWrap(True)
        lay.addWidget(self.result_lbl)
        lay.addStretch(1)

    def _enable(self):
        h = self.hollow.isChecked()
        self.wall.setEnabled(h)
        self.honey.setEnabled(h)
        for w in (self.cell, self.rib):
            w.setEnabled(h and self.honey.isChecked())

    def refresh(self):
        m = self.get_model()
        self.model_lbl.setText(tr("orient_model", name=m.name) if m is not None else tr("select_model_first"))
        self.go.setEnabled(m is not None)

    def options(self) -> BuildOptions:
        return BuildOptions(
            base_height=self.base.value(), hollow=self.hollow.isChecked(), wall=self.wall.value(),
            honeycomb=self.honey.isChecked(), cell=self.cell.value(), rib=self.rib.value(),
            voxel=float(self.quality.currentData()))

    def build(self):
        m = self.get_model()
        if m is None:
            return
        scan = m.mesh.transformed(m.matrix)

        def progress(text):
            self.status(f"{tr('builder_title')}: {text}...")
            self.result_lbl.setText(f"{text}...")
            QApplication.processEvents()

        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.go.setEnabled(False)
        try:
            result = build_model(scan, self.options(), progress)
        except BuildError as exc:
            QApplication.restoreOverrideCursor()
            self.result_lbl.setText("")
            QMessageBox.warning(self, tr("builder_title"), str(exc))
            return
        except MemoryError:
            QApplication.restoreOverrideCursor()
            self.result_lbl.setText("")
            QMessageBox.warning(self, tr("builder_title"), tr("builder_memory"))
            return
        except Exception as exc:  # noqa: BLE001
            import traceback

            from .diagnostics import log

            log("model builder failed\n" + traceback.format_exc())
            QApplication.restoreOverrideCursor()
            self.result_lbl.setText("")
            QMessageBox.warning(self, tr("builder_title"), f"{type(exc).__name__}: {exc}")
            return
        finally:
            self.go.setEnabled(True)
        QApplication.restoreOverrideCursor()
        self.add_result(m, result)
        self.result_lbl.setText(tr("builder_done", faces=result.n_faces))
        self.status(tr("builder_done", faces=result.n_faces))
