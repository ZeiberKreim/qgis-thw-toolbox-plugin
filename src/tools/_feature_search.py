from qgis.core import QgsFeature, QgsFeatureRequest, QgsGeometry, QgsPointXY, QgsVectorLayer

# Default tolerance fallback when a feature has no `size` attribute.
_FALLBACK_SIZE = 30.0
# Minimum tolerance in map units. Below this, near-pixel-perfect clicks
# would be required, which feels broken on dense layers.
_MIN_TOLERANCE = 10.0


def _tolerance_for(feature: QgsFeature, has_size_field: bool) -> float:
    size = feature["size"] if has_size_field else _FALLBACK_SIZE
    return max(size * 0.5, _MIN_TOLERANCE)


def find_nearest_feature(layer: QgsVectorLayer, canvas, point: QgsPointXY) -> QgsFeature | None:
    """Return the feature closest to `point` within size-derived tolerance.

    Used by IdentifyTool (click), MoveTool (hover), and MoveTool (press)
    so all three behave consistently. Tolerance scales with the feature's
    `size` attribute (half the symbol size, floored at 10 map units).
    """
    request = QgsFeatureRequest()
    request.setFilterRect(canvas.mapSettings().mapToLayerCoordinates(layer, canvas.extent()))

    has_size_field = "size" in [field.name() for field in layer.fields()]
    target_geom = QgsGeometry.fromPointXY(point)

    closest: QgsFeature | None = None
    min_distance = float("inf")

    for feature in layer.getFeatures(request):
        geom = feature.geometry()
        if not geom:
            continue
        distance = geom.distance(target_geom)
        tolerance = _tolerance_for(feature, has_size_field)
        if distance < min_distance and distance < tolerance:
            min_distance = distance
            closest = feature

    return closest
