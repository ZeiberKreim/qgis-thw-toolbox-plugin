from qgis.core import QgsField
from qgis.PyQt.QtCore import QVariant

# Qt6 compatibility: QVariant.Bool was removed in Qt6/PyQt6.
# Booleans are stored as integers in most backends, so Int is a safe fallback.
QVARIANT_BOOL = getattr(QVariant, "Bool", QVariant.Int)


# Single source of truth for the THW Toolbox feature schema.
# All layer creation, field migration, and runtime field checks derive
# from this list. Order matters for layer creation; do not reorder
# without handling existing GeoPackage migration.
LAYER_FIELDS: list[tuple[str, object]] = [
    ("name", QVariant.String),
    ("svg_path", QVariant.String),
    ("svg_content", QVariant.String),
    ("size", QVariant.Double),
    ("scale_with_map", QVARIANT_BOOL),
    ("unique_id", QVariant.String),
    ("label", QVariant.String),
    ("show_label", QVARIANT_BOOL),
    ("white_background", QVARIANT_BOOL),
    ("rotation", QVariant.Double),
    ("origin_x", QVariant.Int),
    ("origin_y", QVariant.Int),
]


def build_qgs_fields() -> list[QgsField]:
    """Fresh QgsField objects for layer creation / migration."""
    return [QgsField(name, vtype) for name, vtype in LAYER_FIELDS]


def field_types_dict() -> dict[str, object]:
    """{field_name: QVariant.Type} for runtime field-presence checks."""
    return dict(LAYER_FIELDS)
