"""Main window."""
from __future__ import annotations

import os
import sys

import numpy as np
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction, QActionGroup, QColor, QKeySequence, QPalette, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .align_tool import AlignController, AlignPanel
from .cut_tool import BRUSH, LASSO, POLYGON, CutPanel, CutTool
from .i18n import set_language, tr
from .mesh import load_stl, merge_meshes, save_stl
from .model import Model
from .viewer import Viewer

UNDO_LIMIT = 30


class MainWindow(QMainWindow):
    def __init__(self, settings: QSettings):
        super().__init__()
        self.settings = settings
        self.setWindowTitle(tr("app_title"))
        self.resize(1400, 880)
        self.setAcceptDrops(True)
        self.undo_stack: list[tuple[Model, object, np.ndarray]] = []
        self._last_dir = settings.value("last_dir", "")

        self.viewer = Viewer(self)
        self.setCentralWidget(self.viewer)

        self.cut = CutTool(self.viewer, self.active_model, self.push_undo, self._tools_changed)
        self.align = AlignController(self.viewer, self.push_undo, self._tools_changed, self.statusBar().showMessage)

        self._build_models_dock()
        self._build_tools_dock()
        self._build_actions()
        self._build_shortcuts()
        self.statusBar().showMessage(tr("drop_hint"))

    # ================================================================ UI
    def _build_models_dock(self):
        dock = QDockWidget(tr("models"), self)
        dock.setObjectName("models")
        dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        w = QWidget()
        lay = QVBoxLayout(w)
        self.model_list = QListWidget()
        self.model_list.currentRowChanged.connect(self._model_selected)
        self.model_list.itemChanged.connect(self._model_item_changed)
        lay.addWidget(self.model_list)
        row = QHBoxLayout()
        self.color_btn = QPushButton(tr("color"))
        self.color_btn.clicked.connect(self._pick_color)
        row.addWidget(self.color_btn)
        rm = QPushButton(tr("remove_model"))
        rm.clicked.connect(self._remove_model)
        row.addWidget(rm)
        lay.addLayout(row)
        lay.addWidget(QLabel(tr("opacity")))
        self.opacity = QSlider(Qt.Horizontal)
        self.opacity.setRange(10, 100)
        self.opacity.setValue(100)
        self.opacity.valueChanged.connect(self._opacity_changed)
        lay.addWidget(self.opacity)
        self.info = QLabel(tr("no_model"))
        self.info.setWordWrap(True)
        lay.addWidget(self.info)
        dock.setWidget(w)
        dock.setMinimumWidth(230)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)

    def _build_tools_dock(self):
        self.tools_dock = QDockWidget(tr("cut_title"), self)
        self.tools_dock.setObjectName("tools")
        self.tools_dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        self.stack = QStackedWidget()
        self.cut_panel = CutPanel(self.cut)
        self.align_panel = AlignPanel(self.align, lambda: list(self.viewer.models))
        self.stack.addWidget(self.cut_panel)
        self.stack.addWidget(self.align_panel)
        self.tools_dock.setWidget(self.stack)
        self.tools_dock.setMinimumWidth(300)
        self.addDockWidget(Qt.RightDockWidgetArea, self.tools_dock)
        self.tools_dock.hide()

    def _act(self, text, slot, shortcut=None, checkable=False):
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        a.setCheckable(checkable)
        if checkable:
            a.toggled.connect(slot)
        else:
            a.triggered.connect(lambda _=False: slot())
        return a

    def _build_actions(self):
        mb = self.menuBar()
        tb = self.addToolBar("main")
        tb.setObjectName("main_toolbar")
        tb.setToolButtonStyle(Qt.ToolButtonTextOnly)

        a_open = self._act(tr("open"), self.open_dialog, QKeySequence.Open)
        a_save = self._act(tr("save"), self.save_model, QKeySequence.Save)
        a_merge = self._act(tr("save_merged"), self.save_merged)
        a_exit = self._act(tr("exit"), self.close)
        m = mb.addMenu(tr("menu_file"))
        for a in (a_open, a_save, a_merge):
            m.addAction(a)
        m.addSeparator()
        m.addAction(a_exit)

        a_undo = self._act(tr("undo"), self.undo, QKeySequence.Undo)
        mb.addMenu(tr("menu_edit")).addAction(a_undo)

        mv = mb.addMenu(tr("menu_view"))
        a_fit = self._act(tr("reset_view"), self.viewer.fit, "F")
        mv.addAction(a_fit)
        view_actions = []
        for name in ("front", "back", "left", "right", "top", "bottom"):
            a = self._act(tr("view_" + name), lambda n=name: self.viewer.set_view(n))
            mv.addAction(a)
            view_actions.append(a)
        mv.addSeparator()
        self.a_edges = self._act(tr("wireframe"), self._toggle_edges, "E", checkable=True)
        mv.addAction(self.a_edges)
        a_par = self._act(tr("parallel"), self.viewer.set_parallel, checkable=True)
        mv.addAction(a_par)

        self.a_cut = self._act(tr("tool_cut"), self._toggle_cut, "X", checkable=True)
        self.a_align = self._act(tr("tool_align"), self._toggle_align, "A", checkable=True)
        grp = QActionGroup(self)
        grp.setExclusionPolicy(QActionGroup.ExclusionPolicy.ExclusiveOptional)
        grp.addAction(self.a_cut)
        grp.addAction(self.a_align)
        mt = mb.addMenu(tr("menu_tools"))
        mt.addAction(self.a_cut)
        mt.addAction(self.a_align)

        mh = mb.addMenu(tr("menu_help"))
        mh.addAction(self._act(tr("shortcuts"), lambda: QMessageBox.information(self, tr("shortcuts"), tr("shortcut_text"))))
        mh.addAction(self._act(tr("about"), lambda: QMessageBox.about(self, tr("about"), tr("about_text", v=__version__))))

        for a in (a_open, a_save, a_undo):
            tb.addAction(a)
        tb.addSeparator()
        tb.addAction(a_fit)
        for a in view_actions:
            tb.addAction(a)
        tb.addSeparator()
        tb.addAction(self.a_cut)
        tb.addAction(self.a_align)

    def _build_shortcuts(self):
        def sc(key, fn):
            s = QShortcut(QKeySequence(key), self)
            s.activated.connect(fn)

        sc(Qt.Key_Delete, self._key_delete)
        sc(Qt.Key_Escape, self._key_escape)
        sc(Qt.Key_Return, self._key_enter)
        sc(Qt.Key_Enter, self._key_enter)
        sc(Qt.Key_Backspace, self._key_backspace)
        sc("B", lambda: self._cut_mode(BRUSH))
        sc("L", lambda: self._cut_mode(LASSO))
        sc("P", lambda: self._cut_mode(POLYGON))
        sc("[", lambda: self._brush_size(1 / 1.2))
        sc("]", lambda: self._brush_size(1.2))

    # ============================================================ models
    def active_model(self) -> Model | None:
        row = self.model_list.currentRow()
        if 0 <= row < len(self.viewer.models):
            return self.viewer.models[row]
        if len(self.viewer.models) == 1:
            return self.viewer.models[0]
        return None

    def open_dialog(self):
        paths, _ = QFileDialog.getOpenFileNames(self, tr("open"), self._last_dir, tr("stl_filter"))
        self.open_files(paths)

    def open_files(self, paths):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            for p in paths:
                try:
                    mesh = load_stl(p)
                except Exception as exc:  # noqa: BLE001
                    QApplication.restoreOverrideCursor()
                    QMessageBox.warning(self, tr("error"), tr("load_failed", path=p, err=exc))
                    QApplication.setOverrideCursor(Qt.WaitCursor)
                    continue
                name = os.path.splitext(os.path.basename(p))[0]
                model = Model(name, mesh, path=p)
                model.set_edges(self.a_edges.isChecked())
                self.viewer.add_model(model, fit=True)
                item = QListWidgetItem(name)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked)
                self.model_list.addItem(item)
                self.model_list.setCurrentRow(self.model_list.count() - 1)
                self._last_dir = os.path.dirname(p)
                self.settings.setValue("last_dir", self._last_dir)
                self.statusBar().showMessage(tr("loaded", name=name, faces=mesh.n_faces))
        finally:
            QApplication.restoreOverrideCursor()
        self.align_panel.refresh_models()
        self._update_info()

    def _model_selected(self, row):
        m = self.active_model()
        if m is not None:
            self.opacity.blockSignals(True)
            self.opacity.setValue(int(m.opacity * 100))
            self.opacity.blockSignals(False)
        for other in self.viewer.models:
            if other is not m and other.selection.any():
                other.clear_selection()
        self.cut.cancel()
        self._update_info()
        self.viewer.render()

    def _model_item_changed(self, item):
        row = self.model_list.row(item)
        if 0 <= row < len(self.viewer.models):
            self.viewer.models[row].set_visible(item.checkState() == Qt.Checked)
            self.viewer.render()

    def _pick_color(self):
        m = self.active_model()
        if m is None:
            return
        c = QColorDialog.getColor(QColor.fromRgbF(*m.color), self)
        if c.isValid():
            m.set_color((c.redF(), c.greenF(), c.blueF()))
            self.viewer.render()

    def _opacity_changed(self, v):
        m = self.active_model()
        if m is not None:
            m.set_opacity(v / 100.0)
            self.viewer.render()

    def _remove_model(self):
        m = self.active_model()
        if m is None:
            return
        if QMessageBox.question(self, tr("remove_model"), tr("confirm_remove", name=m.name)) != QMessageBox.Yes:
            return
        self.align.stop_picking()
        row = self.viewer.models.index(m)
        self.viewer.remove_model(m)
        self.model_list.takeItem(row)
        self.undo_stack = [u for u in self.undo_stack if u[0] is not m]
        self.align_panel.refresh_models()
        self._update_info()

    def _toggle_edges(self, on):
        for m in self.viewer.models:
            m.set_edges(on)
        self.viewer.render()

    def _update_info(self):
        m = self.active_model()
        if m is None:
            self.info.setText(tr("no_model"))
            return
        lo, hi = m.world_bounds()
        sx, sy, sz = hi - lo
        self.info.setText(tr("info", faces=m.mesh.n_faces, verts=m.mesh.n_vertices, sx=sx, sy=sy, sz=sz))

    # ============================================================ saving
    def _ask_save_path(self, default_name):
        start = os.path.join(self._last_dir or "", default_name + ".stl")
        path, _ = QFileDialog.getSaveFileName(self, tr("save"), start, tr("stl_filter"))
        if path and not path.lower().endswith(".stl"):
            path += ".stl"
        return path

    def save_model(self):
        m = self.active_model()
        if m is None:
            QMessageBox.information(self, tr("save"), tr("select_model_first"))
            return
        path = self._ask_save_path(m.name)
        if path:
            save_stl(path, m.mesh, m.matrix)
            self.statusBar().showMessage(tr("saved", path=path))

    def save_merged(self):
        visible = [m for m in self.viewer.models if m.visible]
        if not visible:
            return
        path = self._ask_save_path("merged")
        if path:
            save_stl(path, merge_meshes([m.mesh.transformed(m.matrix) for m in visible]))
            self.statusBar().showMessage(tr("saved", path=path))

    # ============================================================== undo
    def push_undo(self, model: Model):
        self.undo_stack.append((model, model.mesh, model.matrix.copy()))
        del self.undo_stack[:-UNDO_LIMIT]

    def undo(self):
        if self.cut.active and self.cut.poly3d:
            self.cut.remove_last_point()
            return
        if not self.undo_stack:
            self.statusBar().showMessage(tr("nothing_to_undo"), 3000)
            return
        model, mesh, matrix = self.undo_stack.pop()
        if model not in self.viewer.models:
            return
        if mesh is not model.mesh:
            model.set_mesh(mesh)
        model.set_matrix(matrix)
        self.viewer.render()
        self._tools_changed()

    # ============================================================= tools
    def _toggle_cut(self, on):
        if on:
            self.align.stop_picking()
            self.stack.setCurrentWidget(self.cut_panel)
            self.tools_dock.setWindowTitle(tr("cut_title"))
            self.tools_dock.show()
            self.cut.activate()
        else:
            self.cut.deactivate()
            if not self.a_align.isChecked():
                self.tools_dock.hide()

    def _toggle_align(self, on):
        if on:
            self.stack.setCurrentWidget(self.align_panel)
            self.tools_dock.setWindowTitle(tr("align_title"))
            self.tools_dock.show()
            self.align_panel.refresh_models()
        else:
            self.align.stop_picking()
            if not self.a_cut.isChecked():
                self.tools_dock.hide()

    def _tools_changed(self):
        self.cut_panel.refresh()
        self.align_panel.refresh()
        self._update_info()

    def _cut_mode(self, mode):
        if self.cut.active:
            self.cut_panel.set_mode(mode)

    def _brush_size(self, factor):
        if self.cut.active:
            self.cut.set_radius(self.cut.radius * factor)

    def _key_delete(self):
        if self.cut.active:
            self.cut.delete_selection()

    def _key_escape(self):
        if self.cut.active:
            if self.cut.poly3d or self.cut._lasso:
                self.cut.cancel()
                self.viewer.render()
            else:
                self.cut.clear()
        elif self.align.picking:
            self.align.stop_picking()

    def _key_enter(self):
        if self.cut.active:
            self.cut.close_polygon()

    def _key_backspace(self):
        if self.cut.active:
            self.cut.remove_last_point()
        elif self.align.picking:
            self.align.undo_point()

    def _set_lang(self, lang):
        self.settings.setValue("lang", lang)
        QMessageBox.information(self, tr("menu_language"), tr("restart_lang") + "\n" +
                                ("Restart to apply." if lang == "en" else "أعد التشغيل للتطبيق."))

    # ======================================================= drag & drop
    def dragEnterEvent(self, ev):
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        paths = [u.toLocalFile() for u in ev.mimeData().urls() if u.toLocalFile().lower().endswith(".stl")]
        if paths:
            self.open_files(paths)

    def closeEvent(self, ev):
        self.viewer.Finalize()
        super().closeEvent(ev)


def _apply_dark_theme(app: QApplication):
    app.setStyle("Fusion")
    pal = QPalette()
    base = QColor(43, 46, 52)
    pal.setColor(QPalette.Window, base)
    pal.setColor(QPalette.WindowText, QColor(225, 225, 225))
    pal.setColor(QPalette.Base, QColor(32, 34, 38))
    pal.setColor(QPalette.AlternateBase, base)
    pal.setColor(QPalette.ToolTipBase, QColor(255, 255, 220))
    pal.setColor(QPalette.ToolTipText, QColor(0, 0, 0))
    pal.setColor(QPalette.Text, QColor(225, 225, 225))
    pal.setColor(QPalette.Button, QColor(58, 62, 70))
    pal.setColor(QPalette.ButtonText, QColor(230, 230, 230))
    pal.setColor(QPalette.Highlight, QColor(52, 120, 200))
    pal.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor(120, 120, 120))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(120, 120, 120))
    app.setPalette(pal)


def main(argv=None):
    argv = sys.argv if argv is None else argv
    app = QApplication.instance() or QApplication(argv)
    app.setApplicationName("ProView")
    settings = QSettings("ProView", "ProView")
    set_language("en")
    _apply_dark_theme(app)
    win = MainWindow(settings)
    win.show()
    files = [a for a in argv[1:] if a.lower().endswith(".stl") and os.path.isfile(a)]
    if files:
        win.open_files(files)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
