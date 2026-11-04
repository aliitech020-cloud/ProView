"""Triangle mesh data, STL reading/writing and VTK conversion.

The STL parser is pure numpy on purpose: it is fast and works with
non-ASCII (e.g. Arabic) file paths on Windows, which VTK readers do not
always handle.
"""
from __future__ import annotations

import re
import struct

import numpy as np

_STL_RECORD = np.dtype([("n", "<f4", (3,)), ("v", "<f4", (3, 3)), ("a", "<u2")])


class Mesh:
    """Indexed triangle mesh: vertices (n, 3) float64 and faces (m, 3) int64."""

    def __init__(self, vertices: np.ndarray, faces: np.ndarray):
        self.vertices = np.ascontiguousarray(vertices, dtype=np.float64).reshape(-1, 3)
        self.faces = np.ascontiguousarray(faces, dtype=np.int64).reshape(-1, 3)

    # ------------------------------------------------------------------ info
    @property
    def n_vertices(self) -> int:
        return len(self.vertices)

    @property
    def n_faces(self) -> int:
        return len(self.faces)

    def copy(self) -> "Mesh":
        return Mesh(self.vertices.copy(), self.faces.copy())

    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        if self.n_vertices == 0:
            return np.zeros(3), np.zeros(3)
        return self.vertices.min(axis=0), self.vertices.max(axis=0)

    def diagonal(self) -> float:
        lo, hi = self.bounds()
        return float(np.linalg.norm(hi - lo))

    # -------------------------------------------------------------- geometry
    def face_normals(self, vertices: np.ndarray | None = None, normalize=True) -> np.ndarray:
        v = self.vertices if vertices is None else vertices
        tri = v[self.faces]
        n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        if normalize:
            ln = np.linalg.norm(n, axis=1, keepdims=True)
            ln[ln == 0] = 1.0
            n = n / ln
        return n

    def vertex_normals(self, vertices: np.ndarray | None = None) -> np.ndarray:
        """Area weighted vertex normals."""
        v = self.vertices if vertices is None else vertices
        fn = self.face_normals(v, normalize=False)
        vn = np.zeros_like(v)
        for k in range(3):
            np.add.at(vn, self.faces[:, k], fn)
        ln = np.linalg.norm(vn, axis=1, keepdims=True)
        ln[ln == 0] = 1.0
        return vn / ln

    def face_centroids(self, vertices: np.ndarray | None = None) -> np.ndarray:
        v = self.vertices if vertices is None else vertices
        return v[self.faces].mean(axis=1)

    # ------------------------------------------------------------- editing
    def remove_faces(self, mask: np.ndarray) -> "Mesh":
        """Return a new mesh without the faces where ``mask`` is True."""
        return self.keep_faces(~np.asarray(mask, dtype=bool))

    def keep_faces(self, mask: np.ndarray) -> "Mesh":
        faces = self.faces[np.asarray(mask, dtype=bool)]
        used = np.zeros(self.n_vertices, dtype=bool)
        used[faces.ravel()] = True
        remap = np.cumsum(used) - 1
        return Mesh(self.vertices[used], remap[faces])

    def connected_components(self) -> tuple[int, np.ndarray]:
        """Label faces by connected component (faces sharing a vertex)."""
        from scipy.sparse import coo_matrix
        from scipy.sparse.csgraph import connected_components

        n = self.n_vertices
        if self.n_faces == 0:
            return 0, np.zeros(0, dtype=np.int64)
        f = self.faces
        rows = np.concatenate([f[:, 0], f[:, 1], f[:, 2]])
        cols = np.concatenate([f[:, 1], f[:, 2], f[:, 0]])
        graph = coo_matrix((np.ones(len(rows), dtype=np.int8), (rows, cols)), shape=(n, n))
        count, vlabels = connected_components(graph, directed=False)
        return count, vlabels[f[:, 0]]

    def transformed(self, matrix: np.ndarray) -> "Mesh":
        return Mesh(transform_points(matrix, self.vertices), self.faces.copy())


def transform_points(matrix: np.ndarray, pts: np.ndarray) -> np.ndarray:
    m = np.asarray(matrix, dtype=np.float64)
    return pts @ m[:3, :3].T + m[:3, 3]


# ---------------------------------------------------------------------- I/O
def _merge_vertices(tri_vertices: np.ndarray) -> Mesh:
    """Build an indexed mesh from a (m, 3, 3) float32 triangle soup."""
    flat = np.ascontiguousarray(tri_vertices.reshape(-1, 3), dtype=np.float32)
    flat = flat + np.float32(0.0)  # turns -0.0 into 0.0 so they merge
    key = flat.view(np.dtype((np.void, 12))).ravel()
    _, first, inverse = np.unique(key, return_index=True, return_inverse=True)
    vertices = flat[first].astype(np.float64)
    faces = inverse.reshape(-1, 3).astype(np.int64)
    # drop degenerate triangles (two identical corners)
    ok = (faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2]) & (faces[:, 0] != faces[:, 2])
    mesh = Mesh(vertices, faces)
    if not ok.all():
        mesh = mesh.keep_faces(ok)
    return mesh


def load_stl(path: str) -> Mesh:
    with open(path, "rb") as fh:
        data = fh.read()
    if len(data) < 15:
        raise ValueError("File is too small to be an STL file")
    if len(data) >= 84:
        count = struct.unpack_from("<I", data, 80)[0]
        if 84 + count * 50 == len(data):
            rec = np.frombuffer(data, dtype=_STL_RECORD, count=count, offset=84)
            return _merge_vertices(rec["v"])
    head = data[:512].lstrip().lower()
    if head.startswith(b"solid"):
        text = data.decode("ascii", errors="ignore")
        nums = re.findall(r"vertex\s+(\S+)\s+(\S+)\s+(\S+)", text)
        if nums:
            arr = np.array(nums, dtype=np.float32)
            arr = arr[: (len(arr) // 3) * 3]
            return _merge_vertices(arr.reshape(-1, 3, 3))
    # fall back to binary with a wrong header count
    if len(data) >= 84:
        count = (len(data) - 84) // 50
        if count > 0:
            rec = np.frombuffer(data, dtype=_STL_RECORD, count=count, offset=84)
            return _merge_vertices(rec["v"])
    raise ValueError("Unrecognised STL file")


def save_stl(path: str, mesh: Mesh, matrix: np.ndarray | None = None, header: str = "ProView") -> None:
    """Write a binary STL. ``matrix`` (4x4) is applied to the vertices first."""
    verts = mesh.vertices if matrix is None else transform_points(matrix, mesh.vertices)
    tri = verts[mesh.faces]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    ln[ln == 0] = 1.0
    rec = np.zeros(mesh.n_faces, dtype=_STL_RECORD)
    rec["n"] = n / ln
    rec["v"] = tri
    with open(path, "wb") as fh:
        fh.write(header.encode("ascii", "replace")[:80].ljust(80, b" "))
        fh.write(struct.pack("<I", mesh.n_faces))
        fh.write(rec.tobytes())


def merge_meshes(meshes: list[Mesh]) -> Mesh:
    verts, faces, off = [], [], 0
    for m in meshes:
        verts.append(m.vertices)
        faces.append(m.faces + off)
        off += m.n_vertices
    if not verts:
        return Mesh(np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64))
    return Mesh(np.vstack(verts), np.vstack(faces))


# ---------------------------------------------------------------------- VTK
def to_polydata(mesh: Mesh):
    from vtkmodules.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray
    from vtkmodules.vtkCommonCore import vtkPoints
    from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData

    pts = vtkPoints()
    pts.SetData(numpy_to_vtk(np.ascontiguousarray(mesh.vertices, dtype=np.float64), deep=True))
    m = mesh.n_faces
    offsets = np.arange(0, 3 * m + 1, 3, dtype=np.int64)
    conn = np.ascontiguousarray(mesh.faces.ravel(), dtype=np.int64)
    cells = vtkCellArray()
    cells.SetData(numpy_to_vtkIdTypeArray(offsets, deep=True), numpy_to_vtkIdTypeArray(conn, deep=True))
    pd = vtkPolyData()
    pd.SetPoints(pts)
    pd.SetPolys(cells)
    if mesh.n_faces:
        normals = numpy_to_vtk(np.ascontiguousarray(mesh.vertex_normals(), dtype=np.float32), deep=True)
        normals.SetName("Normals")
        pd.GetPointData().SetNormals(normals)
    return pd
