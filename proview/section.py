"""Planar cross-sections of meshes and gap measurement between two section curves."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree


def plane_section(vertices: np.ndarray, faces: np.ndarray, origin, normal) -> np.ndarray:
    """Intersect a triangle mesh with a plane. Returns segments (k, 2, 3) in the same space."""
    origin = np.asarray(origin, float)
    normal = np.asarray(normal, float)
    normal = normal / (np.linalg.norm(normal) or 1.0)
    if len(faces) == 0:
        return np.zeros((0, 2, 3))
    d = (vertices - origin) @ normal
    # nudge vertices lying exactly on the plane so every crossing edge is well defined
    d = np.where(d == 0.0, 1e-12, d)
    fd = d[faces]  # (m, 3)
    pos = fd > 0
    npos = pos.sum(1)
    cross = (npos == 1) | (npos == 2)
    if not cross.any():
        return np.zeros((0, 2, 3))
    f = faces[cross]
    fd = fd[cross]
    pos = pos[cross]
    # the "odd" vertex is the one alone on its side
    lone_pos = pos.sum(1) == 1
    odd = np.where(lone_pos, np.argmax(pos, 1), np.argmax(~pos, 1))
    i0 = odd
    i1 = (odd + 1) % 3
    i2 = (odd + 2) % 3
    rows = np.arange(len(f))
    v = vertices[f]  # (k, 3, 3)
    a, b, c = v[rows, i0], v[rows, i1], v[rows, i2]
    da, db, dc = fd[rows, i0], fd[rows, i1], fd[rows, i2]
    t1 = (da / (da - db))[:, None]
    t2 = (da / (da - dc))[:, None]
    p1 = a + (b - a) * t1
    p2 = a + (c - a) * t2
    return np.stack([p1, p2], 1)


def plane_basis(normal, up_hint) -> tuple[np.ndarray, np.ndarray]:
    """Two orthonormal in-plane axes (u = 'right', v = 'up' as close to up_hint as possible)."""
    n = np.asarray(normal, float)
    n = n / (np.linalg.norm(n) or 1.0)
    up = np.asarray(up_hint, float)
    v = up - n * (up @ n)
    if np.linalg.norm(v) < 1e-9:
        v = np.cross(n, [1.0, 0.0, 0.0])
        if np.linalg.norm(v) < 1e-9:
            v = np.cross(n, [0.0, 1.0, 0.0])
    v = v / np.linalg.norm(v)
    u = np.cross(v, n)
    return u, v


def to_plane_2d(points: np.ndarray, origin, u, v) -> np.ndarray:
    rel = np.asarray(points, float) - np.asarray(origin, float)
    return np.stack([rel @ u, rel @ v], -1)


@dataclass
class GapResult:
    points: np.ndarray  # (n, 2) sample points on the compared curve
    nearest: np.ndarray  # (n, 2) nearest point on the reference curve
    distance: np.ndarray  # (n,)

    @property
    def max_index(self) -> int:
        return int(np.argmax(self.distance)) if len(self.distance) else -1

    @property
    def max(self) -> float:
        return float(self.distance.max()) if len(self.distance) else 0.0

    @property
    def mean(self) -> float:
        return float(self.distance.mean()) if len(self.distance) else 0.0


class SegmentSet:
    """Fast exact point-to-polyline distance for a set of 2D segments."""

    def __init__(self, segs: np.ndarray):
        self.segs = np.asarray(segs, float).reshape(-1, 2, 2)
        self.a = self.segs[:, 0]
        self.ab = self.segs[:, 1] - self.segs[:, 0]
        mids = self.segs.mean(1)
        self.tree = cKDTree(mids) if len(mids) else None
        lengths = np.linalg.norm(self.ab, axis=1)
        self.half_max = float(lengths.max()) / 2 if len(lengths) else 0.0

    def nearest(self, pts: np.ndarray, k: int = 12):
        pts = np.asarray(pts, float).reshape(-1, 2)
        if self.tree is None or len(pts) == 0:
            return np.full(len(pts), np.inf), np.zeros_like(pts)
        k = min(k, len(self.segs))
        _, idx = self.tree.query(pts, k=k)
        idx = idx.reshape(len(pts), k)
        a = self.a[idx]  # (n, k, 2)
        ab = self.ab[idx]
        denom = np.einsum("nkj,nkj->nk", ab, ab)
        denom[denom == 0] = 1.0
        t = np.clip(np.einsum("nkj,nkj->nk", pts[:, None] - a, ab) / denom, 0.0, 1.0)
        proj = a + ab * t[..., None]
        dist = np.linalg.norm(proj - pts[:, None], axis=2)
        best = np.argmin(dist, 1)
        rows = np.arange(len(pts))
        return dist[rows, best], proj[rows, best]


def gap_analysis(reference_segs: np.ndarray, compared_segs: np.ndarray, spacing: float | None = None) -> GapResult:
    """Distance from points along the compared curve to the reference curve (all 2D)."""
    comp = np.asarray(compared_segs, float).reshape(-1, 2, 2)
    if len(comp) == 0 or len(reference_segs) == 0:
        empty = np.zeros((0, 2))
        return GapResult(empty, empty, np.zeros(0))
    # sample the compared curve: segment end points plus extra points on long segments
    pts = [comp[:, 0], comp[:, 1]]
    if spacing:
        lengths = np.linalg.norm(comp[:, 1] - comp[:, 0], axis=1)
        for s, n in zip(comp[lengths > spacing], (lengths[lengths > spacing] // spacing).astype(int)):
            t = np.linspace(0, 1, n + 2)[1:-1, None]
            pts.append(s[0] + (s[1] - s[0]) * t)
    pts = np.unique(np.vstack(pts).round(9), axis=0)
    dist, near = SegmentSet(reference_segs).nearest(pts)
    return GapResult(pts, near, dist)
