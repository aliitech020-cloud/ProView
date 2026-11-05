"""Floating models panel: one row per model with visibility, color and its own opacity slider."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap, QRadialGradient
from PySide6.QtWidgets import (
    QAbstractItemView,
    QColorDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .i18n import tr
from .icons import icon
from .model import MATERIALS

ROW_HEIGHT = 58


def _material_icon(color, specular, size=18):
    """A small shaded ball showing the material colour and how glossy it is."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    base = QColor.fromRgbF(*color)
    g = QRadialGradient(size * 0.35, size * 0.32, size * 0.75)
    hi = QColor(255, 255, 255) if specular > 0.4 else base.lighter(118)
    g.setColorAt(0.0, hi)
    g.setColorAt(0.25 if specular > 0.4 else 0.5, base)
    g.setColorAt(1.0, base.darker(170))
    p.setBrush(g)
    p.setPen(QColor(20, 22, 26))
    p.drawEllipse(1, 1, size - 2, size - 2)
    p.end()
    return QIcon(pm)


def _rgb(color, factor=1.0):
    return tuple(int(max(0, min(255, round(c * 255 * factor)))) for c in color)


class ModelRow(QWidget):
    def __init__(self, panel, model):
        super().__init__()
        self.panel = panel
        self.model = model
        self.setAttribute(Qt.WA_TranslucentBackground)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 4, 8, 4)
        lay.setSpacing(2)

        top = QHBoxLayout()
        top.setSpacing(4)
        self.eye = QToolButton()
        self.eye.setCheckable(True)
        self.eye.setChecked(model.visible)
        self.eye.setIconSize(QSize(18, 18))
        self.eye.setAutoRaise(True)
        self.eye.setToolTip(tr("toggle_visible"))
        self.eye.toggled.connect(lambda on: self._visible(on))
        top.addWidget(self.eye)

        self.swatch = QToolButton()
        self.swatch.setFixedSize(18, 18)
        self.swatch.setToolTip(tr("material"))
        self.swatch.clicked.connect(lambda _=False: self._pick_color())
        top.addWidget(self.swatch)

        self.name = QLabel()
        self.name.setToolTip(model.name)
        top.addWidget(self.name, 1)
        self.mat_lbl = QLabel()
        self.mat_lbl.setStyleSheet("color:#8a909a; font-size:10px;")
        top.addWidget(self.mat_lbl)

        self.colors_btn = QToolButton()
        self.colors_btn.setIcon(icon("scan_colors"))
        self.colors_btn.setIconSize(QSize(16, 16))
        self.colors_btn.setCheckable(True)
        self.colors_btn.setAutoRaise(True)
        self.colors_btn.setToolTip(tr("scan_colors_row"))
        self.colors_btn.toggled.connect(lambda on: self._colors(on))
        top.addWidget(self.colors_btn)
        lay.addLayout(top)

        bottom = QHBoxLayout()
        bottom.setContentsMargins(26, 0, 0, 0)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(5, 100)
        self.slider.setValue(int(round(model.opacity * 100)))
        self.slider.setToolTip(tr("opacity"))
        self.slider.valueChanged.connect(lambda v: self._opacity(v))
        bottom.addWidget(self.slider, 1)
        self.pct = QLabel()
        self.pct.setFixedWidth(36)
        self.pct.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.pct.setStyleSheet("color:#aab0bb; font-size:11px;")
        bottom.addWidget(self.pct)
        lay.addLayout(bottom)
        self.refresh()

    def refresh(self):
        m = self.model
        self.eye.blockSignals(True)
        self.eye.setChecked(m.visible)
        self.eye.blockSignals(False)
        self.eye.setIcon(icon("eye" if m.visible else "eye_off"))
        self.colors_btn.setVisible(m.has_colors)
        self.colors_btn.blockSignals(True)
        self.colors_btn.setChecked(m.show_colors)
        self.colors_btn.blockSignals(False)
        r, g, b = _rgb(m.color)
        self.swatch.setStyleSheet("QToolButton{border:none; background:transparent;}")
        self.swatch.setIcon(_material_icon(m.color, m.finish[2]))
        self.swatch.setIconSize(QSize(18, 18))
        self.swatch.setToolTip(f"{tr('material')}: {m.material}")
        fm = self.name.fontMetrics()
        self.name.setText(fm.elidedText(m.name, Qt.ElideMiddle, 120))
        self.mat_lbl.setText(self.mat_lbl.fontMetrics().elidedText(m.material, Qt.ElideRight, 92))
        self.name.setToolTip(f"{m.name}\n{tr('material')}: {m.material}")
        self.name.setStyleSheet("color:#e8eaee;" if m.visible else "color:#7d838e;")
        hr, hg, hb = _rgb(m.color, 1.08)
        dr, dg, db = _rgb(m.color, 0.55)
        self.slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{ height:6px; background:#23262c; border-radius:3px; }}
            QSlider::sub-page:horizontal {{ background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 rgb({dr},{dg},{db}), stop:1 rgb({r},{g},{b})); border-radius:3px; }}
            QSlider::handle:horizontal {{ background:rgb({hr},{hg},{hb}); border:2px solid #15171b;
                width:14px; height:14px; margin:-5px 0; border-radius:8px; }}
        """)
        self.pct.setText(f"{self.slider.value()}%")

    def _visible(self, on):
        self.model.set_visible(on)
        self.refresh()
        self.panel.changed()

    def _opacity(self, v):
        self.model.set_opacity(v / 100.0)
        self.pct.setText(f"{v}%")
        self.panel.changed(render_only=True)

    def _colors(self, on):
        self.model.set_show_colors(on)
        self.panel.changed()

    def _pick_color(self):
        """Material menu: stone colours, zirconia glossy/matte, metals ... or a custom colour."""
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background:#23262c; color:#e6e8ec; border:1px solid #3a3f48; }"
                           "QMenu::item { padding:5px 22px 5px 8px; }"
                           "QMenu::item:selected { background:#2b4a70; }"
                           "QMenu::separator { height:1px; background:#3a3f48; margin:4px 6px; }")
        group = None
        for name, (color, _finish) in MATERIALS.items():
            g = name.split(" - ")[0] if " - " in name else name
            if group is not None and g != group and (" - " in name or " - " in prev):
                menu.addSeparator()
            group, prev = g, name
            act = menu.addAction(_material_icon(color, _finish[2]), name)
            act.setCheckable(True)
            act.setChecked(self.model.material == name)
            if self.model.material == name:
                f = act.font()
                f.setBold(True)
                act.setFont(f)
            act.triggered.connect(lambda _=False, n=name: self._set_material(n))
        menu.addSeparator()
        custom = menu.addAction(tr("custom_color"))
        custom.triggered.connect(lambda _=False: self._custom_color())
        menu.exec(self.swatch.mapToGlobal(self.swatch.rect().bottomLeft()))

    def _set_material(self, name):
        self.model.set_material(name)
        self.refresh()
        self.panel.changed()

    def _custom_color(self):
        c = QColorDialog.getColor(QColor.fromRgbF(*self.model.color), self.panel.window_)
        if c.isValid():
            self.model.set_color((c.redF(), c.greenF(), c.blueF()))
            self.refresh()
            self.panel.changed()


class ModelsPanel(QFrame):
    """Always-floating panel that follows the 3D view (top-left corner by default)."""

    def __init__(self, window, viewer, on_change, on_merge, on_remove, on_select):
        import os

        flags = Qt.Widget if os.environ.get("PROVIEW_PANEL_CHILD") else Qt.Tool | Qt.FramelessWindowHint
        super().__init__(window, flags)
        self.window_ = window
        self.viewer = viewer
        self.on_change = on_change
        self.offset = QPoint(16, 16)
        self._drag = None
        self.setObjectName("modelsPanel")
        self.setStyleSheet("""
            #modelsPanel { background:#1d2025; border:1px solid #3a3f48; border-radius:10px; }
            #panelHeader { color:#e8eaee; font-weight:bold; font-size:13px; }
            QListWidget { background:transparent; border:none; outline:none; }
            QListWidget::item { border-radius:6px; margin:1px 0; }
            QListWidget::item:selected { background:#2b4a70; }
            QListWidget::item:hover:!selected { background:#272b32; }
            QPushButton { background:#2b2e35; border:1px solid #3a3f48; border-radius:6px; padding:5px 8px;
                          color:#e6e8ec; }
            QPushButton:hover { border-color:#4aa3ff; background:#323743; }
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 10)
        lay.setSpacing(6)
        self.header = QLabel(tr("models"))
        self.header.setObjectName("panelHeader")
        self.header.setCursor(Qt.SizeAllCursor)
        self.header.setToolTip(tr("drag_panel"))
        lay.addWidget(self.header)

        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setToolTip(tr("models_tip"))
        # Connect through plain lambdas: connecting a signal straight to a bound method of the
        # (still constructing) main window crashes PySide6 on Windows.
        self.list.currentRowChanged.connect(lambda row: on_select(row))
        lay.addWidget(self.list)
        self.empty = QLabel(tr("drop_hint"))
        self.empty.setWordWrap(True)
        self.empty.setStyleSheet("color:#8a909a; font-size:11px;")
        lay.addWidget(self.empty)

        row = QHBoxLayout()
        b = QPushButton(icon("merge"), tr("merge"))
        b.setToolTip(tr("merge_tip"))
        b.clicked.connect(lambda _=False: on_merge())
        row.addWidget(b)
        b = QPushButton(icon("remove"), tr("remove_model"))
        b.clicked.connect(lambda _=False: on_remove())
        row.addWidget(b)
        lay.addLayout(row)
        self.info = QLabel(tr("no_model"))
        self.info.setWordWrap(True)
        self.info.setStyleSheet("color:#aab0bb; font-size:11px;")
        lay.addWidget(self.info)
        self.setFixedWidth(300)
        self._resize_list()

    # ------------------------------------------------------------- rows
    def add_model(self, model):
        item = QListWidgetItem()
        item.setSizeHint(QSize(0, ROW_HEIGHT))
        self.list.addItem(item)
        self.list.setItemWidget(item, ModelRow(self, model))
        self.list.setCurrentRow(self.list.count() - 1)
        self._resize_list()

    def remove_row(self, row):
        self.list.takeItem(row)
        self._resize_list()

    def row_widget(self, row) -> ModelRow | None:
        item = self.list.item(row)
        return self.list.itemWidget(item) if item else None

    def refresh_rows(self):
        for i in range(self.list.count()):
            w = self.row_widget(i)
            if w:
                w.refresh()

    def selected_rows(self):
        return sorted({self.list.row(i) for i in self.list.selectedItems()})

    def changed(self, render_only=False):
        self.viewer.render()
        if not render_only:
            self.on_change()

    def _resize_list(self):
        n = self.list.count()
        self.list.setVisible(n > 0)
        self.empty.setVisible(n == 0)
        self.list.setFixedHeight(min(max(n, 1), 6) * (ROW_HEIGHT + 2) + 4)
        self.header.setText(f"{tr('models')}  ({n})" if n else tr("models"))
        self.adjustSize()
        self.follow()

    # ------------------------------------------------------- positioning
    def follow(self):
        """Keep the panel at its offset from the 3D view's top-left corner."""
        if not self.viewer.isVisible():
            return
        origin = self.viewer.mapToGlobal(QPoint(0, 0))
        vw, vh = self.viewer.width(), self.viewer.height()
        x = min(max(self.offset.x(), 0), max(vw - self.width(), 0))
        y = min(max(self.offset.y(), 0), max(vh - self.height(), 0))
        self.move(origin + QPoint(x, y))

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton and self.header.geometry().contains(ev.position().toPoint()):
            self._drag = ev.globalPosition().toPoint() - self.pos()
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if self._drag is not None:
            pos = ev.globalPosition().toPoint() - self._drag
            self.offset = pos - self.viewer.mapToGlobal(QPoint(0, 0))
            self.follow()
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        self._drag = None
        super().mouseReleaseEvent(ev)
