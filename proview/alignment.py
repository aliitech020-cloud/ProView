"""Rigid alignment: point-pair (Kabsch), best-fit (ICP) and automatic alignment.

All functions work in world coordinates and return 4x4 matrices ``T`` such
that ``T @ floating`` lies on ``fixed``.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree

from .mesh import transform_points


@dataclass
class AlignResult:
    matrix: np.ndarray
    rms: float  # RMS distance of inlier pairs
    inlier_fraction: float  # share of floating samples within the inlier distance
    iterations: int = 0


def make_matrix(R: np.ndarray, t: np.ndarray) -> np.ndarray:
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = t
    return T


def kabsch(src: np.ndarray, dst: np.ndarray, weights: np.ndarray | None = None) -> np.ndarray:
    """Best rigid transform mapping ``src`` points onto ``dst`` points."""
    src = np.asarray(src, dtype=np.float64)
    dst = np.asarray(dst, dtype=np.float64)
    if len(src) != len(dst) or len(src) == 0:
        raise ValueError("Point sets must be non-empty and of equal size")
    w = np.ones(len(src)) if weights is None else np.asarray(weights, dtype=np.float64)
    w = w / w.sum()
    cs = (src * w[:, None]).sum(0)
    cd = (dst * w[:, None]).sum(0)
    if len(src) < 3:
        return make_matrix(np.eye(3), cd - cs)
    H = ((src - cs) * w[:, None]).T @ (dst - cd)
    U, _, Vt = np.linalg.svd(H)
    d = np.sign(np.linalg.det(Vt.T @ U.T))
    D = np.diag([1.0, 1.0, d if d != 0 else 1.0])
    R = Vt.T @ D @ U.T
    return make_matrix(R, cd - R @ cs)


def _rotation_from_small_angles(a: float, b: float, c: float) -> np.ndarray:
    ca, sa = np.cos(a), np.sin(a)
    cb, sb = np.cos(b), np.sin(b)
    cc, sc = np.cos(c), np.sin(c)
    Rx = np.array([[1, 0, 0], [0, ca, -sa], [0, sa, ca]])
    Ry = np.array([[cb, 0, sb], [0, 1, 0], [-sb, 0, cb]])
    Rz = np.array([[cc, -sc, 0], [sc, cc, 0], [0, 0, 1]])
    return Rz @ Ry @ Rx


class FixedTarget:
    """Pre-processed fixed (reference) surface for repeated ICP queries."""

    def __init__(self, points: np.ndarray, normals: np.ndarray, max_points: int = 300_000, seed: int = 0):
        if len(points) > max_points:
            idx = np.random.default_rng(seed).choice(len(points), max_points, replace=False)
            points, normals = points[idx], normals[idx]
        self.points = np.ascontiguousarray(points, dtype=np.float64)
        self.normals = np.ascontiguousarray(normals, dtype=np.float64)
        self.tree = cKDTree(self.points)
        lo, hi = self.points.min(0), self.points.max(0)
        self.diagonal = float(np.linalg.norm(hi - lo)) or 1.0


def sample_points(points: np.ndarray, normals: np.ndarray, count: int, seed: int = 1):
    if len(points) <= count:
        return points, normals
    idx = np.random.default_rng(seed).choice(len(points), count, replace=False)
    return points[idx], normals[idx]


def icp(
    src: np.ndarray,
    src_normals: np.ndarray | None,
    target: FixedTarget,
    init: np.ndarray | None = None,
    iterations: int = 50,
    trim: float = 0.9,
    max_distance: float | None = None,
    point_to_plane: bool = True,
    tolerance: float = 1e-7,
) -> AlignResult:
    """Trimmed point-to-plane ICP of ``src`` onto ``target``."""
    T = np.eye(4) if init is None else np.array(init, dtype=np.float64)
    diag = target.diagonal
    if max_distance is None:
        max_distance = 0.1 * diag
    prev_err = np.inf
    rms, frac = np.inf, 0.0
    it = 0
    for it in range(1, iterations + 1):
        p = transform_points(T, src)
        d, idx = target.tree.query(p, k=1, workers=-1)
        q = target.points[idx]
        nq = target.normals[idx]
        keep = d <= max_distance
        if src_normals is not None:
            ns = src_normals @ T[:3, :3].T
            keep &= np.einsum("ij,ij->i", ns, nq) > 0.3  # same side of a thin shell
        if keep.sum() < 6:
            break
        cutoff = np.quantile(d[keep], trim)
        keep &= d <= cutoff
        if keep.sum() < 6:
            break
        p_k, q_k, n_k = p[keep], q[keep], nq[keep]
        if point_to_plane:
            A = np.hstack([np.cross(p_k, n_k), n_k])
            b = -np.einsum("ij,ij->i", p_k - q_k, n_k)
            AtA = A.T @ A + np.eye(6) * 1e-9 * len(A)
            try:
                x = np.linalg.solve(AtA, A.T @ b)
            except np.linalg.LinAlgError:
                break
            dT = make_matrix(_rotation_from_small_angles(*x[:3]), x[3:])
        else:
            dT = kabsch(p_k, q_k)
        T = dT @ T
        err = float(np.sqrt(np.mean(d[keep] ** 2)))
        if abs(prev_err - err) < tolerance * diag:
            break
        prev_err = err
        # shrink the inlier distance as we converge
        max_distance = max(min(max_distance, 6.0 * err + 1e-3 * diag), 0.005 * diag)

    # final quality estimate
    p = transform_points(T, src)
    d, _ = target.tree.query(p, k=1, workers=-1)
    inlier = d <= 0.01 * diag
    frac = float(inlier.mean()) if len(d) else 0.0
    rms = float(np.sqrt(np.mean(d[inlier] ** 2))) if inlier.any() else float(np.sqrt(np.mean(d ** 2)))
    return AlignResult(T, rms, frac, it)


def _proper_frame(points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    c = points.mean(0)
    cov = np.cov((points - c).T)
    _, vecs = np.linalg.eigh(cov)
    F = vecs[:, ::-1]
    if np.linalg.det(F) < 0:
        F[:, 2] *= -1
    return c, F


def _cube_rotations() -> list[np.ndarray]:
    rots = []
    for perm in itertools.permutations(range(3)):
        for signs in itertools.product((1, -1), repeat=3):
            R = np.zeros((3, 3))
            for i, j in enumerate(perm):
                R[i, j] = signs[i]
            if np.linalg.det(R) > 0:
                rots.append(R)
    return rots


def auto_align(
    src: np.ndarray,
    src_normals: np.ndarray,
    target: FixedTarget,
    coarse_samples: int = 1000,
    fine_samples: int = 6000,
    fine_iterations: int = 80,
) -> AlignResult:
    """Global alignment without user points.

    Tries the current pose, a centroid match and 24 orientations of the
    principal axes, refines each with a short ICP and keeps the best.
    """
    cs, Fs = _proper_frame(src)
    cd, Fd = _proper_frame(target.points)
    candidates = [np.eye(4), make_matrix(np.eye(3), cd - cs)]
    for C in _cube_rotations():
        R = Fd @ C @ Fs.T
        candidates.append(make_matrix(R, cd - R @ cs))

    s_pts, s_nrm = sample_points(src, src_normals, coarse_samples, seed=3)
    best = None
    for T0 in candidates:
        res = icp(s_pts, s_nrm, target, T0, iterations=25, trim=0.8, max_distance=0.3 * target.diagonal)
        key = (round(res.inlier_fraction, 2), -res.rms)
        if best is None or key > best[0]:
            best = (key, res)
    f_pts, f_nrm = sample_points(src, src_normals, fine_samples, seed=4)
    return icp(f_pts, f_nrm, target, best[1].matrix, iterations=fine_iterations, trim=0.9)


def best_fit(src, src_normals, target: FixedTarget, init=None, iterations=80, samples=8000) -> AlignResult:
    pts, nrm = sample_points(src, src_normals, samples, seed=5)
    res = icp(pts, nrm, target, init, iterations=iterations, trim=0.9, max_distance=0.05 * target.diagonal)
    return res
