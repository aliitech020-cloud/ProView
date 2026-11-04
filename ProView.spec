# PyInstaller spec: build with  `pyinstaller ProView.spec`
# Produces dist/ProView/ProView.exe (one-folder build, fast start-up).
block_cipher = None

excluded = [
    "tkinter", "matplotlib", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick", "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtPdf",
    "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtCharts", "PySide6.QtDataVisualization",
]

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=[],
    hiddenimports=[
        "vtkmodules.vtkRenderingOpenGL2",
        "vtkmodules.vtkInteractionStyle",
        "vtkmodules.vtkRenderingFreeType",
        "vtkmodules.vtkRenderingUI",
        "vtkmodules.util.numpy_support",
        "scipy.spatial._ckdtree",
        "scipy.sparse.csgraph._validation",
    ],
    excludes=excluded,
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ProView",
    console=False,
    icon=None,
)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, name="ProView")
