"""Model builder: turn a scan (open surface, teeth up) into a printable dental model.

Steps
  1. the scan's open edge is extended straight down to a flat base (z0) -> closed solid
  2. optional hollowing: the inside is removed, keeping walls of a given thickness,
     with the base left open so resin can drain
  3. optional honeycomb: hexagonal ribs inside the hollow part for strength

The outer surface keeps the scan exactly; the inner (hollow) surface is made from
a voxel grid with marching cubes.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .mesh import Mesh


@dataclass
class BuildOptions:
    base_height: float = 5.0  # mm from the lowest scan point down to the base plane
    hollow: bool = True
    wall: float = 2.0  # wall thickness (mm)
    honeycomb: bool = True
    cell: float = 6.0  # honeycomb cell size, flat to flat (mm)
    rib: float = 1.0  # honeycomb rib thickness (mm)
    voxel: float = 0.2  # voxel size for the hollow part (mm)
    edge_smooth: float = 1.0  # smooth the scan's open edge over this distance (mm), 0 = off
    inner_smooth: float = 2.5  # inner surface is a union of balls of this radius (mm), 0 = follow outside
    auto_orient: bool = True  # find the teeth direction (upper / lower jaw) automatically
    trim: bool = True  # cut the scan's edge flat (removes hanging tissue, undercut flaps)
    trim_offset: float = 0.0  # mm; 0 = automatic level, positive = cut higher


MAX_VOXELS = 40_000_000


class BuildError(Exception):
    pass


# ---------------------------------------------------------------------- loops
def boundary_loops(faces: np.ndarray) -> list[list[int]]:
    """Ordered boundary loops, following the faces' edge direction."""
    e = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    key = e[:, 0].astype(np.int64) * (int(faces.max()) + 1) + e[:, 1]
    rkey = e[:, 1].astype(np.int64) * (int(faces.max()) + 1) + e[:, 0]
    boundary = e[~np.isin(key, rkey)]
    nxt: dict[int, list[int]] = {}
    for a, b in boundary:
        nxt.setdefault(int(a), []).append(int(b))
    loops = []
    while nxt:
        start = next(iter(nxt))
        loop = [start]
        cur = start
        while True:
            outs = nxt.get(cur)
            if not outs:
                break
            b = outs.pop()
            if not outs:
                del nxt[cur]
            if b == start:
                break
            loop.append(b)
            cur = b
            if len(loop) > len(boundary) + 1:
                break
        if len(loop) >= 3:
            loops.append(loop)
    return loops


def _loop_length(v, loop):
    p = v[loop]
    return float(np.linalg.norm(p - np.roll(p, -1, 0), axis=1).sum())


def fill_small_holes(mesh: Mesh, keep_loop: list[int]) -> Mesh:
    """Close every boundary loop except ``keep_loop`` with a fan around its centre."""
    verts = [mesh.vertices]
    faces = [mesh.faces]
    n = mesh.n_vertices
    keep = set(keep_loop)
    for loop in boundary_loops(mesh.faces):
        if set(loop) & keep:
            continue
        c = mesh.vertices[loop].mean(0)
        verts.append(c[None])
        lp = np.array(loop)
        faces.append(np.stack([np.roll(lp, -1), lp, np.full(len(lp), n)], 1))
        n += 1
    return Mesh(np.vstack(verts), np.vstack(faces))


def _smooth_loop_xy(p: np.ndarray, iterations: int = 10) -> np.ndarray:
    q = p.copy()
    for _ in range(iterations):
        q = 0.5 * q + 0.25 * (np.roll(q, 1, 0) + np.roll(q, -1, 0))
    return q


# ---------------------------------------------------------------------- vtk helpers
def _to_polydata(v, f):
    from .mesh import to_polydata

    return to_polydata(Mesh(v, f))


def _from_polydata(pd) -> Mesh:
    from vtkmodules.util.numpy_support import vtk_to_numpy
    from vtkmodules.vtkFiltersCore import vtkTriangleFilter

    tri = vtkTriangleFilter()
    tri.SetInputData(pd)
    tri.Update()
    out = tri.GetOutput()
    if out.GetNumberOfPoints() == 0:
        return Mesh(np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64))
    v = vtk_to_numpy(out.GetPoints().GetData()).astype(np.float64)
    conn = vtk_to_numpy(out.GetPolys().GetConnectivityArray()).reshape(-1, 3)
    return Mesh(v, conn)


def _triangulate_planar_loops(loops_xy: list[np.ndarray], z: float) -> Mesh:
    """Triangulate the region bounded by closed 2D loops (outer boundary and holes)."""
    from vtkmodules.vtkCommonCore import vtkPoints
    from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData
    from vtkmodules.vtkFiltersGeneral import vtkContourTriangulator

    pts = vtkPoints()
    pts.SetDataTypeToDouble()
    lines = vtkCellArray()
    k = 0
    for loop in loops_xy:
        n = len(loop)
        lines.InsertNextCell(n + 1)
        for x, y in loop:
            pts.InsertNextPoint(float(x), float(y), z)
        for i in range(n):
            lines.InsertCellPoint(k + i)
        lines.InsertCellPoint(k)
        k += n
    pd = vtkPolyData()
    pd.SetPoints(pts)
    pd.SetLines(lines)
    tri = vtkContourTriangulator()
    tri.SetInputData(pd)
    tri.Update()
    out = _from_polydata(tri.GetOutput())
    exact = np.column_stack([np.vstack(loops_xy), np.full(k, z)])
    if out.n_vertices == k:  # the triangulator keeps the input points: use the exact coordinates
        out = Mesh(exact, out.faces)
    return out


def signed_volume(v, f) -> float:
    a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)


# ---------------------------------------------------------------------- voxels
def _column_crossings(v, f, x0, y0, h, nx, ny):
    """z of every crossing of vertical rays through voxel-column centres with the triangles."""
    tri = v[f]
    xy = tri[:, :, :2]
    lo = xy.min(1)
    hi = xy.max(1)
    i0 = np.ceil((lo[:, 0] - x0) / h - 0.5).astype(np.int64)
    i1 = np.floor((hi[:, 0] - x0) / h - 0.5).astype(np.int64)
    j0 = np.ceil((lo[:, 1] - y0) / h - 0.5).astype(np.int64)
    j1 = np.floor((hi[:, 1] - y0) / h - 0.5).astype(np.int64)
    i0, j0 = np.maximum(i0, 0), np.maximum(j0, 0)
    i1, j1 = np.minimum(i1, nx - 1), np.minimum(j1, ny - 1)
    ni = np.maximum(i1 - i0 + 1, 0)
    nj = np.maximum(j1 - j0 + 1, 0)
    cnt = ni * nj
    keep = cnt > 0
    cols_all, z_all = [], []
    idx = np.nonzero(keep)[0]
    for chunk in np.array_split(idx, max(1, int(cnt[keep].sum() // 4_000_000) + 1)):
        if len(chunk) == 0:
            continue
        c = cnt[chunk]
        rep = np.repeat(chunk, c)
        start = np.repeat(np.cumsum(c) - c, c)
        k = np.arange(len(rep)) - start
        ii = i0[rep] + k % ni[rep]
        jj = j0[rep] + k // ni[rep]
        px = x0 + (ii + 0.5) * h
        py = y0 + (jj + 0.5) * h
        a, b, cc = tri[rep, 0], tri[rep, 1], tri[rep, 2]
        d = (b[:, 0] - a[:, 0]) * (cc[:, 1] - a[:, 1]) - (cc[:, 0] - a[:, 0]) * (b[:, 1] - a[:, 1])
        ok = np.abs(d) > 1e-18
        d = np.where(ok, d, 1.0)
        w1 = ((px - a[:, 0]) * (cc[:, 1] - a[:, 1]) - (cc[:, 0] - a[:, 0]) * (py - a[:, 1])) / d
        w2 = ((b[:, 0] - a[:, 0]) * (py - a[:, 1]) - (px - a[:, 0]) * (b[:, 1] - a[:, 1])) / d
        w0 = 1 - w1 - w2
        inside = ok & (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
        z = w0 * a[:, 2] + w1 * b[:, 2] + w2 * cc[:, 2]
        cols_all.append((jj * nx + ii)[inside])
        z_all.append(z[inside])
    if not cols_all:
        return np.zeros(0, np.int64), np.zeros(0)
    return np.concatenate(cols_all), np.concatenate(z_all)


def voxelize_open_bottom(v, f, z0, x0, y0, zg0, h, nx, ny, nz) -> np.ndarray:
    """Inside test for the solid bounded by an open-bottom surface and the plane z0.

    Each column's crossings with the surface are paired from the top; a column with
    an odd number of crossings is closed at z0.
    """
    cols, z = _column_crossings(v, f, x0, y0, h, nx, ny)
    occ = np.zeros((ny * nx, nz + 1), np.int16)
    if len(cols):
        counts = np.bincount(cols, minlength=nx * ny)
        odd = np.nonzero(counts % 2 == 1)[0]
        cols = np.concatenate([cols, odd])
        z = np.concatenate([z, np.full(len(odd), z0)])
        order = np.lexsort((z, cols))
        cols, z = cols[order], z[order]
        first = np.r_[True, cols[1:] != cols[:-1]]
        pos = np.arange(len(cols)) - np.maximum.accumulate(np.where(first, np.arange(len(cols)), 0))
        s_mask = pos % 2 == 0
        starts, ends = np.nonzero(s_mask)[0], np.nonzero(s_mask)[0] + 1
        valid = ends < len(cols)
        starts, ends = starts[valid], ends[valid]
        valid = cols[starts] == cols[ends]
        starts, ends = starts[valid], ends[valid]
        ks = np.clip(np.ceil((z[starts] - zg0) / h - 0.5).astype(np.int64), 0, nz)
        ke = np.clip(np.floor((z[ends] - zg0) / h - 0.5).astype(np.int64) + 1, 0, nz)
        good = ke > ks
        np.add.at(occ, (cols[starts][good], ks[good]), 1)
        np.add.at(occ, (cols[ends][good], ke[good]), -1)
    inside = np.cumsum(occ, axis=1)[:, :nz] > 0
    return inside.reshape(ny, nx, nz).transpose(1, 0, 2)  # (nx, ny, nz)


def hex_ribs(nx, ny, x0, y0, h, cell, rib) -> np.ndarray:
    """(nx, ny) mask of vertical honeycomb walls (pointy-top hexagons, flat-to-flat = cell)."""
    return hex_cell_field(nx, ny, x0, y0, h, cell, rib) <= 0


def hex_cell_field(nx, ny, x0, y0, h, cell, rib) -> np.ndarray:
    """(nx, ny) distance (mm) into the open part of the nearest honeycomb cell; <= 0 on the ribs."""
    xs = x0 + (np.arange(nx) + 0.5) * h
    ys = y0 + (np.arange(ny) + 0.5) * h
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    r = cell / 2.0  # inradius
    # lattice of centres: columns spaced 2r apart, rows 1.5 * circumradius
    R = r * 2 / np.sqrt(3)
    dy = 1.5 * R
    row = np.round(Y / dy)
    best = np.full(X.shape, np.inf)
    for drow in (-1, 0, 1):
        rr = row + drow
        cy = rr * dy
        shift = np.where(rr % 2 == 0, 0.0, r)
        cx = np.round((X - shift) / (2 * r)) * 2 * r + shift
        px, py = X - cx, Y - cy
        # hexagon "radius" in the inradius metric (pointy-top: flat sides left/right)
        d = np.maximum(np.abs(px), np.abs(px) * 0.5 + np.abs(py) * np.sqrt(3) / 2)
        best = np.minimum(best, d)
    return (r - rib / 2.0) - best


# ---------------------------------------------------------------------- main
def build_model(scan: Mesh, opts: BuildOptions, progress=lambda text: None) -> Mesh:
    """Make a closed (optionally hollow, honeycomb-reinforced) model from a scan in world space."""
    if scan.n_faces == 0:
        raise BuildError("The model is empty.")
    progress("Finding the scan edge")
    loops = boundary_loops(scan.faces)
    if not loops:
        raise BuildError("The model is already closed (no open edge). Use a scan, not a solid model.")
    v = scan.vertices
    main = max(loops, key=lambda lp: _loop_length(v, lp))
    R = np.eye(3)
    if opts.auto_orient:
        # teeth direction: away from the plane of the open edge, towards the bulk of the scan
        R = rotation_to_z(detect_up(v, main))
        scan = Mesh(v @ R.T, scan.faces, scan.colors)
        v = scan.vertices
    edge_z = v[main][:, 2].mean()
    if edge_z > (v[:, 2].min() + v[:, 2].max()) / 2:
        raise BuildError("The open edge of the scan points up. Turn the model so the teeth point up "
                         "(Orient tool), or switch on automatic orientation.")
    from .repair import fill_holes, remove_dangling_faces, smooth_open_edge

    if opts.trim:
        # a flat cut just above most of the edge: hanging flaps and edges that fold back
        # under the model are removed, the new edge is a clean line
        progress("Trimming the scan edge")
        z_cut = float(np.quantile(v[main][:, 2], 0.9)) + opts.trim_offset
        if z_cut >= v[:, 2].max() - 0.5:
            raise BuildError("The trim level is above the teeth. Lower the trim level.")
        cut = _clip_above(Mesh(v, scan.faces), z_cut)
        cut = remove_dangling_faces(cut)
        if cut.n_faces == 0:
            raise BuildError("Nothing is left after trimming the edge. Lower the trim level.")
        scan = split_parts(cut, min_share=0.0, min_faces=1)[0]  # the largest piece
        v = scan.vertices
        loops = boundary_loops(scan.faces)
        if not loops:
            raise BuildError("The trimmed scan has no open edge.")
        main = max(loops, key=lambda lp: _loop_length(v, lp))

    progress("Closing small holes")
    mesh, _, _ = fill_holes(scan, None, keep=main)
    mesh = Mesh(mesh.vertices, mesh.faces)
    # vertex numbers can change while cleaning: find the open edge again
    loops = boundary_loops(mesh.faces)
    if not loops:
        raise BuildError("The model has no open edge after closing its holes.")
    main = max(loops, key=lambda lp: _loop_length(mesh.vertices, lp))
    if opts.edge_smooth > 0:
        mesh = smooth_open_edge(mesh, main, opts.edge_smooth)
    z0 = float(mesh.vertices[:, 2].min()) - opts.base_height

    # ---------------- outer solid: scan + vertical walls down to z0
    progress("Building the base")
    v_out, f_out, bottom_xy = _outer(mesh, main, z0)
    # scans can be stored inside-out: make the closed outer solid face outwards
    cap0 = _triangulate_planar_loops([bottom_xy], z0)
    cf = cap0.faces[:, ::-1] if cap0.face_normals()[:, 2].mean() > 0 else cap0.faces
    vol = signed_volume(np.vstack([v_out, cap0.vertices]), np.vstack([f_out, cf + len(v_out)]))
    if vol < 0:
        mesh = Mesh(mesh.vertices, mesh.faces[:, ::-1])
        v_out, f_out, bottom_xy = _outer(mesh, main[::-1], z0)

    bottom_loops = [bottom_xy]
    inner = None
    if opts.hollow:
        inner, holes = _hollow(v_out, f_out, z0, opts, progress)
        bottom_loops += holes

    progress("Closing the base")
    cap = _triangulate_planar_loops(bottom_loops, z0)
    if cap.n_faces == 0:
        raise BuildError("Could not close the base (the scan edge crosses itself when seen from above).")
    cap_f = cap.faces
    if cap.face_normals()[:, 2].mean() > 0:  # the base must face down
        cap_f = cap_f[:, ::-1]

    parts_v = [v_out, cap.vertices]
    parts_f = [f_out, cap_f + len(v_out)]
    if inner is not None and inner.n_faces:
        parts_v.append(inner.vertices)
        parts_f.append(inner.faces + len(v_out) + cap.n_vertices)
    allv = np.vstack(parts_v)
    allf = np.vstack(parts_f)

    progress("Joining the surfaces")
    result = _merge_points(allv, allf)
    # safety net: close any small gap left where base openings touch each other
    if boundary_loops(result.faces):
        from .repair import fill_holes

        progress("Checking the model is closed")
        result, _, _ = fill_holes(result, None)
        result = Mesh(result.vertices, result.faces)
    if opts.auto_orient:  # back to the scan's own position
        result = Mesh(result.vertices @ R, result.faces)
    return result


def detect_up(v: np.ndarray, edge_loop) -> np.ndarray:
    """Unit vector pointing from the scan's open edge towards the teeth."""
    p = v[edge_loop]
    c = p.mean(0)
    _, _, vt = np.linalg.svd(p - c, full_matrices=False)
    n = vt[2]
    if ((v - c) @ n).mean() < 0:
        n = -n
    return n / np.linalg.norm(n)


def rotation_to_z(n: np.ndarray) -> np.ndarray:
    """Rotation matrix R with R @ n = +Z."""
    z = np.array([0.0, 0.0, 1.0])
    n = n / np.linalg.norm(n)
    c = float(n @ z)
    if c > 1 - 1e-12:
        return np.eye(3)
    if c < -1 + 1e-12:
        return np.diag([1.0, -1.0, -1.0])
    axis = np.cross(n, z)
    s = np.linalg.norm(axis)
    axis /= s
    K = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    return np.eye(3) + s * K + (1 - c) * K @ K


def split_parts(mesh: Mesh, min_share: float = 0.02, min_faces: int = 200) -> list[Mesh]:
    """Separate pieces (e.g. upper and lower arch in one file), small debris dropped."""
    count, labels = mesh.connected_components()
    if count <= 1:
        return [mesh]
    sizes = np.bincount(labels, minlength=count)
    keep = [i for i in np.argsort(-sizes) if sizes[i] >= max(min_faces, min_share * mesh.n_faces)]
    return [mesh.keep_faces(labels == i) for i in keep] or [mesh]


def build_models(scan: Mesh, opts: BuildOptions, progress=lambda text: None) -> list[Mesh]:
    """One model per separate piece of the scan."""
    parts = split_parts(scan)
    out = []
    for i, part in enumerate(parts):
        prefix = f"Part {i + 1}/{len(parts)}: " if len(parts) > 1 else ""
        out.append(build_model(part, opts, lambda t, p=prefix: progress(p + t)))
    return out


def _outer(mesh: Mesh, loop_list, z0):
    """Scan + vertical walls from its open edge down to z0 (open at the bottom)."""
    v, f = mesh.vertices, mesh.faces
    loop = np.array(loop_list)
    bottom_xy = _smooth_loop_xy(v[loop][:, :2])
    nb = len(loop)
    bottom_idx = np.arange(len(v), len(v) + nb)
    v_out = np.vstack([v, np.column_stack([bottom_xy, np.full(nb, z0)])])
    a, a_next = loop, np.roll(loop, -1)
    b, b_next = bottom_idx, np.roll(bottom_idx, -1)
    walls = np.vstack([np.stack([a_next, a, b], 1), np.stack([a_next, b, b_next], 1)])
    return v_out, np.vstack([f, walls]), bottom_xy


def _merge_points(v, f, tol=1e-6) -> Mesh:
    key = np.round(v / tol).astype(np.int64)
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    inv = inv.reshape(-1)
    f2 = inv[f]
    ok = (f2[:, 0] != f2[:, 1]) & (f2[:, 1] != f2[:, 2]) & (f2[:, 0] != f2[:, 2])
    return Mesh(v[first], f2[ok]).keep_faces(np.ones(int(ok.sum()), bool))


def _hollow(v_out, f_out, z0, opts: BuildOptions, progress):
    """Inner surface of the hollow model and the 2D outlines of its openings in the base."""
    from scipy import ndimage

    h = float(opts.voxel)
    lo = v_out.min(0)
    hi = v_out.max(0)
    pad = 2
    below = 3  # voxel layers under the base plane (the cavity runs out through the base)
    # small irrational offset so rays never pass exactly through vertices
    x0 = lo[0] - pad * h + 0.0137 * h
    y0 = lo[1] - pad * h + 0.0291 * h
    zg0 = z0 - below * h
    nx = int(np.ceil((hi[0] - x0) / h)) + pad
    ny = int(np.ceil((hi[1] - y0) / h)) + pad
    nz = int(np.ceil((hi[2] - zg0) / h)) + pad
    if nx * ny * nz > MAX_VOXELS:
        # the inside is smooth anyway: use a coarser grid instead of refusing
        h *= (nx * ny * nz / MAX_VOXELS) ** (1 / 3) * 1.02
        progress(f"Large model: inside resolution {h:.2f} mm")
        x0 = lo[0] - pad * h + 0.0137 * h
        y0 = lo[1] - pad * h + 0.0291 * h
        zg0 = z0 - below * h
        nx = int(np.ceil((hi[0] - x0) / h)) + pad
        ny = int(np.ceil((hi[1] - y0) / h)) + pad
        nz = int(np.ceil((hi[2] - zg0) / h)) + pad

    progress("Measuring the inside")
    inside = voxelize_open_bottom(v_out, f_out, z0, x0, y0, zg0, h, nx, ny, nz)
    k0 = int(np.floor((z0 - zg0) / h))  # first layer at/above the base plane
    inside[:, :, :k0 + 1] = inside[:, :, k0 + 1:k0 + 2]  # extend through the base: no floor
    progress("Hollowing")
    # f > 0 inside the cavity; a continuous distance field gives a smooth inner surface
    f = (ndimage.distance_transform_edt(inside).astype(np.float32) * h) - np.float32(opts.wall)
    del inside
    if opts.inner_smooth > 0:
        # opening with a ball: the cavity becomes a union of balls -> smooth, does not follow
        # the teeth, and is never closer to the outside than the wall thickness
        progress("Smoothing the inside")
        r = np.float32(opts.inner_smooth)
        core = ndimage.distance_transform_edt(f > 0).astype(np.float32) * h > r
        opened = r - ndimage.distance_transform_edt(~core).astype(np.float32) * h
        del core
        f = np.minimum(f, opened)
        del opened
    if opts.honeycomb:
        g = hex_cell_field(nx, ny, x0, y0, h, opts.cell, opts.rib).astype(np.float32)
        f = np.minimum(f, g[:, :, None])
        del g
    # keep only cavity parts open to the base (no sealed bubbles)
    labels, n = ndimage.label(f > 0)
    if n == 0:
        return None, []
    open_labels = np.unique(labels[:, :, 0])
    open_labels = open_labels[open_labels > 0]
    sealed = (labels > 0) & ~np.isin(labels, open_labels)
    del labels
    f[sealed] = -h
    del sealed
    if not (f > 0).any():
        return None, []

    progress("Making the inner surface")
    field = ndimage.gaussian_filter(f, 0.6)
    del f
    surf = _marching(field, (x0 + 0.5 * h, y0 + 0.5 * h, zg0 + 0.5 * h), h, level=0.0)
    del field
    if surf.n_faces == 0:
        return None, []
    # orient: normals must point into the cavity (= out of the solid material)
    if signed_volume(surf.vertices, surf.faces) > 0:
        surf = Mesh(surf.vertices, surf.faces[:, ::-1])

    progress("Opening the base")
    clipped = _clip_above(surf, z0)
    holes = []
    for lp in boundary_loops(clipped.faces):
        p = clipped.vertices[lp]
        if np.all(np.abs(p[:, 2] - z0) < 1e-4):
            holes.append(p[:, :2])
    return clipped, holes


def _marching(field, origin, h, level=0.5) -> Mesh:
    from vtkmodules.util.numpy_support import numpy_to_vtk
    from vtkmodules.vtkCommonDataModel import vtkImageData
    from vtkmodules.vtkFiltersCore import vtkFlyingEdges3D

    nx, ny, nz = field.shape
    img = vtkImageData()
    img.SetDimensions(nx, ny, nz)
    img.SetSpacing(h, h, h)
    img.SetOrigin(*origin)
    arr = numpy_to_vtk(np.ascontiguousarray(field.transpose(2, 1, 0)).ravel(), deep=True)
    img.GetPointData().SetScalars(arr)
    fe = vtkFlyingEdges3D()
    fe.SetInputData(img)
    fe.SetValue(0, level)
    fe.ComputeNormalsOff()
    fe.ComputeGradientsOff()
    fe.Update()
    return _from_polydata(fe.GetOutput())


def _clip_above(mesh: Mesh, z0: float) -> Mesh:
    from vtkmodules.vtkCommonDataModel import vtkPlane
    from vtkmodules.vtkFiltersCore import vtkClipPolyData

    plane = vtkPlane()
    plane.SetOrigin(0, 0, z0)
    plane.SetNormal(0, 0, 1)
    clip = vtkClipPolyData()
    clip.SetInputData(_to_polydata(mesh.vertices, mesh.faces))
    clip.SetClipFunction(plane)
    clip.SetOutputPointsPrecision(1)  # double
    clip.Update()
    out = _from_polydata(clip.GetOutput())
    # snap the cut edge exactly onto the plane
    near = np.abs(out.vertices[:, 2] - z0) < 1e-5
    out.vertices[near, 2] = z0
    return _merge_points(out.vertices, out.faces, tol=1e-7)
