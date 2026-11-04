"""VTK 3D view embedded in Qt, with a tool-aware interactor style."""
from __future__ import annotations

import numpy as np
import vtkmodules.qt

vtkmodules.qt.PyQtImpl = "PySide6"

# VTK factory overrides (OpenGL rendering, interaction, text)
import vtkmodules.vtkInteractionStyle  # noqa: F401,E402
import vtkmodules.vtkRenderingFreeType  # noqa: F401,E402
import vtkmodules.vtkRenderingOpenGL2  # noqa: F401,E402
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor  # noqa: E402
from vtkmodules.vtkCommonCore import vtkPoints  # noqa: E402
from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData  # noqa: E402
from vtkmodules.vtkInteractionStyle import vtkInteractorStyleTrackballCamera  # noqa: E402
from vtkmodules.vtkRenderingCore import (  # noqa: E402
    vtkActor2D,
    vtkPolyDataMapper2D,
    vtkRenderer,
)


class ViewerStyle(vtkInteractorStyleTrackballCamera):
    """Trackball camera; an active tool gets first refusal on mouse events.

    Without a tool: left = rotate. With a tool: left goes to the tool.
    Right drag always rotates, middle drag pans, wheel zooms.
    """

    def __init__(self):
        super().__init__()
        self.tool = None
        self.viewer = None
        self._right_rotating = False
        self.AddObserver("LeftButtonPressEvent", self._left_down)
        self.AddObserver("LeftButtonReleaseEvent", self._left_up)
        self.AddObserver("RightButtonPressEvent", self._right_down)
        self.AddObserver("RightButtonReleaseEvent", self._right_up)
        self.AddObserver("MouseMoveEvent", self._move)
        self.AddObserver("MouseWheelForwardEvent", self._wheel_fwd)
        self.AddObserver("MouseWheelBackwardEvent", self._wheel_back)
        self.AddObserver("CharEvent", lambda *a: None)  # disable VTK hot keys (q/e quit etc.)
        self.AddObserver("KeyPressEvent", lambda *a: None)

    def _state(self):
        iren = self.GetInteractor()
        x, y = iren.GetEventPosition()
        return x, y, bool(iren.GetControlKey()), bool(iren.GetShiftKey()), iren.GetRepeatCount()

    def _left_down(self, *_):
        x, y, ctrl, shift, rep = self._state()
        if self.viewer is not None:
            face = self.viewer.cube.hit(x, y)
            if face is not None:
                if face:
                    self.viewer.set_view(face)
                return
        if self.tool is not None and self.tool.on_press(x, y, ctrl, shift, rep):
            return
        self.OnLeftButtonDown()

    def _left_up(self, *_):
        x, y, ctrl, shift, _ = self._state()
        if self.tool is not None and self.tool.on_release(x, y, ctrl, shift):
            return
        self.OnLeftButtonUp()

    def _right_down(self, *_):
        self._right_rotating = True
        self.OnLeftButtonDown()

    def _right_up(self, *_):
        if self._right_rotating:
            self._right_rotating = False
            self.OnLeftButtonUp()

    def _move(self, *_):
        x, y, ctrl, shift, _ = self._state()
        if self.viewer is not None and self.GetState() == 0 and self.viewer.cube.hover(x, y):
            self.viewer.render()
        if self.tool is not None and not self._right_rotating and self.tool.on_move(x, y, ctrl, shift):
            return
        self.OnMouseMove()

    def _wheel(self, direction):
        iren = self.GetInteractor()
        if self.tool is not None and iren.GetControlKey() and self.tool.on_wheel(direction):
            return True
        return False

    def _wheel_fwd(self, *_):
        if not self._wheel(1):
            self.OnMouseWheelForward()

    def _wheel_back(self, *_):
        if not self._wheel(-1):
            self.OnMouseWheelBackward()

    # helpers for tools that turn a left drag into a rotation
    def start_rotate(self):
        self.OnLeftButtonDown()

    def end_rotate(self):
        self.OnLeftButtonUp()


class Overlay2D:
    """A 2D polyline / point set drawn on top of the scene in display pixels."""

    def __init__(self, renderer, color=(1.0, 0.85, 0.1), width=2.0, point_size=0.0):
        self.renderer = renderer
        self.pd = vtkPolyData()
        mapper = vtkPolyDataMapper2D()
        mapper.SetInputData(self.pd)
        self.actor = vtkActor2D()
        self.actor.SetMapper(mapper)
        p = self.actor.GetProperty()
        p.SetColor(*color)
        p.SetLineWidth(width)
        if point_size:
            p.SetPointSize(point_size)
        self.point_mode = bool(point_size)
        renderer.AddViewProp(self.actor)
        self.clear()

    def set(self, pts, closed=False):
        pts = np.asarray(pts, dtype=np.float64).reshape(-1, 2)
        points = vtkPoints()
        for x, y in pts:
            points.InsertNextPoint(float(x), float(y), 0.0)
        cells = vtkCellArray()
        n = len(pts)
        if self.point_mode:
            for i in range(n):
                cells.InsertNextCell(1)
                cells.InsertCellPoint(i)
            self.pd.SetVerts(cells)
            self.pd.SetLines(vtkCellArray())
        else:
            if n >= 2:
                cells.InsertNextCell(n + (1 if closed else 0))
                for i in range(n):
                    cells.InsertCellPoint(i)
                if closed:
                    cells.InsertCellPoint(0)
            self.pd.SetLines(cells)
            self.pd.SetVerts(vtkCellArray())
        self.pd.SetPoints(points)
        self.pd.Modified()

    def clear(self):
        self.set(np.zeros((0, 2)))

    def set_visible(self, on: bool):
        self.actor.SetVisibility(on)

    def remove(self):
        self.renderer.RemoveViewProp(self.actor)


class Viewer(QVTKRenderWindowInteractor):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rw = self.GetRenderWindow()
        self.rw.SetMultiSamples(0)  # MSAA breaks depth peeling (transparency); FXAA is used instead
        self.rw.SetAlphaBitPlanes(1)
        self.ren = self._make_renderer()
        self.rw.AddRenderer(self.ren)
        self.style = ViewerStyle()
        self.style.viewer = self
        self.SetInteractorStyle(self.style)

        self.models = []
        self.split_renderers: list = []
        self._split = False

        from .view_cube import ViewCube

        from .diagnostics import log

        log("viewer: renderer ready")
        self.cube = ViewCube(self)
        log("viewer: view cube ready")
        self._anim = None
        self.Initialize()

    @staticmethod
    def _make_renderer():
        ren = vtkRenderer()
        ren.GradientBackgroundOn()
        ren.SetBackground(0.16, 0.18, 0.22)
        ren.SetBackground2(0.42, 0.46, 0.54)
        ren.SetUseDepthPeeling(1)
        ren.SetMaximumNumberOfPeels(8)
        ren.SetOcclusionRatio(0.0)
        ren.UseFXAAOn()
        return ren

    # --------------------------------------------------------------- scene
    def add_model(self, model, fit=False):
        self.models.append(model)
        self.ren.AddActor(model.actor)
        if len(self.models) == 1:
            self.set_view("iso", animate=False)
        elif fit:
            self.fit()
        else:
            self.ren.ResetCameraClippingRange()
        self.render()

    def remove_model(self, model):
        if model in self.models:
            self.models.remove(model)
        self.ren.RemoveActor(model.actor)
        for r in self.split_renderers:
            r.RemoveActor(model.actor)
        self.render()

    def render(self):
        self.ren.ResetCameraClippingRange()
        for r in self.split_renderers:
            r.ResetCameraClippingRange()
        self.rw.Render()

    def fit(self, renderer=None):
        rens = [renderer] if renderer else ([self.ren] if not self._split else self.split_renderers)
        for r in rens:
            r.ResetCamera()
            r.ResetCameraClippingRange()
        self.rw.Render()

    VIEWS = {  # camera position direction (from focal point), view up
        "front": ((0, -1, 0), (0, 0, 1)),
        "back": ((0, 1, 0), (0, 0, 1)),
        "left": ((-1, 0, 0), (0, 0, 1)),
        "right": ((1, 0, 0), (0, 0, 1)),
        "top": ((0, 0, 1), (0, 1, 0)),
        "bottom": ((0, 0, -1), (0, -1, 0)),
        "iso": ((1, -1, 1), (0, 0, 1)),
    }

    def set_view(self, name: str, animate: bool = True):
        """Standard views (Z is up, the front looks along +Y), with a short smooth rotation."""
        pos, up = self.VIEWS[name]
        pos = np.array(pos, float) / np.linalg.norm(pos)
        up = np.array(up, float)
        if self._split:
            for r in self.split_renderers:
                cam = r.GetActiveCamera()
                fp = np.array(cam.GetFocalPoint())
                cam.SetPosition(*(fp + pos * cam.GetDistance()))
                cam.SetViewUp(*up)
                r.ResetCamera()
            self.render()
            return
        cam = self.ren.GetActiveCamera()
        if not animate:
            self._place_camera(cam, pos, up)
            self.ren.ResetCamera()
            self.render()
            return
        from PySide6.QtCore import QTimer
        from scipy.spatial.transform import Rotation, Slerp

        def frame(back, upv):
            upv = upv - back * (upv @ back)
            upv /= np.linalg.norm(upv)
            return np.column_stack([np.cross(upv, back), upv, back])

        start_back = -np.array(cam.GetDirectionOfProjection())
        start = frame(start_back, np.array(cam.GetViewUp()))
        end = frame(pos, up)
        slerp = Slerp([0.0, 1.0], Rotation.from_matrix([start, end]))
        steps = 14
        if self._anim is not None:
            self._anim.stop()
        state = {"i": 0}
        timer = QTimer(self)
        self._anim = timer

        def tick():
            state["i"] += 1
            t = state["i"] / steps
            t = t * t * (3 - 2 * t)  # ease in/out
            R = slerp([t]).as_matrix()[0]
            self._place_camera(cam, R[:, 2], R[:, 1])
            if state["i"] >= steps:
                timer.stop()
                self._anim = None
                self.ren.ResetCamera()
            self.render()

        timer.timeout.connect(tick)
        timer.start(16)

    @staticmethod
    def _place_camera(cam, back, up):
        fp = np.array(cam.GetFocalPoint())
        cam.SetPosition(*(fp + back * cam.GetDistance()))
        cam.SetViewUp(*up)

    def set_parallel(self, on: bool):
        for r in [self.ren] + self.split_renderers:
            r.GetActiveCamera().SetParallelProjection(on)
        self.render()

    # ----------------------------------------------------------- split view
    @property
    def is_split(self):
        return self._split

    def enter_split(self, left_models, right_models):
        if self._split:
            self.exit_split()
        self._split = True
        self.cube.set_visible(False)
        self.rw.RemoveRenderer(self.ren)
        left, right = self._make_renderer(), self._make_renderer()
        left.SetViewport(0.0, 0.0, 0.5, 1.0)
        right.SetViewport(0.5, 0.0, 1.0, 1.0)
        right.SetBackground(0.18, 0.16, 0.22)
        for m in left_models:
            left.AddActor(m.actor)
        for m in right_models:
            right.AddActor(m.actor)
        for r in (left, right):
            parallel = self.ren.GetActiveCamera().GetParallelProjection()
            r.GetActiveCamera().DeepCopy(self.ren.GetActiveCamera())
            r.GetActiveCamera().SetParallelProjection(parallel)
            r.ResetCamera()
            self.rw.AddRenderer(r)
        self.split_renderers = [left, right]
        self.render()
        return left, right

    def exit_split(self):
        if not self._split:
            return
        for r in self.split_renderers:
            r.RemoveAllViewProps()
            self.rw.RemoveRenderer(r)
        self.split_renderers = []
        self._split = False
        self.rw.AddRenderer(self.ren)
        self.cube.set_visible(True)
        self.render()

    def poked_renderer(self, x, y):
        return self._Iren.FindPokedRenderer(int(x), int(y))

    def capture_zbuffer(self, renderer, hide=()):
        """Render without 2D overlays and return the depth buffer."""
        from .selection import read_zbuffer

        states = [(a, a.GetVisibility()) for a in hide]
        for a, _ in states:
            a.SetVisibility(False)
        cube_on = self.cube.ren.GetDraw()
        self.cube.set_visible(False)
        self.render()
        z = read_zbuffer(renderer)
        for a, v in states:
            a.SetVisibility(v)
        self.cube.set_visible(cube_on)
        return z

    def screenshot(self, path: str):
        from vtkmodules.vtkIOImage import vtkPNGWriter
        from vtkmodules.vtkRenderingCore import vtkWindowToImageFilter

        self.render()
        w2i = vtkWindowToImageFilter()
        w2i.SetInput(self.rw)
        w2i.ReadFrontBufferOff()
        w2i.Update()
        writer = vtkPNGWriter()
        writer.SetFileName(path)
        writer.SetInputConnection(w2i.GetOutputPort())
        writer.Write()
