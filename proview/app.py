"""Main window."""
from __future__ import annotations

import os
import sys

import numpy as np
from PySide6.QtCore import QEvent, QSettings, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QColor, QKeySequence, QPalette, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QSizePolicy,
    QStackedWidget,
    QToolBar,
    QToolButton,
    QWidget,
)

from . import __version__
from .align_tool import AlignController, AlignPanel
from .cut_tool import BRUSH, LASSO, POLYGON, CutPanel, CutTool
from .i18n import set_language, tr
from .icons import app_icon, icon
from .mesh import MESH_EXTENSIONS, load_mesh, merge_meshes, save_mesh
from .model import Model
from .models_panel import ModelsPanel
from .viewer import Viewer

UNDO_LIMIT = 30

TOOLBAR_STYLE = """
QToolBar#actionBar { background:#1b1d22; border:none; border-bottom:1px solid #0f1013; padding:6px 10px; spacing:6px; }
QToolBar#actionBar QToolButton { color:#e6e8ec; border:1px solid transparent; border-radius:7px; padding:4px; }
QToolBar#actionBar QToolButton:hover { background:#2a2e36; border-color:#3a404b; }
QToolBar#actionBar QToolButton[tile="true"] { background:#25282f; border:1px solid #30343c; border-radius:9px;
    min-width:66px; max-width:66px; min-height:58px; font-size:11px; padding:5px 2px 4px 2px; }
QToolBar#actionBar QToolButton[tile="true"]:hover { background:#2f343e; border-color:#4a90e2; }
QToolBar#actionBar QToolButton[tile="true"]:checked { background:#1d3a5e; border:1px solid #4aa3ff; }
QToolBar#actionBar QToolButton[tile="true"]:pressed { background:#173050; }
"""


class MainWindow(QMainWindow):
    def __init__(self, settings: QSettings):
        super().__init__()
        self.settings = settings
        self.setWindowTitle(tr("app_title"))
        self.setWindowIcon(app_icon())
        self.resize(1400, 880)
        self.setAcceptDrops(True)
        self.undo_stack: list[tuple[Model, object, np.ndarray]] = []
        self._last_dir = settings.value("last_dir", "")

        self.viewer = Viewer(self)
        self.setCentralWidget(self.viewer)

        self.cut = CutTool(self.viewer, self.active_model, self.push_undo, self._tools_changed)
        self.align = AlignController(self.viewer, self.push_undo, self._tools_changed, self.statusBar().showMessage)

        self.panel = ModelsPanel(self, self.viewer, self._models_changed, self.merge_models,
                                 self._remove_model, self._model_selected)
        self.model_list = self.panel.list
        self._build_tools_dock()
        self._build_actions()
        self._build_shortcuts()
        self.statusBar().showMessage(tr("drop_hint"))

    # ================================================================ UI
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
        self.tools_dock.visibilityChanged.connect(lambda _: QTimer.singleShot(0, self.panel.follow))

    def _act(self, text, slot, shortcut=None, checkable=False, icon_name=None):
        a = QAction(text, self)
        if icon_name:
            a.setIcon(icon(icon_name))
        tip = text.replace("...", "")
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
            tip += f"  ({QKeySequence(shortcut).toString(QKeySequence.NativeText)})"
        a.setToolTip(tip)
        a.setCheckable(checkable)
        if checkable:
            a.toggled.connect(lambda on: slot(on))
        else:
            a.triggered.connect(lambda _=False: slot())
        return a

    def _build_actions(self):
        mb = self.menuBar()
        a_open = self._act(tr("open"), self.open_dialog, QKeySequence.Open, icon_name="open")
        a_save = self._act(tr("save"), self.save_model, QKeySequence.Save, icon_name="save")
        a_export = self._act(tr("save_merged"), self.save_merged)
        a_exit = self._act(tr("exit"), self.close)
        m = mb.addMenu(tr("menu_file"))
        for a in (a_open, a_save, a_export):
            m.addAction(a)
        m.addSeparator()
        m.addAction(a_exit)

        a_undo = self._act(tr("undo"), self.undo, QKeySequence.Undo, icon_name="undo")
        mb.addMenu(tr("menu_edit")).addAction(a_undo)

        mv = mb.addMenu(tr("menu_view"))
        a_fit = self._act(tr("reset_view"), self.viewer.fit, "F", icon_name="fit")
        mv.addAction(a_fit)
        for key, name in (("1", "front"), ("2", "back"), ("3", "left"), ("4", "right"),
                          ("5", "top"), ("6", "bottom"), ("0", "iso")):
            mv.addAction(self._act(tr("view_" + name), lambda n=name: self.viewer.set_view(n), key,
                                   icon_name="view_" + name if name != "iso" else None))
        mv.addSeparator()
        self.a_edges = self._act(tr("wireframe"), self._toggle_edges, "E", checkable=True, icon_name="edges")
        mv.addAction(self.a_edges)
        self.a_colors = self._act(tr("scan_colors"), self._toggle_scan_colors, "C", checkable=True,
                                  icon_name="scan_colors")
        self.a_colors.setChecked(True)
        mv.addAction(self.a_colors)
        a_par = self._act(tr("parallel"), self.viewer.set_parallel, checkable=True)
        mv.addAction(a_par)

        self.a_cut = self._act(tr("tool_cut"), self._toggle_cut, "X", checkable=True, icon_name="cut")
        self.a_align = self._act(tr("tool_align"), self._toggle_align, "A", checkable=True, icon_name="align")
        a_merge = self._act(tr("merge"), self.merge_models, "M", icon_name="merge")
        grp = QActionGroup(self)
        grp.setExclusionPolicy(QActionGroup.ExclusionPolicy.ExclusiveOptional)
        grp.addAction(self.a_cut)
        grp.addAction(self.a_align)
        mt = mb.addMenu(tr("menu_tools"))
        for a in (self.a_cut, self.a_align, a_merge):
            mt.addAction(a)

        a_help = self._act(tr("shortcuts"), lambda: QMessageBox.information(self, tr("shortcuts"), tr("shortcut_text")),
                           icon_name="help")
        mh = mb.addMenu(tr("menu_help"))
        mh.addAction(a_help)
        mh.addAction(self._act(tr("about"), self._about))

        # action bar: file buttons on the left, big tool tiles centred
        tb = QToolBar("actions")
        tb.setObjectName("actionBar")
        tb.setMovable(False)
        tb.setFloatable(False)
        tb.setIconSize(QSize(26, 26))
        tb.setStyleSheet(TOOLBAR_STYLE)
        self.addToolBar(Qt.TopToolBarArea, tb)
        left = [a_open, a_save, a_undo]
        for a in left:
            tb.addAction(a)
        tb.addWidget(self._spacer())
        tiles = [
            (self.a_cut, tr("tile_cut")), (self.a_align, tr("tile_align")), (a_merge, tr("tile_merge")),
            (self.a_colors, tr("tile_colors")), (self.a_edges, tr("tile_edges")), (a_fit, tr("tile_fit")),
        ]
        for a, label in tiles:
            btn = QToolButton()
            btn.setDefaultAction(a)
            btn.setText(label)
            btn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            btn.setIconSize(QSize(28, 28))
            btn.setProperty("tile", True)
            a.changed.connect(lambda b=btn, t=label: b.setText(t))
            tb.addWidget(btn)
        tb.addWidget(self._spacer())
        tb.addAction(a_help)
        # balance the left group so the tiles stay centred
        pad = QWidget()
        pad.setFixedWidth(2 * 40)
        tb.addWidget(pad)

    @staticmethod
    def _spacer():
        w = QWidget()
        w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        return w

    def _about(self):
        box = QMessageBox(self)
        box.setWindowTitle(tr("about"))
        box.setIconPixmap(app_icon().pixmap(96, 96))
        box.setText(tr("about_text", v=__version__))
        box.exec()

    def _build_shortcuts(self):
        def sc(key, fn):
            s = QShortcut(QKeySequence(key), self)
            s.activated.connect(lambda: fn())

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

    # ============================================== floating panel tracking
    def showEvent(self, ev):
        super().showEvent(ev)
        QTimer.singleShot(0, self._show_panel)

    def _show_panel(self):
        self.panel.show()
        self.panel.follow()

    def moveEvent(self, ev):
        super().moveEvent(ev)
        self.panel.follow()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        QTimer.singleShot(0, self.panel.follow)

    def changeEvent(self, ev):
        super().changeEvent(ev)
        if ev.type() == QEvent.WindowStateChange:
            if self.isMinimized():
                self.panel.hide()
            else:
                QTimer.singleShot(0, self._show_panel)

    # ============================================================ models
    def active_model(self) -> Model | None:
        row = self.model_list.currentRow()
        if 0 <= row < len(self.viewer.models):
            return self.viewer.models[row]
        if len(self.viewer.models) == 1:
            return self.viewer.models[0]
        return None

    def open_dialog(self):
        paths, _ = QFileDialog.getOpenFileNames(self, tr("open"), self._last_dir, tr("mesh_filter"))
        self.open_files(paths)

    def open_files(self, paths):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            for p in paths:
                try:
                    mesh = load_mesh(p)
                except Exception as exc:  # noqa: BLE001
                    QApplication.restoreOverrideCursor()
                    QMessageBox.warning(self, tr("error"), tr("load_failed", path=p, err=exc))
                    QApplication.setOverrideCursor(Qt.WaitCursor)
                    continue
                name = os.path.splitext(os.path.basename(p))[0]
                self._add_model(Model(name, mesh, path=p))
                self._last_dir = os.path.dirname(p)
                self.settings.setValue("last_dir", self._last_dir)
                self.statusBar().showMessage(tr("loaded", name=name, faces=mesh.n_faces))
        finally:
            QApplication.restoreOverrideCursor()
        self.align_panel.refresh_models()
        self._update_info()

    def _add_model(self, model: Model):
        model.set_edges(self.a_edges.isChecked())
        model.set_show_colors(self.a_colors.isChecked())
        self.viewer.add_model(model, fit=True)
        self.panel.add_model(model)

    def merge_models(self):
        """Combine the selected models (or all visible ones) into one new model."""
        parts = [self.viewer.models[r] for r in self.panel.selected_rows()]
        if len(parts) < 2:
            parts = [m for m in self.viewer.models if m.visible]
        if len(parts) < 2:
            QMessageBox.information(self, tr("merge"), tr("merge_need"))
            return
        self.cut.cancel()
        self.align.stop_picking()
        for m in parts:
            m.clear_selection()
        mesh = merge_meshes([m.mesh.transformed(m.matrix) for m in parts], [m.color for m in parts])
        names = " + ".join(m.name for m in parts)
        name = "Merged - " + names if len(names) < 60 else f"Merged ({len(parts)} models)"
        for m in parts:
            m.set_visible(False)
        self._add_model(Model(name, mesh, color=parts[0].color))
        self.panel.refresh_rows()
        self.align_panel.refresh_models()
        self._update_info()
        self.statusBar().showMessage(tr("merge_done", n=len(parts), faces=mesh.n_faces))

    def _model_selected(self, row):
        m = self.active_model()
        for other in self.viewer.models:
            if other is not m and other.selection.any():
                other.clear_selection()
        self.cut.cancel()
        self._update_info()
        self.viewer.render()

    def _models_changed(self):
        self.align_panel.refresh_models()
        self._update_info()

    def _remove_model(self):
        m = self.active_model()
        if m is None:
            return
        if QMessageBox.question(self, tr("remove_model"), tr("confirm_remove", name=m.name)) != QMessageBox.Yes:
            return
        self.align.stop_picking()
        row = self.viewer.models.index(m)
        self.viewer.remove_model(m)
        self.panel.remove_row(row)
        self.undo_stack = [u for u in self.undo_stack if u[0] is not m]
        self.align_panel.refresh_models()
        self._update_info()

    def _toggle_edges(self, on):
        for m in self.viewer.models:
            m.set_edges(on)
        self.viewer.render()

    def _toggle_scan_colors(self, on):
        for m in self.viewer.models:
            m.set_show_colors(on)
        self.panel.refresh_rows()
        self.viewer.render()

    def _update_info(self):
        m = self.active_model()
        if m is None:
            self.panel.info.setText(tr("no_model"))
            return
        lo, hi = m.world_bounds()
        sx, sy, sz = hi - lo
        self.panel.info.setText(tr("info", faces=m.mesh.n_faces, verts=m.mesh.n_vertices, sx=sx, sy=sy, sz=sz))

    # ============================================================ saving
    def _ask_save_path(self, default_name, colored=False):
        start = os.path.join(self._last_dir or "", default_name + (".ply" if colored else ".stl"))
        filt = tr("save_filter")
        if colored:  # offer PLY first so the scan colors are kept
            filt = ";;".join(reversed(filt.split(";;")))
        path, chosen = QFileDialog.getSaveFileName(self, tr("save"), start, filt)
        if path and not path.lower().endswith(MESH_EXTENSIONS):
            path += ".ply" if "ply" in chosen.lower() else ".stl"
        return path

    def save_model(self):
        m = self.active_model()
        if m is None:
            QMessageBox.information(self, tr("save"), tr("select_model_first"))
            return
        path = self._ask_save_path(m.name, m.has_colors)
        if path:
            save_mesh(path, m.mesh, m.matrix)
            self.statusBar().showMessage(tr("saved", path=path))

    def save_merged(self):
        visible = [m for m in self.viewer.models if m.visible]
        if not visible:
            return
        path = self._ask_save_path("merged", any(m.has_colors for m in visible))
        if path:
            save_mesh(path, merge_meshes([m.mesh.transformed(m.matrix) for m in visible], [m.color for m in visible]))
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

    # ======================================================= drag & drop
    def dragEnterEvent(self, ev):
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        paths = [u.toLocalFile() for u in ev.mimeData().urls() if u.toLocalFile().lower().endswith(MESH_EXTENSIONS)]
        if paths:
            self.open_files(paths)

    def closeEvent(self, ev):
        self.panel.close()
        self.viewer.Finalize()
        super().closeEvent(ev)


def _apply_dark_theme(app: QApplication):
    app.setStyle("Fusion")
    pal = QPalette()
    base = QColor(36, 39, 44)
    pal.setColor(QPalette.Window, base)
    pal.setColor(QPalette.WindowText, QColor(225, 225, 225))
    pal.setColor(QPalette.Base, QColor(28, 30, 34))
    pal.setColor(QPalette.AlternateBase, base)
    pal.setColor(QPalette.ToolTipBase, QColor(30, 32, 36))
    pal.setColor(QPalette.ToolTipText, QColor(230, 230, 230))
    pal.setColor(QPalette.Text, QColor(225, 225, 225))
    pal.setColor(QPalette.Button, QColor(52, 56, 64))
    pal.setColor(QPalette.ButtonText, QColor(230, 230, 230))
    pal.setColor(QPalette.Highlight, QColor(52, 120, 200))
    pal.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor(120, 120, 120))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(120, 120, 120))
    app.setPalette(pal)
    app.setStyleSheet("QToolTip { border:1px solid #3a3f48; padding:4px; }")


def main(argv=None):
    from . import diagnostics

    argv = sys.argv if argv is None else argv
    diagnostics.setup()
    diagnostics.log("starting")
    if sys.platform == "win32":  # own taskbar icon instead of the python one
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ProView.STLViewer")
        except Exception:  # noqa: BLE001
            pass
    app = QApplication.instance() or QApplication(argv)
    diagnostics.log("QApplication created")
    diagnostics.route_vtk_messages()
    app.setApplicationName("ProView")
    app.setWindowIcon(app_icon())
    settings = QSettings("ProView", "ProView")
    set_language("en")
    _apply_dark_theme(app)
    win = MainWindow(settings)
    diagnostics.log("main window created")
    win.show()
    diagnostics.log("main window shown")
    if "--selftest" in argv:
        i = argv.index("--selftest")
        out = argv[i + 1] if len(argv) > i + 1 else "selftest.png"
        QTimer.singleShot(1500, lambda: diagnostics.run_selftest(win, app, out))
        return app.exec()
    files = [a for a in argv[1:] if a.lower().endswith(MESH_EXTENSIONS) and os.path.isfile(a)]
    if files:
        win.open_files(files)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
