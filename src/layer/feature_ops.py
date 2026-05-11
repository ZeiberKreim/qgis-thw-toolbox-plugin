import os
import uuid
from collections.abc import Callable

from qgis.core import QgsFeature, QgsField, QgsGeometry, QgsPointXY, QgsVectorLayer

from .fields import field_types_dict

# Default size used when adaptive sizing has no zoom info
_BASE_SIZE = 30.0
# Bounds for the adaptive zoom-aware initial size
_ADAPTIVE_MIN = 50.0
_ADAPTIVE_MAX = 500.0


class FeatureOperations:
    """All single- and multi-attribute mutations on the toolbox layer.

    The layer is fetched lazily via `layer_provider` because the plugin
    can swap the layer at project-save time. After every successful
    write, one of the dirty callbacks fires so the renderer or labeling
    can refresh.

    Attribute writes go through `_update_attribute`, which encapsulates
    the QGIS startEditing → changeAttributeValue → commitChanges dance.
    """

    def __init__(
        self,
        layer_provider: Callable[[], QgsVectorLayer | None],
        settings,
        plugin_dir: str,
        canvas,
        error_alert: Callable[[str, str, str | None], None],
        on_renderer_dirty: Callable[[], None],
        on_labeling_dirty: Callable[[], None],
    ):
        self._layer_provider = layer_provider
        self._settings = settings
        self._plugin_dir = plugin_dir
        self._canvas = canvas
        self._error_alert = error_alert
        self._on_renderer_dirty = on_renderer_dirty
        self._on_labeling_dirty = on_labeling_dirty

    @property
    def layer(self) -> QgsVectorLayer | None:
        return self._layer_provider()

    # ------------------------------------------------------------------
    # Single-attribute setters
    # ------------------------------------------------------------------

    def resize(self, fid, size) -> None:
        self._update_attribute(fid, "size", size, dirty="renderer")

    def toggle_scale(self, fid, value) -> None:
        self._update_attribute(fid, "scale_with_map", value, dirty="renderer")

    def toggle_white_background(self, fid, value) -> None:
        self._update_attribute(fid, "white_background", value, dirty="renderer")

    def rotate(self, fid, degrees) -> None:
        self._update_attribute(fid, "rotation", degrees, dirty="renderer")

    def set_label(self, fid, text) -> None:
        self._update_attribute(fid, "label", text, dirty="labeling")

    def toggle_label(self, fid, value) -> None:
        self._update_attribute(fid, "show_label", value, dirty="labeling")

    def update_origin(self, fid, origin_x, origin_y) -> None:
        """Set both origin_x and origin_y in one edit transaction."""
        layer = self.layer
        if not layer:
            return
        idx_x = layer.fields().indexFromName("origin_x")
        idx_y = layer.fields().indexFromName("origin_y")
        if idx_x < 0 or idx_y < 0:
            return
        if not layer.isEditable():
            layer.startEditing()
        layer.changeAttributeValue(fid, idx_x, origin_x)
        layer.changeAttributeValue(fid, idx_y, origin_y)
        layer.commitChanges()
        layer.triggerRepaint()
        self._on_renderer_dirty()

    def _update_attribute(self, fid, field_name: str, value, dirty: str) -> None:
        """Generic single-attribute write with renderer or labeling refresh."""
        layer = self.layer
        if not layer:
            return
        idx = layer.fields().indexFromName(field_name)
        if idx < 0:
            return
        if not layer.isEditable():
            layer.startEditing()
        layer.changeAttributeValue(fid, idx, value)
        layer.commitChanges()
        layer.triggerRepaint()
        if dirty == "renderer":
            self._on_renderer_dirty()
        elif dirty == "labeling":
            self._on_labeling_dirty()

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(self, fid) -> bool:
        """Delete the feature from the layer. Returns True on success."""
        layer = self.layer
        if not layer:
            return False
        # Only the ogr (GeoPackage) path is supported — LayerManager always
        # creates GeoPackages, so the legacy memory-layer fallback was unreachable.
        if layer.providerType() != "ogr":
            return False
        layer.startEditing()
        layer.deleteFeature(fid)
        layer.commitChanges()
        self._on_renderer_dirty()
        return True

    # ------------------------------------------------------------------
    # Place
    # ------------------------------------------------------------------

    def place_feature(self, svg_path: str, point: QgsPointXY) -> QgsFeature | None:
        """Insert a new feature at `point` from an SVG file.

        Auto-migrates the layer schema if newer fields are missing,
        embeds the SVG content into `svg_content`, computes an adaptive
        initial size based on the current zoom, and returns the inserted
        feature (refreshed from the layer so it has the persisted fid).

        Returns None if the SVG is unreadable or the layer is not ready.
        Caller is responsible for any UI follow-up (selection, dock).
        """
        layer = self.layer
        if not layer:
            return None

        self._ensure_schema(layer)

        svg_content = self._read_svg(svg_path)
        if svg_content is None:
            return None

        relative_path = self._relative_to_plugin(svg_path)
        icon_size = self._initial_size(layer)
        default_label = os.path.splitext(os.path.basename(svg_path))[0].replace("_", " ")

        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromPointXY(point))
        f.setAttribute("name", os.path.basename(svg_path))
        f.setAttribute("svg_path", relative_path)
        f.setAttribute("svg_content", svg_content)
        f.setAttribute("size", icon_size)
        f.setAttribute("scale_with_map", self._settings.new_icon_scaling_with_map)
        f.setAttribute("unique_id", str(uuid.uuid4()))
        f.setAttribute("label", default_label)
        f.setAttribute("show_label", False)
        f.setAttribute("white_background", False)
        f.setAttribute("rotation", 0.0)
        origin_x, origin_y = 1, 1
        if os.path.basename(svg_path).startswith("Schadensstelle"):
            origin_y = 0
        f.setAttribute("origin_x", origin_x)
        f.setAttribute("origin_y", origin_y)

        layer.startEditing()
        added = layer.dataProvider().addFeature(f)
        layer.commitChanges()
        layer.updateExtents()

        self._on_renderer_dirty()

        if not added:
            return None

        # Look the feature back up — its persisted fid differs from the in-memory one
        return self._find_inserted_feature(layer, f, point)

    # ------------------------------------------------------------------
    # place_feature internals
    # ------------------------------------------------------------------

    def _ensure_schema(self, layer: QgsVectorLayer) -> None:
        """Add any newer fields that are missing on this layer.

        Surfaces a clear error if a field can't be added — silent failure
        here cascades into a confusing KeyError on `setAttribute` later.
        """
        existing = {field.name() for field in layer.fields()}
        missing = [(n, QgsField(n, t)) for n, t in field_types_dict().items() if n not in existing]
        if not missing:
            return

        if not layer.startEditing():
            self._error_alert(
                "Layer-Schema-Fehler",
                "Layer kann nicht in den Bearbeitungsmodus versetzt werden.",
                f"Fehlende Felder: {[n for n, _ in missing]}",
            )
            return

        failed = [n for n, field in missing if not layer.addAttribute(field)]
        if not layer.commitChanges():
            failed = [n for n, _ in missing]

        layer.updateFields()

        still_missing = [n for n, _ in missing if layer.fields().indexFromName(n) < 0]
        if still_missing:
            self._error_alert(
                "Layer-Schema-Fehler",
                "Konnte fehlende Felder nicht zum Layer hinzufügen.",
                f"Fehlende Felder: {still_missing}\n"
                f"addAttribute-Fehler: {failed}\n"
                "Vermutete Ursache: Qt6/QGIS-4 Inkompatibilität bei Feldtypen.",
            )

    def _read_svg(self, svg_path: str) -> str | None:
        """Read SVG file contents; surfaces errors via the alert callback."""
        try:
            if not os.path.exists(svg_path):
                self._error_alert(
                    "SVG-Datei nicht gefunden",
                    f"Die SVG-Datei konnte nicht gefunden werden: {svg_path}",
                    f"Pfad: {svg_path}",
                )
                return None
            with open(svg_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            self._error_alert("SVG-Lesefehler", "Konnte SVG-Datei nicht lesen", f"Pfad: {svg_path}\nFehler: {e}")
            return None

    def _relative_to_plugin(self, svg_path: str) -> str:
        if svg_path.startswith(self._plugin_dir):
            return os.path.relpath(svg_path, self._plugin_dir)
        return svg_path

    def _initial_size(self, layer: QgsVectorLayer) -> float:
        """Compute the initial symbol size: fixed from settings, or zoom-adaptive."""
        if self._settings.new_icon_fixed_size:
            return self._settings.new_icon_size

        # Zoom-adaptive: more zoom (smaller mu/px) → larger symbols
        map_units_per_pixel = self._canvas.mapUnitsPerPixel()
        size = _BASE_SIZE * (1.0 / max(map_units_per_pixel, 0.001))

        # Don't go smaller than the smallest existing symbol — keeps mixed maps consistent
        if layer.featureCount() > 0:
            min_existing = float("inf")
            for feature in layer.getFeatures():
                feat_size = feature.attribute("size")
                if feat_size and feat_size > 0:
                    min_existing = min(min_existing, feat_size)
            if min_existing != float("inf"):
                size = max(size, min_existing)

        return max(_ADAPTIVE_MIN, min(_ADAPTIVE_MAX, size))

    def _find_inserted_feature(self, layer: QgsVectorLayer, draft: QgsFeature, point: QgsPointXY) -> QgsFeature | None:
        """Look up the just-inserted feature by unique_id (or path+location fallback)."""
        target_geom = QgsGeometry.fromPointXY(point)
        for feature in layer.getFeatures():
            if feature.attribute("unique_id") == draft.attribute("unique_id"):
                return feature
            if (
                feature.attribute("svg_path") == draft.attribute("svg_path")
                and feature.geometry().distance(target_geom) < 0.1
            ):
                return feature
        return None
