"""Screen-space helpers: projection, polygon tests, z-buffer and ray picking."""
from __future__ import annotations

import numpy as np


# ------------------------------------------------------------ pure geometry
def points_in_polygon(pts: np.ndarray, poly: np.ndarray) -> np.ndarray:
    """Even-odd rule point-in-polygon, vectorised over ``pts`` (k, 2)."""
    pts = np.asarray(pts, dtype=np.float64)
    poly = np.asarray(poly, dtype=np.float64)
    inside = np.zeros(len(pts), dtype=bool)
    if len(poly) < 3 or len(pts) == 0:
        return inside
    x, y = pts[:, 0], pts[:, 1]
    xj, yj = poly[-1]
    for xi, yi in poly:
        if yi != yj:
            cond = (yi > y) != (yj > y)
            xcross = (xj - xi) * (y - yi) / (yj - yi) + xi
            inside ^= cond & (x < xcross)
        xj, yj = xi, yi
    return inside


def segment_distance(pts: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Distance from 2D points to the segment a-b."""
    ab = b - a
    denom = float(ab @ ab)
    if denom == 0:
        return np.linalg.norm(pts - a, axis=1)
    t = np.clip(((pts - a) @ ab) / denom, 0.0, 1.0)
    proj = a + t[:, None] * ab
    return np.linalg.norm(pts - proj, axis=1)


def _vtk_matrix_to_numpy(m) -> np.ndarray:
    return np.array([[m.GetElement(i, j) for j in range(4)] for i in range(4)])


# ------------------------------------------------------------ VTK helpers
def renderer_pixel_rect(renderer) -> tuple[int, int, int, int]:
    """(x0, y0, width, height) of the renderer viewport in pixels."""
    w, h = renderer.GetRenderWindow().GetActualSize()
    vp = renderer.GetViewport()
    x0, y0 = int(round(vp[0] * w)), int(round(vp[1] * h))
    x1, y1 = int(round(vp[2] * w)), int(round(vp[3] * h))
    return x0, y0, max(x1 - x0, 1), max(y1 - y0, 1)


def project(renderer, pts: np.ndarray) -> np.ndarray:
    """World points -> display coordinates (x, y in pixels, z in [0, 1] depth)."""
    cam = renderer.GetActiveCamera()
    aspect = renderer.GetTiledAspectRatio()
    M = _vtk_matrix_to_numpy(cam.GetCompositeProjectionTransformMatrix(aspect, 0, 1))
    h = pts @ M[:3, :3].T + M[:3, 3]
    w = pts @ M[3, :3] + M[3, 3]
    w = np.where(np.abs(w) < 1e-12, 1e-12, w)
    ndc = h / w[:, None]
    x0, y0, ww, hh = renderer_pixel_rect(renderer)
    out = np.empty_like(ndc)
    out[:, 0] = (ndc[:, 0] + 1.0) * 0.5 * ww + x0
    out[:, 1] = (ndc[:, 1] + 1.0) * 0.5 * hh + y0
    out[:, 2] = ndc[:, 2]
    return out


def display_ray(renderer, x: float, y: float) -> tuple[np.ndarray, np.ndarray]:
    """World-space ray (origin, unit direction) through display pixel (x, y)."""
    renderer.SetDisplayPoint(x, y, 0.0)
    renderer.DisplayToWorld()
    p0 = np.array(renderer.GetWorldPoint(), dtype=np.float64)
    renderer.SetDisplayPoint(x, y, 1.0)
    renderer.DisplayToWorld()
    p1 = np.array(renderer.GetWorldPoint(), dtype=np.float64)
    p0 = p0[:3] / (p0[3] or 1.0)
    p1 = p1[:3] / (p1[3] or 1.0)
    d = p1 - p0
    n = np.linalg.norm(d)
    return p0, d / (n if n else 1.0)


def focal_plane_point(renderer, x: float, y: float) -> np.ndarray:
    """Point under the cursor on the plane through the camera focal point."""
    cam = renderer.GetActiveCamera()
    o, d = display_ray(renderer, x, y)
    fp = np.array(cam.GetFocalPoint())
    n = np.array(cam.GetDirectionOfProjection())
    denom = float(d @ n)
    if abs(denom) < 1e-12:
        return fp
    return o + d * float((fp - o) @ n) / denom


def read_zbuffer(renderer) -> tuple[np.ndarray, tuple[int, int, int, int]] | None:
    """Depth buffer of the renderer viewport as a (h, w) array, row 0 = bottom."""
    from vtkmodules.util.numpy_support import vtk_to_numpy
    from vtkmodules.vtkCommonCore import vtkFloatArray

    rw = renderer.GetRenderWindow()
    x0, y0, w, h = renderer_pixel_rect(renderer)
    arr = vtkFloatArray()
    try:
        rw.GetZbufferData(x0, y0, x0 + w - 1, y0 + h - 1, arr)
    except Exception:  # pragma: no cover - driver specific
        return None
    z = vtk_to_numpy(arr)
    if z.size != w * h:
        return None
    z = z.reshape(h, w).copy()
    if float(z.min()) >= 1.0:  # nothing rendered / unreadable buffer
        return None
    return z, (x0, y0, w, h)


def visible_mask(renderer, centroids, normals, disp, zbuf, tol_world) -> np.ndarray:
    """Which faces (given world centroids/normals and their projection) are visible."""
    cam = renderer.GetActiveCamera()
    if cam.GetParallelProjection():
        to_cam = -np.array(cam.GetDirectionOfProjection())[None, :].repeat(len(centroids), 0)
    else:
        to_cam = np.array(cam.GetPosition())[None, :] - centroids
        ln = np.linalg.norm(to_cam, axis=1, keepdims=True)
        ln[ln == 0] = 1.0
        to_cam = to_cam / ln
    facing = np.einsum("ij,ij->i", normals, to_cam) > 0.0
    if zbuf is None:
        return facing
    z, (x0, y0, w, h) = zbuf
    px = np.floor(disp[:, 0] - x0).astype(np.int64)
    py = np.floor(disp[:, 1] - y0).astype(np.int64)
    on = (px >= 0) & (px < w) & (py >= 0) & (py < h)
    vis = np.zeros(len(centroids), dtype=bool)
    idx = np.nonzero(on & facing)[0]
    if len(idx) == 0:
        return vis
    from scipy.ndimage import maximum_filter

    zmax = maximum_filter(z, size=3, mode="nearest")
    moved = centroids[idx] + to_cam[idx] * tol_world
    zc = project(renderer, moved)[:, 2]
    vis[idx] = zc <= zmax[py[idx], px[idx]] + 1e-6
    return vis


def pick_mesh(renderer, x, y, world_vertices: np.ndarray, faces: np.ndarray):
    """Ray-cast pick against a triangle mesh. Returns (distance, point) or None."""
    if len(faces) == 0:
        return None
    disp = project(renderer, world_vertices)[:, :2]
    tri2 = disp[faces]  # (m, 3, 2)
    lo = tri2.min(axis=1)
    hi = tri2.max(axis=1)
    cand = np.nonzero((lo[:, 0] <= x + 1) & (hi[:, 0] >= x - 1) & (lo[:, 1] <= y + 1) & (hi[:, 1] >= y - 1))[0]
    if len(cand) == 0:
        return None
    o, d = display_ray(renderer, x, y)
    tri = world_vertices[faces[cand]]
    v0, e1, e2 = tri[:, 0], tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]
    pvec = np.cross(d[None, :], e2)
    det = np.einsum("ij,ij->i", e1, pvec)
    ok = np.abs(det) > 1e-14
    inv = np.zeros_like(det)
    inv[ok] = 1.0 / det[ok]
    tvec = o - v0
    u = np.einsum("ij,ij->i", tvec, pvec) * inv
    qvec = np.cross(tvec, e1)
    v = (qvec @ d) * inv
    t = np.einsum("ij,ij->i", e2, qvec) * inv
    eps = 1e-9
    hit = ok & (u >= -eps) & (v >= -eps) & (u + v <= 1 + eps) & (t > 0)
    if not hit.any():
        return None
    k = np.argmin(np.where(hit, t, np.inf))
    return float(t[k]), o + d * t[k]
