"""
FadeEdgeDialog: modal preview/tune UI for the Tools -> Add Faded Edge action.
Shows the source image next to a live-updated preview of fade_edges() /
fade_edges_brush() (shoggoth/util/), with sliders for their parameters and
a variant dropdown. Rendering runs on a background thread, debounced while
sliders are dragged, mirroring PreviewController's pattern.
"""
import inspect
import random
import threading
from pathlib import Path

from PIL.ImageQt import toqpixmap
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QSlider, QVBoxLayout, QWidget,
)

from shoggoth.files import get_last_path, set_last_path
from shoggoth.i18n import tr
from shoggoth.ui.preview_widget import ZoomableImageLabel
from shoggoth.util.fade_edges import fade_edges
from shoggoth.util.fade_edges_brush import fade_edges_brush

RENDER_DEBOUNCE_MS = 150

# (kwarg name, translation key, minimum, maximum, decimal places)
COMMON_PARAMS = [
    ("fade_percent", "PARAM_FADE_PERCENT", 1, 40, 1),
    ("ruggedness", "PARAM_RUGGEDNESS", 0, 1, 2),
    ("roughness_percent", "PARAM_ROUGHNESS_PERCENT", 5, 150, 0),
]
BRUSH_PARAMS = [
    ("bristle_strength", "PARAM_BRISTLE_STRENGTH", 0, 1.5, 2),
    ("bristle_length", "PARAM_BRISTLE_LENGTH", 0.5, 6, 2),
    ("bristle_density", "PARAM_BRISTLE_DENSITY", 4, 40, 0),
    ("grain_strength", "PARAM_GRAIN_STRENGTH", 0, 1, 2),
    ("grain_scale", "PARAM_GRAIN_SCALE", 1, 20, 0),
]

VARIANTS = [
    ("plain", "FADE_VARIANT_PLAIN", fade_edges, COMMON_PARAMS),
    ("brush", "FADE_VARIANT_BRUSH", fade_edges_brush, COMMON_PARAMS + BRUSH_PARAMS),
]


def _defaults_for(fn):
    return {
        name: param.default
        for name, param in inspect.signature(fn).parameters.items()
        if param.default is not inspect.Parameter.empty
    }


class _ParamSlider(QWidget):
    """A labeled slider bound to a float range, shown with its live value."""

    valueChanged = Signal()

    def __init__(self, label, minimum, maximum, default, decimals, parent=None):
        super().__init__(parent)
        self._decimals = decimals
        self._scale = 10 ** decimals

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        name_label = QLabel(label)
        name_label.setMinimumWidth(120)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(round(minimum * self._scale))
        self.slider.setMaximum(round(maximum * self._scale))
        self.slider.setValue(round(default * self._scale))
        self.value_label = QLabel()
        self.value_label.setMinimumWidth(45)
        self.value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        layout.addWidget(name_label)
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.value_label)

        self.slider.valueChanged.connect(self._on_changed)
        self._on_changed(self.slider.value())

    def _on_changed(self, raw):
        self.value_label.setText(f"{raw / self._scale:.{self._decimals}f}")
        self.valueChanged.emit()

    def value(self):
        return self.slider.value() / self._scale


class FadeEdgeDialog(QDialog):
    _render_result = Signal(object, object, int)  # image, error, version

    def __init__(self, source_path, image, parent=None):
        super().__init__(parent)
        self.source_path = Path(source_path)
        self.original_image = image
        self.result_image = None
        self._render_version = 0
        self._seed = random.randint(0, 2**31 - 1)
        self._sliders = {}
        self._has_result_image = False

        self.setWindowTitle(tr("DLG_FADE_EDGE_TITLE"))
        self.setWindowModality(Qt.ApplicationModal)
        self.resize(1100, 650)

        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.timeout.connect(self._start_render)
        self._render_result.connect(self._on_render_result)

        self._build_ui()
        self._rebuild_params()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)

        content = QHBoxLayout()
        root.addLayout(content, 1)

        self.original_view = ZoomableImageLabel()
        self.original_view.setMinimumSize(300, 400)
        self.original_view.setPixmap(toqpixmap(self.original_image))
        content.addWidget(self._preview_column(tr("LBL_ORIGINAL"), self.original_view), 1)

        content.addWidget(self._build_controls())

        self.result_view = ZoomableImageLabel()
        self.result_view.setMinimumSize(300, 400)
        content.addWidget(self._preview_column(tr("LBL_RESULT"), self.result_view), 1)

        bottom = QHBoxLayout()
        self.status_label = QLabel("")
        bottom.addWidget(self.status_label, 1)

        save_btn = QPushButton(tr("BTN_SAVE_AS"))
        save_btn.clicked.connect(self._save_result)
        bottom.addWidget(save_btn)

        close_btn = QPushButton(tr("BTN_CLOSE"))
        close_btn.clicked.connect(self.reject)
        bottom.addWidget(close_btn)

        root.addLayout(bottom)

    def _preview_column(self, title, view):
        column = QWidget()
        layout = QVBoxLayout(column)
        layout.setContentsMargins(0, 0, 0, 0)
        header = QLabel(title)
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)
        layout.addWidget(view, 1)
        return column

    def _build_controls(self):
        panel = QWidget()
        panel.setFixedWidth(260)
        controls = QVBoxLayout(panel)

        controls.addWidget(QLabel(tr("LBL_VARIANT")))
        self.variant_combo = QComboBox()
        for key, label_key, _fn, _params in VARIANTS:
            self.variant_combo.addItem(tr(label_key), key)
        self.variant_combo.currentIndexChanged.connect(self._rebuild_params)
        controls.addWidget(self.variant_combo)

        self.params_layout = QVBoxLayout()
        controls.addLayout(self.params_layout)

        reroll_btn = QPushButton(tr("BTN_REROLL_SEED"))
        reroll_btn.clicked.connect(self._reroll_seed)
        controls.addWidget(reroll_btn)

        controls.addStretch(1)
        return panel

    # ------------------------------------------------------------------
    # Parameter panel
    # ------------------------------------------------------------------

    def _current_variant(self):
        key = self.variant_combo.currentData()
        return next(v for v in VARIANTS if v[0] == key)

    def _rebuild_params(self, *_args):
        while self.params_layout.count():
            item = self.params_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self._sliders = {}

        _key, _label_key, fn, param_spec = self._current_variant()
        defaults = _defaults_for(fn)

        for name, label_key, minimum, maximum, decimals in param_spec:
            slider = _ParamSlider(tr(label_key), minimum, maximum, defaults.get(name, minimum), decimals)
            slider.valueChanged.connect(self._schedule_render)
            self.params_layout.addWidget(slider)
            self._sliders[name] = slider

        self._schedule_render()

    def _reroll_seed(self):
        self._seed = random.randint(0, 2**31 - 1)
        self._schedule_render()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _schedule_render(self):
        self._render_timer.start(RENDER_DEBOUNCE_MS)

    def _start_render(self):
        self._render_version += 1
        version = self._render_version

        _key, _label_key, fn, _params = self._current_variant()
        params = {name: slider.value() for name, slider in self._sliders.items()}
        params["seed"] = self._seed
        source = self.original_image

        def worker():
            try:
                result = fn(source.copy(), **params)
            except Exception as e:
                self._render_result.emit(None, str(e), version)
                return
            self._render_result.emit(result, None, version)

        threading.Thread(target=worker, daemon=True).start()

    def _on_render_result(self, image, error, version):
        if version != self._render_version:
            return
        if error:
            self.status_label.setText(tr("ERR_FADE_EDGE_TOOL").format(error=error))
            return

        self.result_image = image
        self.status_label.setText("")
        pixmap = toqpixmap(image)
        if self._has_result_image:
            self.result_view.update_pixmap(pixmap)
        else:
            self.result_view.setPixmap(pixmap)
            self._has_result_image = True

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def _save_result(self):
        if self.result_image is None:
            return

        default_target = get_last_path("fade_edge_target") / f"{self.source_path.stem}_faded.png"
        target_path, _ = QFileDialog.getSaveFileName(
            self, tr("BTN_SAVE_AS"), str(default_target), tr("FILTER_RASTER_IMAGES")
        )
        if not target_path:
            return
        target = Path(target_path)
        if not target.suffix:
            target = target.with_suffix(".png")
        set_last_path("fade_edge_target", target.parent)

        try:
            self.result_image.save(target)
        except Exception as e:
            QMessageBox.critical(self, tr("DLG_ERROR"), tr("ERR_FADE_EDGE_TOOL").format(error=e))
            return

        self.status_label.setText(tr("STATUS_FADED_EDGE_SAVED").format(path=str(target)))
