"""Crash logging and a self-test used by CI on Windows.

The windowed exe has no console, so errors would otherwise vanish. Everything
goes to %LOCALAPPDATA%\\ProView\\proview.log (or ~/.proview/proview.log).
"""
from __future__ import annotations

import datetime
import faulthandler
import os
import platform
import sys
import traceback

_log_file = None


def log_path() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".proview")
    folder = os.path.join(base, "ProView")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "proview.log")


def log(msg: str) -> None:
    if _log_file is not None:
        _log_file.write(f"[{datetime.datetime.now():%H:%M:%S}] {msg}\n")
        _log_file.flush()


def setup() -> None:
    """Start the log, catch Python exceptions and native crashes."""
    global _log_file
    try:
        _log_file = open(log_path(), "w", encoding="utf-8", buffering=1)
    except OSError:
        return
    from . import __version__

    log(f"ProView {__version__} | Python {sys.version.split()[0]} | {platform.platform()} | "
        f"frozen={getattr(sys, 'frozen', False)}")
    faulthandler.enable(_log_file)  # native crashes (e.g. in the OpenGL driver)

    # windowed exe: stdout/stderr are None, give them somewhere to go
    if sys.stdout is None:
        sys.stdout = _log_file
    if sys.stderr is None:
        sys.stderr = _log_file

    def hook(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        log("UNHANDLED EXCEPTION\n" + text)
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox

            if QApplication.instance() is not None:
                QMessageBox.critical(None, "ProView error",
                                     f"{exc_type.__name__}: {exc}\n\nDetails were saved to:\n{log_path()}")
        except Exception:  # noqa: BLE001
            pass

    sys.excepthook = hook


def route_vtk_messages() -> None:
    """Send VTK warnings to the log instead of VTK's pop-up window on Windows."""
    try:
        from vtkmodules.vtkCommonCore import vtkFileOutputWindow, vtkOutputWindow

        win = vtkFileOutputWindow()
        win.SetFileName(log_path() + ".vtk.txt")
        vtkOutputWindow.SetInstance(win)
    except Exception as exc:  # noqa: BLE001
        log(f"could not redirect VTK output: {exc}")


def run_selftest(win, app, out_png: str) -> None:
    """Exercise the main features, save a screenshot and quit (exit code 0 = ok)."""
    import numpy as np

    from .mesh import Mesh
    from .model import Model

    try:
        log("selftest: start")
        u, v = np.meshgrid(np.linspace(0, 2 * np.pi, 60, endpoint=False), np.linspace(0.1, np.pi - 0.1, 40))
        r = 10 + 2 * np.sin(3 * u) * np.sin(v)
        pts = np.stack([r * np.cos(u) * np.sin(v), r * np.sin(u) * np.sin(v), r * np.cos(v)], -1).reshape(-1, 3)
        faces = []
        for i in range(39):
            for j in range(60):
                a, b = i * 60 + j, i * 60 + (j + 1) % 60
                faces += [(a, a + 60, b), (b, a + 60, b + 60)]
        colors = (np.abs(pts) * 20).clip(0, 255).astype(np.uint8)
        win._add_model(Model("selftest", Mesh(pts, np.array(faces), colors)))
        win._add_model(Model("selftest2", Mesh(pts + 25, np.array(faces))))
        log("selftest: models added")
        win.viewer.models[1].set_opacity(0.5)
        for name in ("front", "top", "iso"):
            win.viewer.set_view(name, animate=False)
        win.viewer.cube.hover(0, 0)
        log("selftest: views ok")
        win.a_cut.setChecked(True)
        win.cut._prepare(win.viewer.models[0])
        win.a_cut.setChecked(False)
        log("selftest: cut prepare ok")
        win.a_section.setChecked(True)
        w, h = win.viewer.rw.GetSize()
        win.section.tool.on_press(int(w * 0.2), h // 2, False, False, 0)
        win.section.tool.on_move(w // 2, h // 2, False, False)
        win.section.tool.on_release(int(w * 0.8), h // 2, False, False)
        assert win.section.curves, "section produced no curves"
        win.section_panel.refresh_view()
        win.a_section.setChecked(False)
        log("selftest: section ok")
        win.a_flat.setChecked(True)
        win.a_flat.setChecked(False)
        win.model_list.setCurrentRow(0)
        win.a_orient.setChecked(True)
        win.orient.rotate_step(2, 15)
        win.orient.drop_to_plane()
        win.orient.cancel()
        win.a_orient.setChecked(False)
        log("selftest: flat + orientation ok")
        win.model_list.selectAll()
        win.merge_models()
        log("selftest: merge ok")
        win.viewer.screenshot(out_png)
        log("selftest: PASSED")
        app.exit(0)
    except Exception:  # noqa: BLE001
        log("selftest: FAILED\n" + traceback.format_exc())
        app.exit(1)
