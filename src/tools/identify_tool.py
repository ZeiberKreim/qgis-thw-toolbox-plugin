from qgis.gui import QgsMapToolIdentify
from qgis.PyQt.QtCore import Qt

from ..logging_utils import get_logger
from ..ui.feature_dock import FeatureDock
from ._feature_search import find_nearest_feature

logger = get_logger(__name__)


class IdentifyTool(QgsMapToolIdentify):
    """Map tool that opens a feature's detail panel on left-click.

    Owns the FeatureDock (right-side panel) — created here so the dock's
    lifecycle is tied to the tool's lifecycle. `layer_manager` is the
    THWToolboxPlugin instance (legacy name); we use it for `.iface`,
    `.layer`, `.move_tool`, and `._show_error_alert`.
    """

    def __init__(self, canvas, layer_manager):
        super().__init__(canvas)
        self.canvas = canvas
        self.layer_manager = layer_manager
        self.layer = layer_manager.layer
        self.setCursor(Qt.CursorShape.ArrowCursor)

        self.feature_dock = FeatureDock(layer_manager.iface.mainWindow())
        layer_manager.iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.feature_dock)

    def canvasReleaseEvent(self, ev):
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        try:
            point = self.canvas.getCoordinateTransform().toMapCoordinates(ev.pos().x(), ev.pos().y())
            closest = find_nearest_feature(self.layer, self.canvas, point)

            if closest:
                self.feature_dock.show_feature(closest, self.layer_manager)
                if hasattr(self.layer_manager, "move_tool"):
                    self.layer_manager.move_tool.moving_feature = closest
            else:
                self.feature_dock.hide()

        except Exception as e:
            logger.exception("Fehler beim Identifizieren")
            self.layer_manager._show_error_alert(
                "Identifizierungsfehler", "Fehler beim Identifizieren von Features", f"Fehler: {e}"
            )
