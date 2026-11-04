import os
import tempfile

import numpy as np

from proview.alignment import FixedTarget, auto_align, best_fit, kabsch, make_matrix
from proview.mesh import Mesh, load_stl, save_stl, transform_points
from proview.selection import points_in_polygon, segment_distance


def bumpy_mesh(nu=60, nv=40):
    """An asymmetric closed-ish blob (no rotational symmetry)."""
    u = np.linspace(0, 2 * np.pi, nu, endpoint=False)
    v = np.linspace(0.05, np.pi - 0.05, nv)
    U, V = np.meshgrid(u, v)
    r = 10 + 2.0 * np.sin(3 * U) * np.sin(V) + 1.5 * np.cos(2 * V) + 0.8 * np.cos(U)
    x = r * np.cos(U) * np.sin(V) * 1.4
    y = r * np.sin(U) * np.sin(V)
    z = r * np.cos(V) * 0.7
    verts = np.stack([x, y, z], -1).reshape(-1, 3)
    faces = []
    for i in range(nv - 1):
        for j in range(nu):
            a = i * nu + j
            b = i * nu + (j + 1) % nu
            c = (i + 1) * nu + j
            d = (i + 1) * nu + (j + 1) % nu
            faces += [(a, c, b), (b, c, d)]
    return Mesh(verts, np.array(faces))


def random_rigid(seed, angle=0.6, shift=5.0):
    rng = np.random.default_rng(seed)
    axis = rng.normal(size=3)
    axis /= np.linalg.norm(axis)
    K = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    R = np.eye(3) + np.sin(angle) * K + (1 - np.cos(angle)) * K @ K
    return make_matrix(R, rng.normal(size=3) * shift)


def test_stl_roundtrip():
    m = bumpy_mesh()
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "نموذج.stl")  # non-ASCII path
        save_stl(p, m)
        m2 = load_stl(p)
    assert m2.n_faces == m.n_faces
    assert m2.n_vertices == m.n_vertices
    assert np.allclose(np.sort(m2.vertices, axis=0), np.sort(m.vertices.astype(np.float32), axis=0), atol=1e-5)


def test_ascii_stl():
    txt = """solid t
facet normal 0 0 1
 outer loop
  vertex 0 0 0
  vertex 1 0 0
  vertex 0 1 0
 endloop
endfacet
facet normal 0 0 1
 outer loop
  vertex 1 0 0
  vertex 1 1 0
  vertex 0 1 0
 endloop
endfacet
endsolid t
"""
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "a.stl")
        with open(p, "w") as fh:
            fh.write(txt)
        m = load_stl(p)
    assert m.n_faces == 2 and m.n_vertices == 4


def test_remove_faces_and_components():
    m = bumpy_mesh()
    mask = np.zeros(m.n_faces, bool)
    mask[:100] = True
    m2 = m.remove_faces(mask)
    assert m2.n_faces == m.n_faces - 100
    assert m2.faces.max() < m2.n_vertices
    # two separate copies -> two components
    from proview.mesh import merge_meshes

    shifted = Mesh(m.vertices + 100, m.faces)
    count, labels = merge_meshes([m, shifted]).connected_components()
    assert count == 2


def test_kabsch():
    rng = np.random.default_rng(0)
    P = rng.normal(size=(10, 3))
    T = random_rigid(1)
    Q = transform_points(T, P)
    assert np.allclose(kabsch(P, Q), T, atol=1e-9)


def test_best_fit_and_auto_align():
    m = bumpy_mesh()
    target = FixedTarget(m.vertices, m.vertex_normals())
    # small misalignment: best fit
    T = random_rigid(2, angle=0.15, shift=1.0)
    moved = transform_points(T, m.vertices)
    moved_n = m.vertex_normals(moved)
    res = best_fit(moved, moved_n, target)
    assert np.allclose(transform_points(res.matrix, moved), m.vertices, atol=1e-3)
    # large misalignment: auto align
    T = random_rigid(3, angle=2.5, shift=20.0)
    moved = transform_points(T, m.vertices)
    moved_n = m.vertex_normals(moved)
    res = auto_align(moved, moved_n, target)
    assert res.inlier_fraction > 0.99
    assert np.allclose(transform_points(res.matrix, moved), m.vertices, atol=1e-2)


def test_selection_helpers():
    poly = np.array([[0, 0], [10, 0], [10, 10], [0, 10]], float)
    pts = np.array([[5, 5], [11, 5], [-1, -1], [9.9, 0.1]])
    assert points_in_polygon(pts, poly).tolist() == [True, False, False, True]
    d = segment_distance(np.array([[0, 1], [5, 3], [12, 0]], float), np.array([0, 0.0]), np.array([10, 0.0]))
    assert np.allclose(d, [1, 3, 2])


def test_ply_roundtrip_and_formats():
    from proview.mesh import load_mesh, save_mesh

    m = bumpy_mesh()
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "a.ply")
        save_mesh(p, m)
        m2 = load_mesh(p)
        assert m2.n_faces == m.n_faces and np.allclose(m2.vertices, m.vertices, atol=1e-4)
        # ascii with a quad, extra vertex props and a big-endian binary with colors
        with open(os.path.join(d, "q.ply"), "w") as fh:
            fh.write("ply\nformat ascii 1.0\nelement vertex 4\nproperty float x\nproperty float y\n"
                     "property float z\nproperty uchar red\nelement face 1\n"
                     "property list uchar int vertex_indices\nend_header\n"
                     "0 0 0 255\n1 0 0 255\n1 1 0 255\n0 1 0 255\n4 0 1 2 3\n")
        q = load_mesh(os.path.join(d, "q.ply"))
        assert q.n_faces == 2 and q.n_vertices == 4
        vdt = np.dtype([("x", ">f4"), ("y", ">f4"), ("z", ">f4"), ("red", "u1"), ("green", "u1"), ("blue", "u1")])
        v = np.zeros(m.n_vertices, vdt)
        v["x"], v["y"], v["z"] = m.vertices.T
        fdt = np.dtype([("n", "u1"), ("i", ">i4", (3,))])
        f = np.zeros(m.n_faces, fdt)
        f["n"], f["i"] = 3, m.faces
        with open(os.path.join(d, "b.ply"), "wb") as fh:
            fh.write((f"ply\nformat binary_big_endian 1.0\nelement vertex {m.n_vertices}\nproperty float x\n"
                      "property float y\nproperty float z\nproperty uchar red\nproperty uchar green\n"
                      f"property uchar blue\nelement face {m.n_faces}\nproperty list uchar int vertex_indices\n"
                      "end_header\n").encode())
            fh.write(v.tobytes() + f.tobytes())
        b = load_mesh(os.path.join(d, "b.ply"))
        assert b.n_faces == m.n_faces and np.allclose(b.vertices, m.vertices, atol=1e-4)
