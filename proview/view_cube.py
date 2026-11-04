"""Navigation cube in the top-right corner: follows the camera, click a face to look at it."""
from __future__ import annotations

import numpy as np
from vtkmodules.util.numpy_support import numpy_to_vtk
from vtkmodules.vtkCommonCore import vtkFloatArray, vtkPoints
from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkImageData, vtkPolyData
from vtkmodules.vtkRenderingCore import vtkActor, vtkPolyDataMapper, vtkRenderer, vtkTexture

from .selection import display_ray

h = 0.5
# corners: bottom-left, bottom-right, top-right, top-left as seen in that standard view
FACE_QUADS = {
    "front": [(-h, -h, -h), (h, -h, -h), (h, -h, h), (-h, -h, h)],
    "back": [(h, h, -h), (-h, h, -h), (-h, h, h), (h, h, h)],
    "right": [(h, -h, -h), (h, h, -h), (h, h, h), (h, -h, h)],
    "left": [(-h, h, -h), (-h, -h, -h), (-h, -h, h), (-h, h, h)],
    "top": [(-h, -h, h), (h, -h, h), (h, h, h), (-h, h, h)],
    "bottom": [(-h, h, -h), (h, h, -h), (h, -h, -h), (-h, -h, -h)],
}
FACES = {(0, 1): "right", (0, -1): "left", (1, 1): "back", (1, -1): "front", (2, 1): "top", (2, -1): "bottom"}


def _label_texture(text: str, hover: bool = False, size: int = 256) -> vtkTexture:
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QLinearGradient, QPainter, QPen

    img = QImage(size, size, QImage.Format_RGBA8888)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    g = QLinearGradient(0, 0, 0, size)
    if hover:
        g.setColorAt(0, QColor(70, 150, 235))
        g.setColorAt(1, QColor(40, 105, 190))
    else:
        g.setColorAt(0, QColor(92, 98, 110))
        g.setColorAt(1, QColor(64, 69, 79))
    p.fillRect(img.rect(), g)
    pen = QPen(QColor(30, 33, 38))
    pen.setWidth(10)
    p.setPen(pen)
    p.drawRect(QRectF(5, 5, size - 10, size - 10))
    font = QFont("Segoe UI")
    font.setBold(True)
    font.setLetterSpacing(QFont.AbsoluteSpacing, 1.5)
    px = 64
    while px > 12:
        font.setPixelSize(px)
        if QFontMetrics(font).horizontalAdvance(text) <= size * 0.78:
            break
        px -= 2
    p.setFont(font)
    p.setPen(QColor(240, 243, 248))
    p.drawText(img.rect(), Qt.AlignCenter, text)
    p.end()

    ptr = img.constBits()
    arr = np.frombuffer(ptr, dtype=np.uint8, count=img.sizeInBytes()).reshape(size, img.bytesPerLine() // 4, 4)
    arr = np.ascontiguousarray(arr[::-1, :size])  # VTK images start at the bottom row
    data = vtkImageData()
    data.SetDimensions(size, size, 1)
    scalars = numpy_to_vtk(arr.reshape(-1, 4), deep=True)
    scalars.SetNumberOfComponents(4)
    data.GetPointData().SetScalars(scalars)
    tex = vtkTexture()
    tex.SetInputData(data)
    tex.InterpolateOn()
    tex.MipmapOn()
    return tex


def _quad(corners):
    pts = vtkPoints()
    for c in corners:
        pts.InsertNextPoint(*c)
    cells = vtkCellArray()
    cells.InsertNextCell(4)
    for i in range(4):
        cells.InsertCellPoint(i)
    tc = vtkFloatArray()
    tc.SetNumberOfComponents(2)
    for uv in ((0, 0), (1, 0), (1, 1), (0, 1)):
        tc.InsertNextTuple2(*uv)
    pd = vtkPolyData()
    pd.SetPoints(pts)
    pd.SetPolys(cells)
    pd.GetPointData().SetTCoords(tc)
    return pd


class ViewCube:
    SIZE = 112  # logical pixels
    MARGIN = 16

    def __init__(self, viewer):
        self.viewer = viewer
        self.ren = vtkRenderer()
        self.ren.SetLayer(1)
        self.ren.InteractiveOff()
        self.ren.GetActiveCamera().ParallelProjectionOn()
        self.actors = {}
        self.textures = {}
        self._hover = None
        for name, corners in FACE_QUADS.items():
            mapper = vtkPolyDataMapper()
            mapper.SetInputData(_quad(corners))
            actor = vtkActor()
            actor.SetMapper(mapper)
            self.textures[name] = (_label_texture(name.upper()), _label_texture(name.upper(), hover=True))
            actor.SetTexture(self.textures[name][0])
            prop = actor.GetProperty()
            prop.SetAmbient(0.55)
            prop.SetDiffuse(0.55)
            prop.SetSpecular(0.15)
            actor.PickableOff()
            self.ren.AddActor(actor)
            self.actors[name] = actor
        viewer.rw.SetNumberOfLayers(2)
        viewer.rw.AddRenderer(self.ren)
        viewer.ren.AddObserver("StartEvent", self.sync)

    def set_visible(self, on: bool):
        self.ren.SetDraw(on)

    def sync(self, *_):
        w, hgt = self.viewer.rw.GetSize()
        if w < 10 or hgt < 10:
            return
        dpr = self.viewer.devicePixelRatioF()
        s, m = self.SIZE * dpr, self.MARGIN * dpr
        x1, y1 = 1.0 - m / w, 1.0 - m / hgt
        self.ren.SetViewport(max(0.0, x1 - s / w), max(0.0, y1 - s / hgt), x1, y1)
        main = self.viewer.ren.GetActiveCamera()
        dop = np.array(main.GetDirectionOfProjection())
        cam = self.ren.GetActiveCamera()
        cam.SetFocalPoint(0, 0, 0)
        cam.SetPosition(*(-dop * 5.0))
        cam.SetViewUp(*main.GetViewUp())
        cam.SetParallelScale(0.92)
        self.ren.ResetCameraClippingRange()

    def hit(self, x, y) -> str | None:
        """Face under display pixel (x, y): a view name, "" for the empty corner area, None elsewhere."""
        if not self.ren.GetDraw():
            return None
        vp = self.ren.GetViewport()
        w, hgt = self.viewer.rw.GetSize()
        if not (vp[0] * w <= x <= vp[2] * w and vp[1] * hgt <= y <= vp[3] * hgt):
            return None
        o, d = display_ray(self.ren, x, y)
        tmin, tmax, face = -np.inf, np.inf, None
        for k in range(3):
            if abs(d[k]) < 1e-12:
                if abs(o[k]) > h:
                    return ""
                continue
            t1, t2 = (-h - o[k]) / d[k], (h - o[k]) / d[k]
            sign = -1 if t1 < t2 else 1
            if t1 > t2:
                t1, t2 = t2, t1
            if t1 > tmin:
                tmin, face = t1, (k, sign)
            tmax = min(tmax, t2)
        if face is None or tmin > tmax:
            return ""
        return FACES[face]

    def hover(self, x, y) -> bool:
        """Highlight the face under the cursor. Returns True if a re-render is needed."""
        face = self.hit(x, y) or None
        if face == self._hover:
            return False
        if self._hover:
            self.actors[self._hover].SetTexture(self.textures[self._hover][0])
        if face:
            self.actors[face].SetTexture(self.textures[face][1])
        self._hover = face
        return True
