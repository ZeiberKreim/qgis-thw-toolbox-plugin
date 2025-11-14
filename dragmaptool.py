from PyQt5.QtCore import Qt
from PyQt5.QtGui import QCursor
from qgis.core import QgsPointXY
from qgis.gui import QgsMapToolEmitPoint


class DragDropMapTool(QgsMapToolEmitPoint):
    def __init__(self, canvas, drop_callback):
        super().__init__(canvas)
        self.canvas = canvas
        self.drop_callback = drop_callback
        self.setCursor(QCursor(Qt.OpenHandCursor))

    def canvasReleaseEvent(self, event):
        point = self.toMapCoordinates(event.pos())
        if self.drop_callback:
            self.drop_callback(QgsPointXY(point))
