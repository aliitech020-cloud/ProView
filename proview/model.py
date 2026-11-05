"""A model in the scene: mesh + pose + VTK actor + face selection."""
from __future__ import annotations

import numpy as np
from vtkmodules.util.numpy_support import numpy_to_vtk
from vtkmodules.vtkCommonMath import vtkMatrix4x4
from vtkmodules.vtkRenderingCore import vtkActor, vtkPolyDataMapper, vtkProperty

from .mesh import Mesh, to_polydata, transform_points

# Dental material looks: colour + how light reflects (matte stone vs glossy zirconia ...).
# finish: ambient, diffuse, specular, specular power
MATERIALS = {
    "Stone - Ivory": ((0.93, 0.89, 0.80), (0.16, 0.86, 0.06, 6)),
    "Stone - Blue": ((0.47, 0.64, 0.86), (0.16, 0.86, 0.06, 6)),
    "Stone - Yellow": ((0.95, 0.83, 0.45), (0.16, 0.86, 0.06, 6)),
    "Stone - Pink": ((0.93, 0.70, 0.70), (0.16, 0.86, 0.06, 6)),
    "Stone - Green": ((0.60, 0.80, 0.58), (0.16, 0.86, 0.06, 6)),
    "Stone - Grey": ((0.70, 0.72, 0.74), (0.16, 0.86, 0.06, 6)),
    "Zirconia - Glossy": ((0.96, 0.95, 0.91), (0.10, 0.80, 0.85, 70)),
    "Zirconia - Matte": ((0.95, 0.94, 0.90), (0.18, 0.84, 0.12, 10)),
    "Resin / PMMA (A2)": ((0.93, 0.87, 0.74), (0.12, 0.82, 0.45, 35)),
    "Wax - Green": ((0.42, 0.68, 0.45), (0.12, 0.80, 0.55, 30)),
    "Wax - Blue": ((0.38, 0.55, 0.85), (0.12, 0.80, 0.55, 30)),
    "Gingiva": ((0.86, 0.48, 0.52), (0.14, 0.82, 0.35, 25)),
    "Titanium": ((0.66, 0.68, 0.72), (0.12, 0.62, 0.90, 60)),
    "Gold": ((0.90, 0.72, 0.32), (0.12, 0.62, 0.90, 55)),
    "Cobalt-Chrome": ((0.78, 0.79, 0.81), (0.12, 0.60, 0.95, 80)),
}
DEFAULT_MATERIALS = ["Stone - Ivory", "Stone - Blue", "Stone - Yellow", "Zirconia - Glossy",
                     "Stone - Green", "Stone - Pink", "Titanium"]
CUSTOM = "Custom"

SELECT_COLOR = np.array([230, 40, 40], dtype=np.uint8)
SELECT_COLOR_ON_SCAN = np.array([30, 140, 255], dtype=np.uint8)  # gums are red, so use blue


def numpy_to_vtk_matrix(M: np.ndarray) -> vtkMatrix4x4:
    m = vtkMatrix4x4()
    for i in range(4):
        for j in range(4):
            m.SetElement(i, j, float(M[i, j]))
    return m


class Model:
    _counter = 0

    def __init__(self, name: str, mesh: Mesh, path: str | None = None, color=None, material=None):
        self.name = name
        self.path = path
        if material is None and color is None:
            material = DEFAULT_MATERIALS[Model._counter % len(DEFAULT_MATERIALS)]
            Model._counter += 1
        if material is not None:
            color = MATERIALS[material][0]
        self.material = material or CUSTOM
        self.finish = MATERIALS[material][1] if material else (0.12, 0.82, 0.25, 25)
        self.color = tuple(color)
        self.matrix = np.eye(4)
        self.visible = True
        self.opacity = 1.0

        self.mapper = vtkPolyDataMapper()
        self.mapper.SetColorModeToDirectScalars()
        self.mapper.ScalarVisibilityOff()
        self.mapper.SetResolveCoincidentTopologyToPolygonOffset()
        self.actor = vtkActor()
        self.actor.SetMapper(self.mapper)
        prop = self.actor.GetProperty()
        prop.SetInterpolationToPhong()
        prop.SetSpecularColor(1.0, 1.0, 1.0)
        prop.SetEdgeColor(0.25, 0.25, 0.3)
        back = vtkProperty()
        back.SetColor(0.45, 0.5, 0.62)
        back.SetAmbient(0.2)
        back.SetDiffuse(0.7)
        self.actor.SetBackfaceProperty(back)
        self.set_color(self.color, keep_material=True)
        self._apply_finish()

        self.mesh: Mesh = mesh
        self.flat = False
        self.show_colors = True
        self.selection = np.zeros(0, dtype=bool)
        self._world = None
        self.set_mesh(mesh)

    # ---------------------------------------------------------------- mesh
    def set_mesh(self, mesh: Mesh) -> None:
        self.mesh = mesh
        self.polydata = to_polydata(mesh)
        self._normals = self.polydata.GetPointData().GetNormals()
        if getattr(self, "flat", False):
            self.polydata.GetPointData().SetNormals(None)
        self.mapper.SetInputData(self.polydata)
        self.selection = np.zeros(mesh.n_faces, dtype=bool)
        self._colors = np.empty((mesh.n_faces, 3), dtype=np.uint8)
        self._colors[:] = self._base_face_colors()
        self._colors_vtk = numpy_to_vtk(self._colors, deep=False)
        self._colors_vtk.SetName("SelectionColors")
        self.polydata.GetCellData().AddArray(self._colors_vtk)
        self._world = None
        self._update_scalars()

    @property
    def has_colors(self) -> bool:
        return self.mesh.colors is not None

    def _base_face_colors(self) -> np.ndarray:
        """Per-face color used for unselected faces while a selection is shown (cached)."""
        key = (id(self.mesh), self.show_colors, self.color)
        if getattr(self, "_base_key", None) != key:
            if self.has_colors and self.show_colors and self.mesh.n_faces:
                self._base_cache = self.mesh.colors[self.mesh.faces].mean(axis=1).round().astype(np.uint8)
            else:
                self._base_cache = self._base_rgb()
            self._base_key = key
        return self._base_cache

    @property
    def select_color(self) -> np.ndarray:
        return SELECT_COLOR_ON_SCAN if self.has_colors and self.show_colors else SELECT_COLOR

    def _update_scalars(self) -> None:
        if self.selection.any():
            self.mapper.SetScalarModeToUseCellFieldData()
            self.mapper.SelectColorArray("SelectionColors")
            self.mapper.ScalarVisibilityOn()
        elif self.has_colors and self.show_colors:
            self.mapper.SetScalarModeToUsePointFieldData()
            self.mapper.SelectColorArray("VertexColors")
            self.mapper.ScalarVisibilityOn()
        else:
            self.mapper.ScalarVisibilityOff()
        self._apply_finish()

    def set_show_colors(self, on: bool) -> None:
        self.show_colors = on
        if hasattr(self, "_colors"):
            self._colors[self.selection] = self.select_color
            self._colors[~self.selection] = self._base_face_colors()[~self.selection] \
                if self.has_colors and on else self._base_rgb()
            self._colors_vtk.Modified()
            self._update_scalars()

    def set_matrix(self, M: np.ndarray) -> None:
        self.matrix = np.array(M, dtype=np.float64)
        self.actor.SetUserMatrix(numpy_to_vtk_matrix(self.matrix))
        self._world = None

    # -------------------------------------------------------------- display
    def _base_rgb(self) -> np.ndarray:
        return (np.array(self.color) * 255).round().astype(np.uint8)

    def _apply_finish(self) -> None:
        ambient, diffuse, specular, power = self.finish
        if getattr(self, "mesh", None) is not None and self.has_colors and self.show_colors:
            specular = min(specular, 0.08)  # scanned colours: keep them readable
        prop = self.actor.GetProperty()
        prop.SetAmbient(ambient)
        prop.SetDiffuse(diffuse)
        prop.SetSpecular(specular)
        prop.SetSpecularPower(power)

    def set_material(self, name: str) -> None:
        """Apply a material preset (colour and surface finish)."""
        color, finish = MATERIALS[name]
        self.material = name
        self.finish = finish
        self.set_color(color, keep_material=True)
        self._apply_finish()

    def set_color(self, color, keep_material: bool = False) -> None:
        if not keep_material and hasattr(self, "material"):
            self.material = CUSTOM  # keeps the current finish, only the colour changes
        self.color = tuple(color)
        self.actor.GetProperty().SetColor(*self.color)
        if hasattr(self, "_colors") and not (self.has_colors and self.show_colors):
            self._colors[~self.selection] = self._base_rgb()
            self._colors_vtk.Modified()

    def set_opacity(self, value: float) -> None:
        self.opacity = value
        self.actor.GetProperty().SetOpacity(value)

    def set_visible(self, visible: bool) -> None:
        self.visible = visible
        self.actor.SetVisibility(visible)

    def set_flat(self, on: bool) -> None:
        """Flat (faceted) shading: without vertex normals every triangle is lit on its own,
        which shows edges and geometric detail sharply."""
        self.flat = on
        pd = self.polydata.GetPointData()
        pd.SetNormals(None if on else self._normals)
        self.polydata.Modified()
        prop = self.actor.GetProperty()
        if on:
            prop.SetInterpolationToFlat()
        else:
            prop.SetInterpolationToPhong()

    def set_edges(self, on: bool) -> None:
        self.actor.GetProperty().SetEdgeVisibility(on)

    # ------------------------------------------------------------ selection
    def set_selection(self, mask: np.ndarray) -> None:
        mask = np.asarray(mask, dtype=bool)
        changed = mask != self.selection
        self.selection = mask.copy()
        if changed.any():
            self._colors[changed & mask] = self.select_color
            off = changed & ~mask
            if off.any():
                base = self._base_face_colors()
                self._colors[off] = base[off] if base.ndim == 2 else base
            self._colors_vtk.Modified()
            self.polydata.Modified()
        self._update_scalars()

    def clear_selection(self) -> None:
        self.set_selection(np.zeros(self.mesh.n_faces, dtype=bool))

    # -------------------------------------------------------------- geometry
    def world_geometry(self):
        """(world vertices, face centroids, face normals) - cached."""
        if self._world is None:
            wv = transform_points(self.matrix, self.mesh.vertices)
            tri = wv[self.mesh.faces]
            cen = tri.mean(axis=1)
            n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
            ln = np.linalg.norm(n, axis=1, keepdims=True)
            ln[ln == 0] = 1.0
            self._world = (wv, cen, n / ln)
        return self._world

    def world_vertex_normals(self) -> np.ndarray:
        return self.mesh.vertex_normals() @ self.matrix[:3, :3].T

    def world_bounds(self):
        wv = self.world_geometry()[0]
        if len(wv) == 0:
            return np.zeros(3), np.zeros(3)
        return wv.min(0), wv.max(0)
