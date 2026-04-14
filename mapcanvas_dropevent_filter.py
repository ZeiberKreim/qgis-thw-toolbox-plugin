from qgis.PyQt.QtCore import QEvent, QObject
from qgis.core import QgsPointXY


class CanvasDropFilter(QObject):
    def __init__(self, canvas, place_feature_callback):
        super().__init__()
        self.canvas = canvas
        self.place_feature = place_feature_callback

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.DragEnter:
            if event.mimeData().hasText():
                event.acceptProposedAction()
                return True

        if event.type() == QEvent.Type.Drop:
            print(f"DEBUG: Drop-Event empfangen: {event.mimeData().text()}")
            svg_path = event.mimeData().text()

            # Prüfe, ob eine Karte vorhanden ist, bevor Koordinaten transformiert werden
            try:
                crs = self.canvas.mapSettings().destinationCrs()
                if not crs.isValid():
                    from qgis.PyQt.QtWidgets import QMessageBox

                    msg_box = QMessageBox()
                    msg_box.setIcon(QMessageBox.Icon.Critical)
                    msg_box.setWindowTitle("Keine Karte vorhanden")
                    msg_box.setText("Bitte ziehen Sie zuerst eine Karte in das Projekt ein.")
                    msg_box.setDetailedText(
                        "Das Plugin benötigt eine Karte mit einem Koordinatensystem (CRS), um Symbole platzieren zu können.\n\n"
                        "So fügen Sie eine Karte hinzu:\n"
                        "1. Gehen Sie zu 'Browser' im QGIS-Fenster\n"
                        "2. Ziehen Sie eine Karte (z.B. OpenStreetMap) in das Projekt\n"
                        "3. Versuchen Sie erneut, ein Symbol zu platzieren"
                    )
                    msg_box.exec()
                    event.ignore()
                    return True
            except Exception as e:
                from qgis.PyQt.QtWidgets import QMessageBox

                msg_box = QMessageBox()
                msg_box.setIcon(QMessageBox.Icon.Critical)
                msg_box.setWindowTitle("Fehler beim Zugriff auf die Karte")
                msg_box.setText("Es gab ein Problem beim Zugriff auf die Karte.")
                msg_box.setDetailedText(f"Fehler: {str(e)}")
                msg_box.exec()
                event.ignore()
                return True

            pt = self.canvas.getCoordinateTransform().toMapCoordinates(event.pos().x(), event.pos().y())
            print(f"DEBUG: Koordinaten: {pt}")
            print(f"DEBUG: Rufe place_feature auf: {self.place_feature}")
            self.place_feature(svg_path, QgsPointXY(pt))
            event.acceptProposedAction()
            return True

        return False
