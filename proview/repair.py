"""Scan repair: fill holes with a smooth patch, smooth the scan's open edge."""
from __future__ import annotations

import numpy as np
from scipy.sparse import coo_matrix, csr_matrix, diags

from .mesh import Mesh


def vertex_adjacency(n: int, faces: np.ndarray) -> csr_matrix:
    f = faces
    rows = np.concatenate([f[:, 0], f[:, 1], f[:, 2], f[:, 1], f[:, 2], f[:, 0]])
    cols = np.concatenate([f[:, 1], f[:, 2], f[:, 0], f[:, 0], f[:, 1], f[:, 2]])
    a = coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(n, n)).tocsr()
    a.data[:] = 1.0
    return a


def loop_size(v: np.ndarray, loop) -> float:
    """Size of a hole: diagonal of its bounding box (mm)."""
    p = v[loop]
    return float(np.linalg.norm(p.max(0) - p.min(0)))


def _patch_delaunay(v, loop, constrained=True):
    """Triangulate a hole: boundary points + interior grid points, Delaunay in the hole's plane.
    Returns (new_points, triangles) where triangle ids < len(loop) refer to loop positions."""
    from vtkmodules.vtkCommonCore import vtkPoints
    from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData
    from vtkmodules.vtkFiltersCore import vtkDelaunay2D
    from vtkmodules.util.numpy_support import vtk_to_numpy

    from .selection import points_in_polygon, segment_distance

    p = v[loop]
    c = p.mean(0)
    _, _, vt = np.linalg.svd(p - c, full_matrices=False)
    e1, e2 = vt[0], vt[1]
    xy = np.stack([(p - c) @ e1, (p - c) @ e2], 1)
    order = np.arange(len(loop))
    area = 0.5 * np.sum(xy[:, 0] * np.roll(xy[:, 1], -1) - np.roll(xy[:, 0], -1) * xy[:, 1])
    if area < 0:  # Delaunay2D keeps the inside of counter-clockwise boundaries
        order = order[::-1]
    h = float(np.mean(np.linalg.norm(p - np.roll(p, -1, 0), axis=1)))
    lo, hi = xy.min(0), xy.max(0)
    gx = np.arange(lo[0] + h / 2, hi[0], h)
    gy = np.arange(lo[1] + h / 2, hi[1], h * np.sqrt(3) / 2)
    pts = []
    for k, yy in enumerate(gy):
        xs = gx + (h / 2 if k % 2 else 0)
        pts.append(np.stack([xs, np.full(len(xs), yy)], 1))
    grid = np.vstack(pts) if pts else np.zeros((0, 2))
    if len(grid):
        grid = grid[points_in_polygon(grid, xy)]
    if len(grid):
        dmin = np.full(len(grid), np.inf)
        for i in range(len(xy)):
            dmin = np.minimum(dmin, segment_distance(grid, xy[i], xy[(i + 1) % len(xy)]))
        grid = grid[dmin > 0.6 * h]
    allxy = np.vstack([xy, grid])
    vp = vtkPoints()
    vp.SetDataTypeToDouble()
    for x, y in allxy:
        vp.InsertNextPoint(x, y, 0.0)
    pd = vtkPolyData()
    pd.SetPoints(vp)
    poly = vtkCellArray()
    poly.InsertNextCell(len(order))
    for i in order:
        poly.InsertCellPoint(int(i))
    src = vtkPolyData()
    src.SetPoints(vp)
    src.SetPolys(poly)
    d = vtkDelaunay2D()
    d.SetInputData(pd)
    if constrained:
        d.SetSourceData(src)
    d.Update()
    out = d.GetOutput()
    if out.GetNumberOfPolys() == 0:
        return None
    tris = vtk_to_numpy(out.GetPolys().GetConnectivityArray()).reshape(-1, 3)
    if not constrained:  # keep the triangles inside the hole outline
        cen = allxy[tris].mean(1)
        tris = tris[points_in_polygon(cen, xy)]
    # Delaunay2D does not keep a consistent winding: make every triangle counter-clockwise
    t = allxy[tris]
    area2 = (t[:, 1, 0] - t[:, 0, 0]) * (t[:, 2, 1] - t[:, 0, 1]) - (t[:, 2, 0] - t[:, 0, 0]) * (t[:, 1, 1] - t[:, 0, 1])
    tris = np.where((area2 < 0)[:, None], tris[:, ::-1], tris)
    new3d = c + grid[:, :1] * e1 + grid[:, 1:2] * e2
    return new3d, tris


def _is_disk_patch(faces, loop) -> bool:
    """The patch's open edges must be exactly the hole's edges, each interior edge used twice."""
    if len(faces) == 0:
        return False
    e = np.sort(np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), 1)
    uniq, cnt = np.unique(e, axis=0, return_counts=True)
    if (cnt > 2).any():
        return False
    open_edges = {tuple(x) for x in uniq[cnt == 1]}
    lp = np.asarray(loop)
    hole_edges = {tuple(sorted((int(a), int(b)))) for a, b in zip(lp, np.roll(lp, -1))}
    return open_edges == hole_edges


def fill_hole(mesh_v: np.ndarray, mesh_f: np.ndarray, loop, colors=None):
    """Patch one boundary loop. Returns (new_vertices, new_faces_global, new_colors)."""
    n0 = len(mesh_v)
    m = len(loop)
    loop = np.asarray(loop)
    res = None
    if m > 3:
        for constrained in (True, False):
            try:
                cand = _patch_delaunay(mesh_v, loop, constrained)
            except Exception:  # noqa: BLE001
                cand = None
            if cand is None:
                continue
            new3d, tris = cand
            gid = np.concatenate([loop, n0 + np.arange(len(new3d))])
            faces = gid[tris]
            if _is_disk_patch(faces, loop):
                res = cand
                break
    if res is None:
        new3d = mesh_v[loop].mean(0)[None]
        faces = np.stack([np.roll(loop, -1), loop, np.full(m, n0)], 1)
    else:
        # orientation: the mesh has a->b on this edge, the patch must have b->a
        a, b = int(loop[0]), int(loop[1])
        has_ab = np.any((faces[:, 0] == a) & (faces[:, 1] == b) | (faces[:, 1] == a) & (faces[:, 2] == b) |
                        (faces[:, 2] == a) & (faces[:, 0] == b))
        if has_ab:
            faces = faces[:, ::-1]
    new_colors = None
    if colors is not None:
        new_colors = np.tile(colors[loop].mean(0).round().astype(np.uint8), (len(new3d), 1))
    return new3d, faces, new_colors


def fair_vertices(v: np.ndarray, faces: np.ndarray, free: np.ndarray, iterations: int = 200) -> np.ndarray:
    """Move the ``free`` vertices to the average of their neighbours (smooth membrane)."""
    if not free.any():
        return v
    a = vertex_adjacency(len(v), faces)
    deg = np.asarray(a.sum(1)).ravel()
    deg[deg == 0] = 1
    w = diags(1.0 / deg) @ a
    v = v.copy()
    idx = np.nonzero(free)[0]
    sub = w[idx]
    for _ in range(iterations):
        v[idx] = sub @ v
    return v


def remove_dangling_faces(mesh: Mesh) -> Mesh:
    """Drop loose triangles that share no edge with the rest (left over around holes)."""
    for _ in range(5):
        f = mesh.faces
        e = np.sort(np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]]), 1)
        _, inv, cnt = np.unique(e, axis=0, return_inverse=True, return_counts=True)
        shared = (cnt[inv.reshape(-1)] > 1).reshape(3, -1).T
        lone = ~shared.any(1)
        if not lone.any() or lone.all():
            break
        mesh = mesh.keep_faces(~lone)
    return mesh


def fill_holes(mesh: Mesh, max_size: float | None = None, keep: list[int] | None = None):
    """Fill boundary loops smaller than ``max_size`` (mm, bounding diagonal); never the loop ``keep``.
    Returns (new mesh, filled count, remaining open loops)."""
    from .model_builder import boundary_loops

    mesh = remove_dangling_faces(mesh)
    loops = boundary_loops(mesh.faces)
    if keep is not None:  # the kept edge may have changed indices: keep the largest loop
        keep = max(loops, key=lambda lp: loop_size(mesh.vertices, lp)) if loops else None
    keep_set = set(keep or [])
    v = mesh.vertices
    colors = mesh.colors
    new_v, new_f, new_c = [v], [mesh.faces], [colors] if colors is not None else None
    n = len(v)
    filled = 0
    remaining = 0
    for lp in loops:
        if keep_set & set(lp):
            remaining += 1
            continue
        if max_size is not None and loop_size(v, lp) > max_size:
            remaining += 1
            continue
        nv, nf, nc = fill_hole(np.vstack(new_v), np.vstack(new_f), lp, colors)
        new_v.append(nv)
        new_f.append(nf)
        if new_c is not None:
            new_c.append(nc)
        n += len(nv)
        filled += 1
    if not filled:
        return mesh, 0, remaining
    allv = np.vstack(new_v)
    allf = np.vstack(new_f)
    free = np.zeros(len(allv), bool)
    free[len(v):] = True
    allv = fair_vertices(allv, allf, free)
    out = Mesh(allv, allf, np.vstack(new_c) if new_c is not None else None)
    return out, filled, remaining


def smooth_open_edge(mesh: Mesh, loop, distance: float) -> Mesh:
    """Smooth the scan's open edge (and blend a band of ``distance`` mm next to it)."""
    if distance <= 0 or len(loop) < 8:
        return mesh
    v = mesh.vertices.copy()
    L = np.asarray(loop)
    p = v[L]
    h = float(np.mean(np.linalg.norm(p - np.roll(p, -1, 0), axis=1))) or 1.0
    iters = int(np.clip(3 * distance / h, 2, 200))
    for _ in range(iters):  # Taubin smoothing along the edge (does not shrink the outline)
        p = p + 0.5 * (0.5 * (np.roll(p, 1, 0) + np.roll(p, -1, 0)) - p)
        p = p - 0.53 * (0.5 * (np.roll(p, 1, 0) + np.roll(p, -1, 0)) - p)
    v[L] = p
    # blend: vertices close to the edge move towards their neighbours' average, less the further away
    a = vertex_adjacency(len(v), mesh.faces)
    edge_len = float(np.mean(np.linalg.norm(v[mesh.faces[:, 0]] - v[mesh.faces[:, 1]], axis=1))) or 1.0
    rings = int(np.clip(distance / edge_len, 1, 30))
    ring = np.full(len(v), -1)
    ring[L] = 0
    front = np.zeros(len(v), bool)
    front[L] = True
    for r in range(1, rings + 1):
        nb = (a @ front.astype(float)) > 0
        new = nb & (ring < 0)
        ring[new] = r
        front = new
    deg = np.asarray(a.sum(1)).ravel()
    deg[deg == 0] = 1
    w = diags(1.0 / deg) @ a
    band = np.nonzero(ring > 0)[0]
    weight = (1.0 - ring[band] / (rings + 1.0))[:, None]
    sub = w[band]
    for _ in range(4):
        v[band] = v[band] + 0.6 * weight * (sub @ v - v[band])
    return Mesh(v, mesh.faces, mesh.colors)
