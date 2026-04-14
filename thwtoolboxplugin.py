import os
import time
import uuid

from qgis.PyQt.QtCore import QEvent, QObject, QSize, Qt, QVariant
from qgis.PyQt.QtGui import QColor, QDrag, QIcon, QPixmap
from qgis.PyQt.QtWidgets import (
    QAction,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from qgis.core import (
    Qgis,
    QgsCategorizedSymbolRenderer,
    QgsFeature,
    QgsFeatureRequest,
    QgsField,
    QgsGeometry,
    QgsMapLayer,
    QgsMarkerSymbol,
    QgsPalLayerSettings,
    QgsPointXY,
    QgsProject,
    QgsProperty,
    QgsRendererCategory,
    QgsSimpleMarkerSymbolLayer,
    QgsSingleSymbolRenderer,
    QgsSvgMarkerSymbolLayer,
    QgsSymbolLayer,
    QgsTextBufferSettings,
    QgsTextFormat,
    QgsUnitTypes,
    QgsVectorFileWriter,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
)
from qgis.gui import QgsMapTool, QgsMapToolIdentify
from qgis.utils import iface

from .identifytool import FeatureDock
from .thwtoolboxplugin_dock import SvgDock
from .thwtoolboxsettings import THWToolboxSettings

# Qt6 compatibility: QVariant.Bool was removed in Qt6/PyQt6.
# Use QVariant.Int as fallback since booleans are stored as integers in most backends.
QVARIANT_BOOL = getattr(QVariant, "Bool", QVariant.Int)


class CanvasDropFilter(QObject):
    def __init__(self, canvas, place_cb):
        super().__init__(canvas)
        self.canvas = canvas
        self.place_cb = place_cb

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Type.DragEnter:
            if ev.mimeData().hasText():
                ev.acceptProposedAction()
                return True
        if ev.type() == QEvent.Type.Drop:
            svg = ev.mimeData().text()
            if hasattr(ev, "position"):
                pos = ev.position().toPoint()
            else:
                pos = ev.pos()
            pt = self.canvas.getCoordinateTransform().toMapCoordinates(pos.x(), pos.y())
            self.place_cb(svg, QgsPointXY(pt))
            ev.acceptProposedAction()
            return True
        return False


class IdentifyTool(QgsMapToolIdentify):
    def __init__(self, canvas, layer_manager):
        super().__init__(canvas)
        self.canvas = canvas
        self.layer_manager = layer_manager
        self.layer = layer_manager.layer
        self.setCursor(Qt.CursorShape.ArrowCursor)

        # Dock-Widget erstellen
        self.feature_dock = FeatureDock(layer_manager.iface.mainWindow())
        layer_manager.iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.feature_dock)

    def _calculate_tolerance(self, feature):
        """Berechnet die Toleranz für Feature-Erkennung basierend auf der Symbolgröße."""
        symbol_size = feature["size"] if "size" in [field.name() for field in self.layer.fields()] else 30.0
        return max(symbol_size * 0.5, 10.0)  # Mindestens 10 Map Units, sonst halbe Symbolgröße

    def canvasReleaseEvent(self, ev):
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        try:
            # Konvertiere Mausposition zu Kartenkoordinaten
            point = self.canvas.getCoordinateTransform().toMapCoordinates(ev.pos().x(), ev.pos().y())

            # Erstelle einen Feature-Request
            request = QgsFeatureRequest()
            request.setFilterRect(self.canvas.mapSettings().mapToLayerCoordinates(self.layer, self.canvas.extent()))

            # Suche nach Features in der Nähe des Klickpunkts
            closest_feature = None
            min_distance = float("inf")

            for feature in self.layer.getFeatures(request):
                if feature.geometry():
                    distance = feature.geometry().distance(QgsGeometry.fromPointXY(point))
                    tolerance = self._calculate_tolerance(feature)
                    if distance < min_distance and distance < tolerance:
                        min_distance = distance
                        closest_feature = feature

            if closest_feature:
                self.feature_dock.show_feature(closest_feature, self.layer_manager)
                # Aktualisiere auch den MoveTool, falls vorhanden
                if hasattr(self.layer_manager, "move_tool"):
                    self.layer_manager.move_tool.moving_feature = closest_feature
            else:
                self.feature_dock.hide()

        except Exception as e:
            error_msg = f"Fehler beim Identifizieren: {str(e)}"
            print(error_msg)
            self.layer_manager._show_error_alert(
                "Identifizierungsfehler", "Fehler beim Identifizieren von Features", f"Fehler: {str(e)}"
            )


class MoveTool(QgsMapTool):
    def __init__(self, canvas, layer_manager):
        super().__init__(canvas)
        self.canvas = canvas
        self.layer_manager = layer_manager
        self.layer = layer_manager.layer
        self.moving_feature = None
        self.is_move_mode = False
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.pan_start = None
        self.is_panning = False
        self.last_center = None
        self.last_pos = None
        self.update_timer = None
        self.last_update_time = 0
        self.update_interval = 100  # ms
        self.update_threshold = 0.1  # Map Units
        self.is_editing = False
        self.last_canvas_update = 0
        self.last_dock_update = 0

    def _calculate_tolerance(self, feature):
        """Berechnet die Toleranz für Feature-Erkennung basierend auf der Symbolgröße."""
        symbol_size = feature["size"] if "size" in [field.name() for field in self.layer.fields()] else 30.0
        return max(symbol_size * 0.5, 10.0)  # Mindestens 10 Map Units, sonst halbe Symbolgröße

    def set_move_mode(self, enabled):
        self.is_move_mode = enabled
        if enabled:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        self.moving_feature = None

    def canvasMoveEvent(self, event):
        # Prüfe, ob der Cursor über einem Feature ist (nur alle 100ms wenn nicht im Move-Modus)
        if not self.moving_feature:
            current_time = time.time() * 1000  # Konvertiere zu Millisekunden
            if current_time - self.last_update_time > 100:  # Nur alle 100ms Feature-Suche
                point = self.canvas.getCoordinateTransform().toMapCoordinates(event.pos().x(), event.pos().y())
                request = QgsFeatureRequest()
                request.setFilterRect(self.canvas.mapSettings().mapToLayerCoordinates(self.layer, self.canvas.extent()))

                closest_feature = None
                min_distance = float("inf")

                for feature in self.layer.getFeatures(request):
                    if feature.geometry():
                        distance = feature.geometry().distance(QgsGeometry.fromPointXY(point))
                        tolerance = self._calculate_tolerance(feature)
                        if distance < min_distance and distance < tolerance:
                            min_distance = distance
                            closest_feature = feature

                if closest_feature:
                    self.setCursor(Qt.CursorShape.PointingHandCursor)
                else:
                    self.setCursor(Qt.CursorShape.ArrowCursor)

                self.last_update_time = current_time
        else:
            # Wenn im Move-Modus, Cursor entsprechend setzen
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

        if self.moving_feature:
            # Aktualisiere die Position des Features mit verbessertem Throttling
            point = self.canvas.getCoordinateTransform().toMapCoordinates(event.pos().x(), event.pos().y())
            current_time = time.time() * 1000  # Konvertiere zu Millisekunden

            # Nur aktualisieren, wenn sich die Position signifikant geändert hat und genug Zeit vergangen ist
            should_update = False
            if self.last_pos is None:
                should_update = True
            elif point.distance(self.last_pos) > self.update_threshold:
                if current_time - self.last_update_time > self.update_interval:
                    should_update = True

            if should_update:
                # Layer nur einmal in den Edit-Modus versetzen
                if not self.is_editing:
                    self.layer.startEditing()
                    self.is_editing = True

                # Feature-Position aktualisieren
                self.layer.changeGeometry(self.moving_feature.id(), QgsGeometry.fromPointXY(point))
                self.last_pos = point
                self.last_update_time = current_time

                # Koordinaten im Dock nur alle 300ms aktualisieren
                if current_time - self.last_dock_update > 300:
                    if hasattr(self.layer_manager, "ident_tool") and hasattr(
                        self.layer_manager.ident_tool, "feature_dock"
                    ):
                        feature = self.layer.getFeature(self.moving_feature.id())
                        if feature.isValid():
                            self.layer_manager.ident_tool.feature_dock.show_feature(feature, self.layer_manager)
                        self.last_dock_update = current_time

                # Canvas nur alle 150ms aktualisieren
                if current_time - self.last_canvas_update > 150:
                    self.canvas.refresh()
                    self.last_canvas_update = current_time
        elif not self.is_panning and self.pan_start and self.last_center:
            # Normales Pan-Verhalten
            dx = event.pos().x() - self.pan_start.x()
            dy = event.pos().y() - self.pan_start.y()

            # Berechne neue Kartenmitte
            map_units_per_pixel = self.canvas.mapUnitsPerPixel()
            new_center_x = self.last_center.x() - (dx * map_units_per_pixel)
            new_center_y = self.last_center.y() + (dy * map_units_per_pixel)

            self.canvas.setCenter(QgsPointXY(new_center_x, new_center_y))
            self.canvas.refresh()

    def canvasPressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return

        # Konvertiere Mausposition zu Kartenkoordinaten
        point = self.canvas.getCoordinateTransform().toMapCoordinates(event.pos().x(), event.pos().y())
        self.last_pos = point

        # Suche nach dem nächsten Feature
        request = QgsFeatureRequest()
        request.setFilterRect(self.canvas.mapSettings().mapToLayerCoordinates(self.layer, self.canvas.extent()))

        closest_feature = None
        min_distance = float("inf")

        for feature in self.layer.getFeatures(request):
            if feature.geometry():
                distance = feature.geometry().distance(QgsGeometry.fromPointXY(point))
                tolerance = self._calculate_tolerance(feature)
                if distance < min_distance and distance < tolerance:
                    min_distance = distance
                    closest_feature = feature

        if closest_feature:
            self.moving_feature = closest_feature
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            # Zeige Feature-Details an
            if hasattr(self.layer_manager, "ident_tool") and hasattr(self.layer_manager.ident_tool, "feature_dock"):
                self.layer_manager.ident_tool.feature_dock.show_feature(closest_feature, self.layer_manager)
        else:
            # Kein Feature gefunden - deselektiere aktuelles Feature
            self.moving_feature = None
            self.set_move_mode(False)
            # Verstecke Feature-Dock und zeige Platzhalter
            if hasattr(self.layer_manager, "ident_tool") and hasattr(self.layer_manager.ident_tool, "feature_dock"):
                self.layer_manager.ident_tool.feature_dock.show_placeholder()
                self.layer_manager.ident_tool.feature_dock.hide()
            # Starte Panning
            self.pan_start = event.pos()
            self.is_panning = True
            self.last_center = self.canvas.center()

    def canvasReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.moving_feature:
                # Layer-Änderungen committen wenn im Edit-Modus
                if self.is_editing:
                    self.layer.commitChanges()
                    self.is_editing = False

                self.moving_feature = None
                self.last_pos = None
                self.setCursor(Qt.CursorShape.PointingHandCursor)
            elif self.is_panning:
                # Normales Pan-Verhalten
                self.is_panning = False
                self.pan_start = None
                self.last_center = None


class THWToolboxPlugin:

    def __init__(self, iface):
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.plugin_dir = os.path.dirname(__file__)
        self.layer = None
        self.current_svg = None
        self.drop_filter = None
        self.ident_tool = None
        self.move_tool = None
        self.action = None
        self.dock = None

        self.settings = THWToolboxSettings()

    def _check_map_available(self):
        """Prüft, ob eine Karte vorhanden ist (CRS gesetzt und Layer im Projekt)."""
        try:
            # Prüfe, ob ein gültiges CRS gesetzt ist
            crs = self.canvas.mapSettings().destinationCrs()
            if not crs.isValid():
                return False

            # Prüfe, ob es Layer im Projekt gibt (außer dem THW Toolbox Marker Layer)
            project_layers = QgsProject.instance().mapLayers().values()
            # Zähle Layer, die nicht unser eigener Marker-Layer sind
            other_layers = [lyr for lyr in project_layers if lyr.name() != "THW Toolbox Marker"]

            # Wenn keine anderen Layer vorhanden sind, ist wahrscheinlich keine Karte geladen
            if len(other_layers) == 0:
                return False

            return True
        except Exception as e:
            print(f"DEBUG: Fehler bei _check_map_available: {e}")
            return False

    def _show_error_alert(self, title, message, details=None):
        """Zeigt einen Fehler-Alert mit optionalen Details."""
        msg_box = QMessageBox(self.iface.mainWindow())
        msg_box.setIcon(QMessageBox.Icon.Critical)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)

        if details:
            msg_box.setDetailedText(details)

        msg_box.exec()

        # Zusätzlich auch in der Message Bar anzeigen
        try:  # QGIS4 Variant
            self.iface.messageBar().pushMessage(
                title,
                message,
                level=Qgis.MessageLevel.Critical,  # Critical level
            )
        except Exception:
            # QGIS3 Variant
            self.iface.messageBar().pushMessage(
                title,
                message,
                level=3,  # Critical level
            )

    def initGui(self):
        icon = QIcon(os.path.join(self.plugin_dir, "icons", "icon.svg"))
        self.action = QAction(icon, "THW Toolbox", self.iface.mainWindow())
        self.action.setCheckable(True)  # Macht das Symbol zu einem Toggle-Button
        self.action.triggered.connect(self.toggle_plugin)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("THW Toolbox", self.action)

        # Export-Aktion hinzufügen
        self.export_action = QAction("Portables Paket exportieren", self.iface.mainWindow())
        self.export_action.triggered.connect(self._export_portable_package)
        self.iface.addPluginToMenu("THW Toolbox", self.export_action)

        # Verbinde Projekt-Events für automatisches Speichern
        QgsProject.instance().writeProject.connect(self._on_project_save)

    def unload(self):
        # Plugin deaktivieren falls aktiv
        if self.action and self.action.isChecked():
            self.deactivate()

        if self.dock:
            self.iface.removeDockWidget(self.dock)
        if self.drop_filter:
            self.canvas.viewport().removeEventFilter(self.drop_filter)
        if self.ident_tool:
            self.canvas.unsetMapTool(self.ident_tool)
        if self.move_tool:
            self.canvas.unsetMapTool(self.move_tool)
        if self.action:
            self.iface.removeToolBarIcon(self.action)
            self.iface.removePluginMenu("THW Toolbox", self.action)
        if self.export_action:
            self.iface.removePluginMenu("THW Toolbox", self.export_action)

        # Trenne Projekt-Events
        QgsProject.instance().writeProject.disconnect(self._on_project_save)

        # Räume temporäre Dateien auf
        self._cleanup_temp_files()

    def activate(self):
        print("DEBUG: Plugin wird aktiviert")

        # Prüfe ZUERST, ob eine Karte vorhanden ist
        if not self._check_map_available():
            self._show_error_alert(
                "Keine Karte vorhanden",
                "Bitte ziehen Sie zuerst eine Karte in das Projekt ein.",
                "Das Plugin benötigt eine Karte mit einem Koordinatensystem (CRS), um funktionieren zu können.\n\n"
                "So fügen Sie eine Karte hinzu:\n"
                "1. Gehen Sie zu 'Browser' im QGIS-Fenster\n"
                "2. Ziehen Sie eine Karte (z.B. OpenStreetMap) in das Projekt\n"
                "3. Aktivieren Sie das Plugin erneut",
            )
            # Plugin nicht aktivieren - Checkbox zurücksetzen
            if self.action:
                self.action.setChecked(False)
            return

        # Bereinige alte temporäre Dateien beim Start
        self._cleanup_temp_files()

        self._init_layer()
        print(f"DEBUG: Layer initialisiert: {self.layer}")

        # Prüfe erneut, ob der Layer erfolgreich initialisiert wurde
        if not self.layer:
            # Layer konnte nicht initialisiert werden (z.B. wegen fehlender Karte)
            if self.action:
                self.action.setChecked(False)
            return

        self._init_dock()
        # Drag & Drop
        if not self.drop_filter:
            print("DEBUG: Erstelle CanvasDropFilter")
            df = CanvasDropFilter(self.canvas, self._place_feature)
            self.drop_filter = df
            self.canvas.viewport().installEventFilter(df)
            self.canvas.setAcceptDrops(True)
            print("DEBUG: CanvasDropFilter installiert")
        # IdentifyTool
        if not self.ident_tool:
            self.ident_tool = IdentifyTool(self.canvas, self)
        else:
            # IdentifyTool existiert bereits, zeige das Feature-Dock an
            if hasattr(self.ident_tool, "feature_dock"):
                self.ident_tool.feature_dock.show()
                self.ident_tool.feature_dock.raise_()
        # MoveTool
        if not self.move_tool:
            self.move_tool = MoveTool(self.canvas, self)
        self.canvas.setMapTool(self.move_tool)

        # Load the configuration settings
        self.settings.load_settings(QgsProject.instance())

        # Plugin-Symbol als aktiv markieren
        if self.action:
            self.action.setChecked(True)

    def toggle_plugin(self):
        """Schaltet das Plugin ein/aus basierend auf dem aktuellen Zustand des Symbols."""
        if self.action.isChecked():
            self.activate()
        else:
            self.deactivate()

    def deactivate(self):
        """Deaktiviert das Plugin und setzt das Symbol zurück."""
        print("DEBUG: Plugin wird deaktiviert")

        # Canvas-Tool zurücksetzen
        if self.canvas.mapTool() == self.move_tool:
            self.canvas.unsetMapTool(self.move_tool)

        # Dock verstecken
        if self.dock:
            self.dock.hide()

        # Feature-Dock verstecken
        if self.ident_tool and hasattr(self.ident_tool, "feature_dock"):
            self.ident_tool.feature_dock.hide()

        # Plugin-Symbol als inaktiv markieren
        if self.action:
            self.action.setChecked(False)

    def _init_layer(self):
        print("DEBUG: _init_layer wird aufgerufen")

        # Prüfe, ob eine Karte vorhanden ist (sollte bereits in activate() geprüft worden sein, aber zur Sicherheit)
        if not self._check_map_available():
            print("DEBUG: Keine Karte vorhanden, kann Layer nicht initialisieren")
            return

        proj = QgsProject.instance()
        pfile = proj.fileName()
        print(f"DEBUG: Projektdatei: {pfile}")

        # Prüfe, ob der Layer bereits im Projekt existiert
        existing_layers = QgsProject.instance().mapLayersByName("THW Toolbox Marker")
        print(f"DEBUG: Bestehende Layer gefunden: {len(existing_layers)}")
        if existing_layers:
            self.layer = existing_layers[0]
            print(f"DEBUG: Verwende bestehenden Layer: {self.layer}")
            return

        crs = self.canvas.mapSettings().destinationCrs().authid()

        # Erstelle immer eine eindeutige GeoPackage-Datei
        if pfile:
            # Wenn Projekt gespeichert ist, verwende den Projektpfad
            base = os.path.splitext(pfile)[0] + "_taktischezeichen"
            gpkg = base + ".gpkg"
        else:
            # Wenn kein Projekt gespeichert ist, erstelle eindeutige Datei im tmp-Ordner
            # Erstelle tmp-Ordner falls er nicht existiert
            tmp_dir = os.path.join(self.plugin_dir, "tmp")
            os.makedirs(tmp_dir, exist_ok=True)

            # Verwende Projekt-ID oder Zeitstempel für Eindeutigkeit
            proj_id = proj.title() or "unnamed"
            # Erstelle sicheren Dateinamen
            safe_name = "".join(c for c in proj_id if c.isalnum() or c in (" ", "-", "_")).rstrip()
            if not safe_name:
                safe_name = "project"
            # Füge Zeitstempel hinzu für Eindeutigkeit
            import time

            timestamp = int(time.time())
            safe_name = f"{safe_name}_{timestamp}"

            gpkg = os.path.join(tmp_dir, f"{safe_name}_taktischezeichen.gpkg")
            print(f"DEBUG: Erstelle eindeutige Datei für ungespeichertes Projekt: {gpkg}")

        lname = "taktische_zeichen"

        # Erstelle oder lade die GeoPackage
        if os.path.exists(gpkg):
            uri = f"{gpkg}|layername={lname}"
            lyr = QgsVectorLayer(uri, "THW Toolbox Marker", "ogr")

            # Prüfen ob die Felder existieren
            existing_fields = [field.name() for field in lyr.fields()]
            if "scale_with_map" not in existing_fields or "svg_content" not in existing_fields:
                # Layer mit neuen Feldern aktualisieren
                self._update_layer_fields(lyr, gpkg, lname)
                lyr = QgsVectorLayer(uri, "THW Toolbox Marker", "ogr")
        else:
            # Erstelle neue GeoPackage mit allen Feldern
            lyr = self._create_new_layer(gpkg, lname, crs)
            if lyr is None:
                # Fehler beim Erstellen des Layers
                return

        # Layer zuerst setzen, dann Renderer initialisieren
        self.layer = lyr
        print(f"DEBUG: Neuer Layer gesetzt: {self.layer}")
        QgsProject.instance().addMapLayer(lyr)
        print("DEBUG: Layer zum Projekt hinzugefügt")
        self._init_renderer(lyr)
        print("DEBUG: Renderer initialisiert")

    def _init_dock(self):
        if self.dock:
            # Dock existiert bereits, zeige es an
            self.dock.show()
            self.dock.raise_()
            return
        self.dock = QDockWidget("Taktische Zeichen", self.iface.mainWindow())
        self.dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea)
        self.svg_dock_widget = SvgDock(self.plugin_dir, self._on_svg_drag_start, self._open_config_dialog)
        self.dock.setWidget(self.svg_dock_widget)
        self.iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)

    def _on_svg_drag_start(self, svg_path):
        self.current_svg = svg_path

    def _create_new_layer(self, gpkg, lname, crs):
        """Erstellt einen neuen Layer mit allen erforderlichen Feldern."""
        try:
            # Stelle sicher, dass das Verzeichnis existiert
            os.makedirs(os.path.dirname(gpkg), exist_ok=True)

            # Erstelle temporären Memory-Layer
            mem = QgsVectorLayer(f"Point?crs={crs}", "temp", "memory")
            dp = mem.dataProvider()
            dp.addAttributes(
                [
                    QgsField("name", QVariant.String),
                    QgsField("svg_path", QVariant.String),
                    QgsField("svg_content", QVariant.String),
                    QgsField("size", QVariant.Double),
                    QgsField("scale_with_map", QVARIANT_BOOL),
                    QgsField("unique_id", QVariant.String),
                    QgsField("label", QVariant.String),
                    QgsField("show_label", QVARIANT_BOOL),
                    QgsField("white_background", QVARIANT_BOOL),
                    QgsField("rotation", QVariant.Double),
                ]
            )
            mem.updateFields()

            # Speichere als GeoPackage
            opts = QgsVectorFileWriter.SaveVectorOptions()
            opts.driverName = "GPKG"
            opts.layerName = lname
            result = QgsVectorFileWriter.writeAsVectorFormatV2(
                mem, gpkg, QgsProject.instance().transformContext(), opts
            )

            if result[0] != QgsVectorFileWriter.WriterError.NoError:
                self._show_error_alert(
                    "Layer-Erstellungsfehler",
                    f"Konnte neuen Layer nicht erstellen: {result[1]}",
                    f"Pfad: {gpkg}\nFehler: {result[1]}",
                )
                return None

            # Lade den gespeicherten Layer
            uri = f"{gpkg}|layername={lname}"
            return QgsVectorLayer(uri, "THW Toolbox Marker", "ogr")

        except Exception as e:
            error_msg = f"Fehler beim Erstellen des neuen Layers: {str(e)}"
            print(error_msg)
            self._show_error_alert(
                "Layer-Erstellungsfehler", "Konnte neuen Layer nicht erstellen", f"Pfad: {gpkg}\nFehler: {str(e)}"
            )
            return None

    def _update_layer_fields(self, old_layer, gpkg, lname):
        """Aktualisiert einen bestehenden Layer mit neuen Feldern."""
        try:
            # Prüfe, ob eine Karte vorhanden ist
            if not self._check_map_available():
                self._show_error_alert(
                    "Keine Karte vorhanden",
                    "Bitte ziehen Sie zuerst eine Karte in das Projekt ein.",
                    "Das Plugin benötigt eine Karte mit einem Koordinatensystem (CRS), um den Layer zu aktualisieren.\n\n"
                    "So fügen Sie eine Karte hinzu:\n"
                    "1. Gehen Sie zu 'Browser' im QGIS-Fenster\n"
                    "2. Ziehen Sie eine Karte (z.B. OpenStreetMap) in das Projekt\n"
                    "3. Versuchen Sie es erneut",
                )
                return

            # Stelle sicher, dass alle Edit-Sessions geschlossen sind
            if old_layer.isEditable():
                try:
                    old_layer.commitChanges()
                except:
                    try:
                        old_layer.rollBack()
                    except:
                        pass

            # Features kopieren, BEVOR der Layer entfernt wird
            crs = self.canvas.mapSettings().destinationCrs().authid()
            mem = QgsVectorLayer(f"Point?crs={crs}", "temp", "memory")
            dp = mem.dataProvider()
            dp.addAttributes(
                [
                    QgsField("name", QVariant.String),
                    QgsField("svg_path", QVariant.String),
                    QgsField("svg_content", QVariant.String),
                    QgsField("size", QVariant.Double),
                    QgsField("scale_with_map", QVARIANT_BOOL),
                    QgsField("unique_id", QVariant.String),
                    QgsField("label", QVariant.String),
                    QgsField("show_label", QVARIANT_BOOL),
                    QgsField("white_background", QVARIANT_BOOL),
                    QgsField("rotation", QVariant.Double),
                ]
            )
            mem.updateFields()

            # Features kopieren
            existing_fields = [field.name() for field in old_layer.fields()]
            for feat in old_layer.getFeatures():
                new_feat = QgsFeature(mem.fields())
                new_feat.setGeometry(feat.geometry())
                new_feat.setAttribute("name", feat.attribute("name"))
                new_feat.setAttribute("svg_path", feat.attribute("svg_path"))
                svg_content = feat.attribute("svg_content") if "svg_content" in existing_fields else ""
                new_feat.setAttribute("svg_content", svg_content)
                new_feat.setAttribute("size", feat.attribute("size"))
                new_feat.setAttribute(
                    "scale_with_map", feat.attribute("scale_with_map") if "scale_with_map" in existing_fields else False
                )
                new_feat.setAttribute(
                    "unique_id", feat.attribute("unique_id") if "unique_id" in existing_fields else str(uuid.uuid4())
                )

                # Label: Verwende vorhandenes oder erstelle Standard-Label
                if "label" in existing_fields and feat.attribute("label"):
                    new_feat.setAttribute("label", feat.attribute("label"))
                else:
                    # Erstelle Standard-Label aus SVG-Namen
                    svg_name = feat.attribute("name") or os.path.basename(feat.attribute("svg_path"))
                    default_label = os.path.splitext(svg_name)[0].replace("_", " ")
                    new_feat.setAttribute("label", default_label)

                new_feat.setAttribute(
                    "show_label", feat.attribute("show_label") if "show_label" in existing_fields else False
                )
                new_feat.setAttribute(
                    "white_background",
                    feat.attribute("white_background") if "white_background" in existing_fields else False,
                )
                new_feat.setAttribute("rotation", feat.attribute("rotation") if "rotation" in existing_fields else 0.0)
                mem.dataProvider().addFeature(new_feat)

            # Alten Layer AUS DEM PROJEKT entfernen, BEVOR die Datei geschrieben wird
            # Dies gibt die Datei frei, damit sie überschrieben werden kann
            old_layer_id = old_layer.id()
            QgsProject.instance().removeMapLayer(old_layer_id)

            # Kurze Wartezeit, damit QGIS die Datei vollständig freigibt
            import time

            time.sleep(0.1)

            # Temporäre Datei verwenden, um Konflikte zu vermeiden
            temp_gpkg = gpkg + ".temp"

            # Lösche temporäre Datei falls sie existiert
            if os.path.exists(temp_gpkg):
                try:
                    os.remove(temp_gpkg)
                except:
                    pass

            # Speichere zuerst in temporäre Datei
            opts = QgsVectorFileWriter.SaveVectorOptions()
            opts.driverName = "GPKG"
            opts.layerName = lname
            opts.actionOnExistingFile = QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteFile

            result = QgsVectorFileWriter.writeAsVectorFormatV2(
                mem, temp_gpkg, QgsProject.instance().transformContext(), opts
            )
            if result[0] != QgsVectorFileWriter.WriterError.NoError:
                self._show_error_alert(
                    "Layer-Aktualisierungsfehler",
                    f"Konnte Layer-Felder nicht aktualisieren: {result[1]}",
                    f"Pfad: {gpkg}\nFehler: {result[1]}",
                )
                return

            # Warte kurz, damit die temporäre Datei vollständig geschrieben ist
            time.sleep(0.1)

            # Temporäre Datei über die ursprüngliche Datei kopieren
            import shutil

            try:
                # Versuche zuerst, die ursprüngliche Datei zu löschen
                if os.path.exists(gpkg):
                    try:
                        os.remove(gpkg)
                        time.sleep(0.1)  # Kurze Wartezeit nach dem Löschen
                    except Exception as e:
                        print(f"Warnung: Konnte ursprüngliche Datei nicht löschen: {e}")

                # Verschiebe die temporäre Datei
                shutil.move(temp_gpkg, gpkg)
            except Exception as e:
                # Falls das Verschieben fehlschlägt, versuche zu kopieren und dann zu löschen
                try:
                    shutil.copy2(temp_gpkg, gpkg)
                    try:
                        os.remove(temp_gpkg)
                    except:
                        pass
                except Exception as e2:
                    self._show_error_alert(
                        "Layer-Aktualisierungsfehler",
                        f"Konnte aktualisierte Datei nicht speichern: {e2}",
                        f"Pfad: {gpkg}\nFehler: {e2}",
                    )
                    return
                print(f"Warnung: Temporäre Datei konnte nicht verschoben werden: {e}")

        except Exception as e:
            error_msg = f"Fehler beim Aktualisieren der Layer-Felder: {str(e)}"
            print(error_msg)
            import traceback

            traceback.print_exc()
            self._show_error_alert(
                "Layer-Aktualisierungsfehler",
                "Konnte Layer-Felder nicht aktualisieren",
                f"Pfad: {gpkg}\nFehler: {str(e)}",
            )

    def _init_renderer(self, layer):
        """Initialisiert den Renderer für den Layer."""
        print(f"DEBUG: _init_renderer aufgerufen mit layer: {layer}")
        if not layer:
            print("DEBUG: Layer ist None, beende _init_renderer")
            return

        # Erstelle einen einfachen Renderer für den Layer
        categories = []

        # Prüfe, ob der Layer Features hat
        if layer.featureCount() > 0:
            for feat in layer.getFeatures():
                svg_path_feat = feat.attribute("svg_path")
                svg_content_feat = (
                    feat.attribute("svg_content") if "svg_content" in [field.name() for field in layer.fields()] else ""
                )
                size = feat.attribute("size")
                scale_with_map = feat.attribute("scale_with_map")
                white_background = (
                    feat.attribute("white_background")
                    if "white_background" in [field.name() for field in layer.fields()]
                    else False
                )
                rotation = (
                    feat.attribute("rotation") if "rotation" in [field.name() for field in layer.fields()] else 0.0
                )
                sym = QgsMarkerSymbol.createSimple({})

                # Wenn weißer Hintergrund aktiviert ist, füge einen weißen Kreis als Hintergrund hinzu
                if white_background:
                    # Erstelle einen weißen Kreis als Hintergrund (etwas größer als das Symbol)
                    bg_layer = QgsSimpleMarkerSymbolLayer(QgsSimpleMarkerSymbolLayer.Shape.Circle, size * 1.2, 0)
                    bg_layer.setColor(QColor(255, 255, 255))  # Weiß
                    bg_layer.setStrokeColor(QColor(255, 255, 255))  # Weiß
                    bg_layer.setStrokeWidth(0)
                    if not scale_with_map:
                        bg_layer.setSizeUnit(QgsUnitTypes.RenderUnit.RenderMapUnits)
                    sym.changeSymbolLayer(0, bg_layer)

                # Verwende SVG-Inhalt direkt aus dem Speicher
                if svg_content_feat and svg_content_feat.strip():
                    # Erstelle temporäre SVG-Datei aus Inhalt
                    temp_svg = self._create_temp_svg_from_content(svg_content_feat, feat.id())
                    if temp_svg:
                        ly = QgsSvgMarkerSymbolLayer(temp_svg, size, 0)
                    else:
                        # Fallback: Verwende den gespeicherten Pfad
                        ly = QgsSvgMarkerSymbolLayer(svg_path_feat, size, 0)
                else:
                    # Versuche den Pfad zu verwenden - konvertiere relativen Pfad zu absolutem Pfad
                    if not os.path.isabs(svg_path_feat):
                        absolute_path = os.path.join(self.plugin_dir, svg_path_feat)
                        if os.path.exists(absolute_path):
                            ly = QgsSvgMarkerSymbolLayer(absolute_path, size, 0)
                        else:
                            # Fallback: Verwende den ursprünglichen Pfad
                            ly = QgsSvgMarkerSymbolLayer(svg_path_feat, size, 0)
                    else:
                        ly = QgsSvgMarkerSymbolLayer(svg_path_feat, size, 0)

                if not scale_with_map:
                    ly.setSizeUnit(QgsUnitTypes.RenderUnit.RenderMapUnits)

                # Rotation anwenden
                ly.setAngle(rotation)

                # SVG-Layer hinzufügen (als zusätzliches Layer, wenn Hintergrund vorhanden ist)
                if white_background:
                    sym.appendSymbolLayer(ly)
                else:
                    sym.changeSymbolLayer(0, ly)
                # Verwende unique_id für die Kategorie, damit jedes Feature individuell skaliert werden kann
                unique_id = (
                    feat.attribute("unique_id")
                    if "unique_id" in [field.name() for field in layer.fields()]
                    else str(feat.id())
                )
                # Verwende den Namen des Features für die Anzeige (Dateiname ohne Pfad und ohne .svg)
                feature_name = feat.attribute("name") if feat.attribute("name") else os.path.basename(svg_path_feat)
                # Entferne .svg Endung falls vorhanden
                display_name = os.path.splitext(feature_name)[0]
                cat = QgsRendererCategory(unique_id, sym, display_name)
                categories.append(cat)

        if categories:
            renderer = QgsCategorizedSymbolRenderer("unique_id", categories)
            layer.setRenderer(renderer)
        else:
            # Fallback: Einfacher Marker-Symbol
            sym = QgsMarkerSymbol.createSimple({})
            renderer = QgsSingleSymbolRenderer(sym)
            layer.setRenderer(renderer)

        # Labeling konfigurieren
        self._setup_labeling(layer)

        layer.triggerRepaint()
        print("DEBUG: Renderer erfolgreich initialisiert und Layer neu gezeichnet")

    def _setup_labeling(self, layer):
        """Konfiguriert das Labeling für den Layer."""
        try:
            # Prüfe, ob die erforderlichen Felder existieren
            field_names = [field.name() for field in layer.fields()]
            if "label" not in field_names or "show_label" not in field_names:
                print("DEBUG: Label-Felder nicht verfügbar, überspringe Labeling")
                return

            # Erstelle Label-Einstellungen
            label_settings = QgsPalLayerSettings()

            # Text-Format konfigurieren
            text_format = QgsTextFormat()
            text_format.setSize(self.settings.label_font_size_mm)  # Schriftgröße
            text_format.setSizeUnit(Qgis.RenderUnit.Millimeters)
            text_format.setColor(Qt.GlobalColor.black)
            # Verwende fette Schrift für bessere Sichtbarkeit
            font = text_format.font()
            font.setBold(True)
            text_format.setFont(font)

            # Buffer-Einstellungen für bessere Lesbarkeit
            buffer_settings = QgsTextBufferSettings()
            buffer_settings.setEnabled(True)
            buffer_settings.setSize(self.settings.label_buffer_size_mm)  # Buffer-Größe
            buffer_settings.setSizeUnit(Qgis.RenderUnit.Millimeters)
            buffer_settings.setColor(Qt.GlobalColor.white)
            text_format.setBuffer(buffer_settings)

            label_settings.setFormat(text_format)

            # Label-Feld setzen
            label_settings.fieldName = "label"
            label_settings.isExpression = False

            # Expression: Nur anzeigen wenn show_label = 1 (true) und label nicht leer
            # Verwende dataDefinedProperties() statt setDataDefinedProperty()
            # Vereinfachte Expression für bessere Kompatibilität
            expr = 'CASE WHEN "show_label" = 1 AND "label" IS NOT NULL AND "label" <> \'\' THEN 1 ELSE 0 END'
            try:
                # Versuche verschiedene Property-Konstanten
                # In QGIS 3.x könnte Show ein Integer oder eine Enum sein
                show_property = QgsProperty.fromExpression(expr)

                label_props = label_settings.dataDefinedProperties()
                if self.settings.label_enable:
                    label_props.setProperty(QgsPalLayerSettings.Property.Show, show_property)
                else:
                    label_props.setProperty(QgsPalLayerSettings.Property.Show, False)

            except Exception as e:
                print(f"DEBUG: Fehler beim Setzen der Expression: {e}")
                import traceback

                traceback.print_exc()
                # Fallback: Verwende Expression im Feld-Namen
                try:
                    expr_simple = 'CASE WHEN "show_label" = 1 THEN "label" ELSE \'\' END'
                    label_settings.isExpression = True
                    label_settings.fieldName = expr_simple
                    print(f"DEBUG: Alternative Label-Expression als Feld-Expression gesetzt: {expr_simple}")
                except Exception as e2:
                    print(f"DEBUG: Auch alternative Expression fehlgeschlagen: {e2}")
                    print("DEBUG: Labels werden ohne Filter angezeigt")

            # Label-Positionierung - unter dem Symbol
            try:
                # 1) Place labels around the point (cartographic / ordered positions)
                if hasattr(Qgis, "LabelPlacement") and hasattr(Qgis.LabelPlacement, "OverPoint"):
                    label_settings.placement = Qgis.LabelPlacement.OverPoint
                else:
                    # Fallback for older versions
                    label_settings.placement = QgsPalLayerSettings.OverPoint

                # 2) Tell QGIS to put the label in the bottom/below quadrant of the point
                if hasattr(Qgis, "LabelQuadrantPosition"):
                    # QGIS >= 3.26: use the new enum
                    label_settings.quadOffset = Qgis.LabelQuadrantPosition.Below
                else:
                    # Older API: use QuadrantPosition enum from QgsPalLayerSettings
                    if hasattr(QgsPalLayerSettings, "BottomMiddle"):
                        label_settings.quadOffset = QgsPalLayerSettings.BottomMiddle
                    elif hasattr(QgsPalLayerSettings, "Bottom"):
                        label_settings.quadOffset = QgsPalLayerSettings.Bottom
                    else:
                        # last resort: standard bottom-middle index
                        label_settings.quadOffset = QgsPalLayerSettings.BottomMiddle if hasattr(
                            QgsPalLayerSettings, "BottomMiddle"
                        ) else 0
            except Exception as e:
                print(f"DEBUG: Position festsetzen fehlgeschlagen: {e}")

            try:
                # Offset-Werte in Points , Abstand abhängig von der Größe des Zeichens
                if hasattr(Qgis, "RenderUnit") and hasattr(Qgis.RenderUnit, "Points"):
                    label_settings.offsetUnits = Qgis.RenderUnit.Points
                size_property = QgsProperty.fromExpression("array(0,size)")
                label_props.setProperty(QgsPalLayerSettings.Property.OffsetXY, size_property)
            except Exception as e:
                print(f"DEBUG: Fehler bei der Festsetzung der Position: {e}")

            # Labeling auf Layer anwenden
            layer.setLabelsEnabled(True)
            layer.setLabeling(QgsVectorLayerSimpleLabeling(label_settings))

            print("DEBUG: Labeling erfolgreich konfiguriert")
            print(f"DEBUG: Label-Feld: {label_settings.fieldName}")
            print(f"DEBUG: Labels aktiviert: {layer.labelsEnabled()}")

        except Exception as e:
            print(f"DEBUG: Fehler beim Konfigurieren des Labelings: {e}")
            import traceback

            traceback.print_exc()

    def _update_renderer(self):
        """Aktualisiert den Renderer mit allen Features."""
        print("DEBUG: _update_renderer aufgerufen")
        if not self.layer:
            print("DEBUG: self.layer ist None, beende _update_renderer")
            return

        # Verwende die _init_renderer Methode, die den aktuellen Layer aktualisiert
        print("DEBUG: Rufe _init_renderer auf")
        self._init_renderer(self.layer)

        # Labeling auch aktualisieren
        self._setup_labeling(self.layer)

    def _save_layer(self):
        """Speichert den aktuellen Layer - ist jetzt nicht mehr nötig, da Layer immer persistent ist."""
        print("DEBUG: _save_layer aufgerufen - Layer ist bereits persistent")
        # Der Layer ist bereits persistent, nichts zu tun
        return

    def _on_project_save(self):
        """Wird aufgerufen, wenn das Projekt gespeichert wird - verschiebt die Datei zum Projektpfad."""
        print("DEBUG: Projekt wird gespeichert, verschiebe Layer-Datei zum Projektpfad")
        if not self.layer:
            return

        # Prüfe, ob der Layer eine GeoPackage ist
        if self.layer.providerType() != "ogr":
            print("DEBUG: Layer ist keine GeoPackage, nichts zu tun")
            return

        proj = QgsProject.instance()
        pfile = proj.fileName()

        if not pfile:
            print("DEBUG: Kein Projektpfad verfügbar")
            return

        # Save the settings
        self.settings.save_settings(QgsProject.instance())

        # Aktuelle Datei-Pfad ermitteln
        current_source = self.layer.source().split("|")[0]
        print(f"DEBUG: Aktuelle Layer-Datei: {current_source}")

        # Prüfe, ob die aktuelle Datei existiert
        if not os.path.exists(current_source):
            print(f"DEBUG: Aktuelle Layer-Datei existiert nicht: {current_source}")
            return

        # Neuer Pfad neben der Projektdatei
        base = os.path.splitext(pfile)[0] + "_taktischezeichen"
        new_gpkg = base + ".gpkg"

        # Prüfe, ob die Datei bereits am richtigen Ort ist
        if os.path.abspath(current_source) == os.path.abspath(new_gpkg):
            print("DEBUG: Datei ist bereits am richtigen Ort")
            return

        try:
            # Stelle sicher, dass das Zielverzeichnis existiert
            target_dir = os.path.dirname(new_gpkg)
            if not os.path.exists(target_dir):
                os.makedirs(target_dir, exist_ok=True)
                print(f"DEBUG: Zielverzeichnis erstellt: {target_dir}")

            # Prüfe Schreibrechte im Zielverzeichnis
            if not os.access(target_dir, os.W_OK):
                raise Exception(f"Keine Schreibrechte im Zielverzeichnis: {target_dir}")

            # Vor dem Export sicherstellen, dass keine Edits offen sind
            try:
                if self.layer.isEditable():
                    print("DEBUG: Layer ist im Bearbeitungsmodus - committe Änderungen vor Export")
                    self.layer.commitChanges()
            except Exception as e:
                print(f"DEBUG: Hinweis beim Committen vor Export: {e}")

            # Wenn Ziel-Datei existiert, lösche sie zuerst
            if os.path.exists(new_gpkg):
                print(f"DEBUG: Ziel-Datei existiert bereits, lösche sie: {new_gpkg}")
                try:
                    os.remove(new_gpkg)
                except Exception as e:
                    print(f"DEBUG: Warnung - Konnte Ziel-Datei nicht löschen: {e}")

            # Verwende QGIS VectorFileWriter für sichere Kopie
            from qgis.core import QgsVectorFileWriter, QgsVectorLayer

            print(f"DEBUG: Kopiere Layer-Daten von {current_source} nach {new_gpkg}")

            # Erstelle Kopie mit QGIS VectorFileWriter
            save_options = QgsVectorFileWriter.SaveVectorOptions()
            save_options.driverName = "GPKG"
            save_options.layerName = "taktische_zeichen"
            # Wichtiger: ganze Datei überschreiben statt nur Layer
            save_options.actionOnExistingFile = QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteFile

            transform_context = QgsProject.instance().transformContext()
            try:
                result = QgsVectorFileWriter.writeAsVectorFormatV3(
                    self.layer, new_gpkg, transform_context, save_options
                )
            except AttributeError:  # Fallback in case <3.20
                result = QgsVectorFileWriter.writeAsVectorFormatV3(
                    self.layer, new_gpkg, transform_context, save_options
                )

            if result[0] != QgsVectorFileWriter.WriterError.NoError:
                print(f"DEBUG: Writer-Export fehlgeschlagen: {result[1]} - versuche Datei-Kopie als Fallback")
                # Fallback: Physische Datei kopieren (kann fehlschlagen, wenn gesperrt)
                import shutil

                shutil.copy2(current_source, new_gpkg)

            print(f"DEBUG: Layer-Daten erfolgreich exportiert/kopiert")

            # Entferne alten Layer aus Projekt
            old_layer_id = self.layer.id()
            QgsProject.instance().removeMapLayer(old_layer_id)

            # Lade den Layer vom neuen Ort
            uri = f"{new_gpkg}|layername=taktische_zeichen"
            new_layer = QgsVectorLayer(uri, "THW Toolbox Marker", "ogr")

            if not new_layer.isValid():
                raise Exception(f"Neuer Layer ist nicht gültig: {new_layer.error().message()}")

            QgsProject.instance().addMapLayer(new_layer)
            self.layer = new_layer

            # Aktualisiere Referenzen in Tools
            self._update_tool_references()

            # Renderer neu initialisieren, damit die Symbole wieder angezeigt werden
            self._init_renderer(new_layer)

            # Versuche die alte Datei zu löschen (optional, da sie nicht mehr verwendet wird)
            try:
                # Warte kurz, damit QGIS die Datei freigibt
                import time

                time.sleep(0.5)
                os.remove(current_source)
                print(f"DEBUG: Alte Datei gelöscht: {current_source}")
            except Exception as e:
                print(f"DEBUG: Warnung - Konnte alte Datei nicht löschen (wird beim nächsten Start bereinigt): {e}")

            print("DEBUG: Layer erfolgreich zum Projektpfad verschoben")

        except Exception as e:
            error_msg = f"Fehler beim Verschieben der Layer-Datei: {str(e)}"
            print(error_msg)
            self._show_error_alert(
                "Fehler beim Projekt-Speichern",
                "Konnte Layer-Datei nicht zum Projektpfad verschieben",
                f"Von: {current_source}\nNach: {new_gpkg}\nFehler: {str(e)}\n\nHinweis: Die Layer-Daten bleiben im ursprünglichen Verzeichnis erhalten.",
            )

    def _cleanup_temp_files(self):
        """Räumt temporäre Dateien im Plugin-Ordner auf."""
        try:
            import glob
            import shutil
            import time

            # 1. Bereinige alte GeoPackage-Dateien im tmp-Ordner
            tmp_dir = os.path.join(self.plugin_dir, "tmp")
            if os.path.exists(tmp_dir):
                temp_pattern = os.path.join(tmp_dir, "*_taktischezeichen.gpkg")
                temp_files = glob.glob(temp_pattern)
            else:
                temp_files = []

            # Auch alte Dateien im Plugin-Root-Ordner bereinigen (für Rückwärtskompatibilität)
            old_pattern = os.path.join(self.plugin_dir, "*_taktischezeichen.gpkg")
            old_files = glob.glob(old_pattern)
            temp_files.extend(old_files)

            current_time = time.time()
            cleanup_threshold = 24 * 60 * 60  # 24 Stunden

            for temp_file in temp_files:
                try:
                    # Prüfe das Alter der Datei
                    file_age = current_time - os.path.getmtime(temp_file)

                    # Lösche Dateien, die älter als 24 Stunden sind
                    if file_age > cleanup_threshold:
                        # Versuche die Datei zu löschen
                        try:
                            os.remove(temp_file)
                            print(f"DEBUG: Temporäre GeoPackage-Datei gelöscht: {temp_file}")
                        except PermissionError:
                            # Datei ist noch gesperrt, versuche später
                            print(f"DEBUG: Temporäre GeoPackage-Datei noch gesperrt, überspringe: {temp_file}")

                except Exception as e:
                    print(f"DEBUG: Konnte temporäre GeoPackage-Datei nicht verarbeiten {temp_file}: {e}")

            # 2. Bereinige temporäre SVG-Cache-Dateien
            temp_dirs = [
                os.path.join(self.plugin_dir, "temp_files", "svg_cache"),
                os.path.join(self.plugin_dir, "temp_files", "preview_cache"),
                os.path.join(self.plugin_dir, "temp_svg"),  # Altes Verzeichnis für Rückwärtskompatibilität
            ]

            for temp_dir in temp_dirs:
                if os.path.exists(temp_dir):
                    try:
                        # Lösche alle Dateien älter als 1 Stunde
                        cache_threshold = 60 * 60  # 1 Stunde

                        for filename in os.listdir(temp_dir):
                            file_path = os.path.join(temp_dir, filename)
                            if os.path.isfile(file_path):
                                file_age = current_time - os.path.getmtime(file_path)

                                if file_age > cache_threshold:
                                    try:
                                        os.remove(file_path)
                                        print(f"DEBUG: Temporäre Cache-Datei gelöscht: {file_path}")
                                    except PermissionError:
                                        print(f"DEBUG: Cache-Datei noch gesperrt, überspringe: {file_path}")

                    except Exception as e:
                        print(f"DEBUG: Fehler beim Bereinigen des Cache-Verzeichnisses {temp_dir}: {e}")

            # 3. Entferne leere temp_files Verzeichnisse
            temp_files_dir = os.path.join(self.plugin_dir, "temp_files")
            if os.path.exists(temp_files_dir):
                try:
                    # Prüfe ob alle Unterverzeichnisse leer sind
                    all_empty = True
                    for root, dirs, files in os.walk(temp_files_dir):
                        if files:  # Wenn es noch Dateien gibt
                            all_empty = False
                            break

                    # Wenn alle Unterverzeichnisse leer sind, entferne das Hauptverzeichnis
                    if all_empty:
                        shutil.rmtree(temp_files_dir)
                        print(f"DEBUG: Leeres temp_files Verzeichnis entfernt: {temp_files_dir}")

                except Exception as e:
                    print(f"DEBUG: Fehler beim Entfernen des temp_files Verzeichnisses: {e}")

            # 4. Entferne leeren tmp-Ordner falls er leer ist
            if os.path.exists(tmp_dir):
                try:
                    if not os.listdir(tmp_dir):  # Wenn der Ordner leer ist
                        os.rmdir(tmp_dir)
                        print(f"DEBUG: Leerer tmp-Ordner entfernt: {tmp_dir}")
                except Exception as e:
                    print(f"DEBUG: Fehler beim Entfernen des tmp-Ordners: {e}")

        except Exception as e:
            print(f"DEBUG: Fehler beim Aufräumen temporärer Dateien: {e}")

    def _update_tool_references(self):
        """Aktualisiert alle Tool-Referenzen auf den aktuellen Layer."""
        if hasattr(self, "ident_tool") and self.ident_tool:
            self.ident_tool.layer = self.layer
        if hasattr(self, "move_tool") and self.move_tool:
            self.move_tool.layer = self.layer

    def _create_temp_svg_from_content(self, svg_content, feature_id):
        """Erstellt eine temporäre SVG-Datei aus dem gespeicherten SVG-Inhalt."""
        import tempfile

        # Erstelle temporäres Verzeichnis falls es nicht existiert
        temp_dir = os.path.join(self.plugin_dir, "temp_files", "svg_cache")
        os.makedirs(temp_dir, exist_ok=True)

        # Erstelle eindeutigen Dateinamen
        temp_filename = f"feature_{feature_id}.svg"
        temp_path = os.path.join(temp_dir, temp_filename)

        try:
            # Schreibe SVG-Inhalt in temporäre Datei
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(svg_content)

            # Bereinige alte temporäre Dateien (behalte nur die letzten 50)
            temp_files = [f for f in os.listdir(temp_dir) if f.startswith("feature_")]
            if len(temp_files) > 50:
                temp_files.sort(key=lambda x: os.path.getctime(os.path.join(temp_dir, x)))
                for old_file in temp_files[:-50]:
                    try:
                        os.remove(os.path.join(temp_dir, old_file))
                    except:
                        pass

            return temp_path
        except Exception as e:
            error_msg = f"Fehler beim Erstellen der temporären SVG-Datei: {str(e)}"
            print(error_msg)
            self._show_error_alert(
                "SVG-Verarbeitungsfehler",
                "Konnte temporäre SVG-Datei nicht erstellen",
                f"Feature ID: {feature_id}\nFehler: {str(e)}",
            )
            return None

    def _place_feature(self, svg_path, point):
        print(f"DEBUG: _place_feature aufgerufen mit svg_path={svg_path}, point={point}")

        # Prüfe, ob eine Karte vorhanden ist
        if not self._check_map_available():
            self._show_error_alert(
                "Keine Karte vorhanden",
                "Bitte ziehen Sie zuerst eine Karte in das Projekt ein.",
                "Das Plugin benötigt eine Karte mit einem Koordinatensystem (CRS), um Symbole platzieren zu können.\n\n"
                "So fügen Sie eine Karte hinzu:\n"
                "1. Gehen Sie zu 'Browser' im QGIS-Fenster\n"
                "2. Ziehen Sie eine Karte (z.B. OpenStreetMap) in das Projekt\n"
                "3. Versuchen Sie erneut, ein Symbol zu platzieren",
            )
            return

        if not self.layer:
            print("DEBUG: self.layer ist None, beende _place_feature")
            return

        print("DEBUG: Prüfe Layer-Felder")
        # Felder überprüfen und ggf. hinzufügen
        required_fields = {
            "name": QVariant.String,
            "svg_path": QVariant.String,
            "svg_content": QVariant.String,  # Neues Feld für SVG-Inhalt
            "size": QVariant.Double,
            "scale_with_map": QVARIANT_BOOL,
            "unique_id": QVariant.String,  # Eindeutige ID für jedes Zeichen
            "label": QVariant.String,  # Label-Text für das Zeichen
            "show_label": QVARIANT_BOOL,  # Ob das Label angezeigt werden soll
            "white_background": QVARIANT_BOOL,  # Ob ein weißer Hintergrund angezeigt werden soll
            "rotation": QVariant.Double,  # Rotationswinkel in Grad
        }

        existing_fields = {field.name(): field.type() for field in self.layer.fields()}
        print(f"DEBUG: Bestehende Felder: {[field.name() for field in self.layer.fields()]}")

        # Fehlende Felder hinzufügen
        fields_to_add = []
        for field_name, field_type in required_fields.items():
            if field_name not in existing_fields:
                fields_to_add.append(QgsField(field_name, field_type))

        if fields_to_add:
            self.layer.startEditing()
            for field in fields_to_add:
                self.layer.addAttribute(field)
            self.layer.commitChanges()

        # SVG-Inhalt lesen
        svg_content = ""
        try:
            if os.path.exists(svg_path):
                with open(svg_path, "r", encoding="utf-8") as f:
                    svg_content = f.read()
            else:
                self._show_error_alert(
                    "SVG-Datei nicht gefunden",
                    f"Die SVG-Datei konnte nicht gefunden werden: {svg_path}",
                    f"Pfad: {svg_path}",
                )
                return
        except Exception as e:
            error_msg = f"Fehler beim Lesen der SVG-Datei: {str(e)}"
            print(error_msg)
            self._show_error_alert(
                "SVG-Lesefehler", "Konnte SVG-Datei nicht lesen", f"Pfad: {svg_path}\nFehler: {str(e)}"
            )
            return

        # Relativen Pfad zum Plugin-Verzeichnis speichern
        plugin_dir = os.path.dirname(__file__)
        if svg_path.startswith(plugin_dir):
            relative_path = os.path.relpath(svg_path, plugin_dir)
        else:
            relative_path = svg_path

        if self.settings.new_icon_fixed_size:
            icon_size = self.settings.new_icon_size
        else:
            # Intelligente Größenberechnung basierend auf dem aktuellen Zoom-Faktor
            map_units_per_pixel = self.canvas.mapUnitsPerPixel()
            # Berechne eine geeignete Größe basierend auf dem Zoom-Faktor
            # Bei kleineren map_units_per_pixel (starker Zoom) = größere Symbole
            # Bei größeren map_units_per_pixel (schwacher Zoom) = kleinere Symbole
            base_size = 30.0  # Basis-Größe
            zoom_factor = 1.0 / max(map_units_per_pixel, 0.001)  # Vermeide Division durch Null
            icon_size = base_size * zoom_factor

            # Prüfe, ob bereits Symbole vorhanden sind und verwende mindestens die Größe des kleinsten Symbols
            if self.layer.featureCount() > 0:
                min_existing_size = float("inf")
                for feature in self.layer.getFeatures():
                    feature_size = feature.attribute("size")
                    if feature_size and feature_size > 0:
                        min_existing_size = min(min_existing_size, feature_size)

                # Wenn ein kleinstes Symbol gefunden wurde, verwende mindestens dessen Größe
                if min_existing_size != float("inf"):
                    icon_size = max(icon_size, min_existing_size)

            # Begrenze die Größe auf einen vernünftigen Bereich
            icon_size = max(10.0, min(500.0, icon_size))
        # Standard-Label aus SVG-Namen erstellen
        svg_name = os.path.basename(svg_path)
        # Entferne .svg Endung und ersetze Unterstriche durch Leerzeichen
        default_label = os.path.splitext(svg_name)[0].replace("_", " ")

        # Feature erstellen
        f = QgsFeature(self.layer.fields())
        f.setGeometry(QgsGeometry.fromPointXY(point))
        f.setAttribute("name", os.path.basename(svg_path))
        f.setAttribute("svg_path", relative_path)  # Relativer Pfad
        f.setAttribute("svg_content", svg_content)  # SVG-Inhalt speichern
        f.setAttribute("size", icon_size)  # Adaptive Größe basierend auf Zoom-Faktor
        f.setAttribute("scale_with_map", self.settings.new_icon_scaling_with_map)  # Standardmäßig nicht mit Karte skalieren
        f.setAttribute("unique_id", str(uuid.uuid4()))  # Eindeutige ID generieren
        f.setAttribute("label", default_label)  # Standard-Label aus SVG-Namen
        f.setAttribute("show_label", False)  # Label standardmäßig nicht anzeigen
        f.setAttribute("white_background", False)  # Weißer Hintergrund standardmäßig nicht aktiviert
        f.setAttribute("rotation", 0.0)  # Rotation standardmäßig 0 Grad

        # Feature zum Layer hinzufügen
        print("DEBUG: Füge Feature zum Layer hinzu")
        self.layer.startEditing()
        result = self.layer.dataProvider().addFeature(f)
        print(f"DEBUG: Feature hinzugefügt: {result}")

        self.layer.commitChanges()
        print("DEBUG: Änderungen committet")

        # Hole die Feature-ID nach dem Commit (dann ist sie korrekt gesetzt)
        new_feature_id = f.id()
        print(f"DEBUG: Neue Feature-ID nach Commit: {new_feature_id}")

        self.layer.updateExtents()
        print("DEBUG: Extents aktualisiert")

        # Layer ist bereits persistent, kein zusätzliches Speichern nötig
        print("DEBUG: Layer ist bereits persistent")

        # Renderer aktualisieren
        print("DEBUG: Aktualisiere Renderer")
        self._update_renderer()

        # Neues Feature automatisch auswählen und im Dock anzeigen
        if result and self.ident_tool and hasattr(self.ident_tool, "feature_dock"):
            print("DEBUG: Wähle neues Feature automatisch aus")

            # Finde das neueste Feature im Layer (das gerade hinzugefügte)
            # Da die Feature-ID möglicherweise noch nicht korrekt ist, suchen wir nach dem Feature mit den gleichen Attributen
            latest_feature = None
            for feature in self.layer.getFeatures():
                if feature.attribute("unique_id") == f.attribute("unique_id") or (
                    feature.attribute("svg_path") == f.attribute("svg_path")
                    and feature.geometry().distance(QgsGeometry.fromPointXY(point)) < 0.1
                ):
                    latest_feature = feature
                    break

            if latest_feature and latest_feature.isValid():
                print(f"DEBUG: Gefundenes Feature ID: {latest_feature.id()}")
                # Zeige das Feature im Dock an
                self.ident_tool.feature_dock.show_feature(latest_feature, self)
                # Aktiviere den Move-Modus für das neue Feature
                if hasattr(self, "move_tool"):
                    self.move_tool.moving_feature = latest_feature
                    self.move_tool.set_move_mode(True)
                    self.canvas.setCursor(Qt.CursorShape.ClosedHandCursor)
                print(f"DEBUG: Feature {latest_feature.id()} automatisch ausgewählt und im Dock angezeigt")
            else:
                print("DEBUG: Konnte das neue Feature nicht finden")

    # Identify callbacks
    def delete_feature(self, fid):
        """Löscht ein Feature und aktualisiert den Layer."""
        if not self.layer:
            return

        # Prüfe, ob der Layer eine GeoPackage ist
        if self.layer.providerType() == "ogr":
            # Direkt aus der GeoPackage löschen
            self.layer.startEditing()
            self.layer.deleteFeature(fid)
            self.layer.commitChanges()

            # Renderer aktualisieren
            self._update_renderer()
        else:
            # Fallback für Memory-Layer
            self._delete_feature_fallback(fid)

        # Nach dem Löschen die Baumstruktur im Dock aktualisieren
        if hasattr(self, "svg_dock_widget"):
            self.svg_dock_widget.treeWidget.clear()
            self.svg_dock_widget.populate_root_folders()

        # Layer-Panel (Layer Tree) aktualisieren
        if hasattr(self.iface, "layerTreeView"):
            self.iface.layerTreeView().refreshLayerSymbology(self.layer.id())

        # Canvas neu zeichnen
        self.canvas.refresh()
        self.canvas.update()

    def _delete_feature_fallback(self, fid):
        """Fallback-Methode für das Löschen von Features in Memory-Layern."""
        if not self.layer:
            return

        crs = self.canvas.mapSettings().destinationCrs().authid()

        # Temporären Layer erstellen
        temp_layer = QgsVectorLayer(f"Point?crs={crs}", "temp", "memory")
        dp = temp_layer.dataProvider()

        # Felder hinzufügen
        dp.addAttributes(
            [
                QgsField("name", QVariant.String),
                QgsField("svg_path", QVariant.String),
                QgsField("svg_content", QVariant.String),
                QgsField("size", QVariant.Double),
                QgsField("scale_with_map", QVARIANT_BOOL),
                QgsField("unique_id", QVariant.String),
                QgsField("label", QVariant.String),
                QgsField("show_label", QVARIANT_BOOL),
                QgsField("white_background", QVARIANT_BOOL),
                QgsField("rotation", QVariant.Double),
            ]
        )
        temp_layer.updateFields()

        # Alle Features außer dem zu löschenden kopieren
        for feat in self.layer.getFeatures():
            if feat.id() != fid:
                new_feat = QgsFeature(temp_layer.fields())
                new_feat.setGeometry(feat.geometry())
                new_feat.setAttribute("name", feat.attribute("name"))
                new_feat.setAttribute("svg_path", feat.attribute("svg_path"))
                new_feat.setAttribute(
                    "svg_content",
                    feat.attribute("svg_content")
                    if "svg_content" in [field.name() for field in self.layer.fields()]
                    else "",
                )
                new_feat.setAttribute("size", feat.attribute("size"))
                new_feat.setAttribute("scale_with_map", feat.attribute("scale_with_map"))
                new_feat.setAttribute(
                    "unique_id",
                    feat.attribute("unique_id")
                    if "unique_id" in [field.name() for field in self.layer.fields()]
                    else str(uuid.uuid4()),
                )

                # Label: Verwende vorhandenes oder erstelle Standard-Label
                if "label" in [field.name() for field in self.layer.fields()] and feat.attribute("label"):
                    new_feat.setAttribute("label", feat.attribute("label"))
                else:
                    # Erstelle Standard-Label aus SVG-Namen
                    svg_name = feat.attribute("name") or os.path.basename(feat.attribute("svg_path"))
                    default_label = os.path.splitext(svg_name)[0].replace("_", " ")
                    new_feat.setAttribute("label", default_label)

                new_feat.setAttribute(
                    "show_label",
                    feat.attribute("show_label")
                    if "show_label" in [field.name() for field in self.layer.fields()]
                    else False,
                )
                new_feat.setAttribute(
                    "white_background",
                    feat.attribute("white_background")
                    if "white_background" in [field.name() for field in self.layer.fields()]
                    else False,
                )
                new_feat.setAttribute(
                    "rotation",
                    feat.attribute("rotation")
                    if "rotation" in [field.name() for field in self.layer.fields()]
                    else 0.0,
                )
                temp_layer.dataProvider().addFeature(new_feat)

        # Alten Layer aus dem Projekt entfernen
        QgsProject.instance().removeMapLayer(self.layer.id())

        # Neuen Layer erstellen und zum Projekt hinzufügen
        self.layer = temp_layer
        QgsProject.instance().addMapLayer(self.layer)

        # Renderer neu erstellen
        self._update_renderer()

        # Layer-Referenzen in anderen Klassen aktualisieren
        self._update_tool_references()

    

    def _open_config_dialog(self):
        dialog = QDialog(self.iface.mainWindow())
        dialog.setWindowTitle("THW Toolbox Einstellungen")
        layout = QVBoxLayout(dialog)

        ##### Default Icon Settings #####
        default_icon_settings_box = QGroupBox("Einstellungen für neue Zeichen")
        default_icon_form = QFormLayout()

        # Scaling with Map Setting
        cb_scale = QCheckBox()
        cb_scale.setChecked(self.settings.new_icon_scaling_with_map)
        default_icon_form.addRow("Neue Zeichen mit Karte skalieren", cb_scale)

        # Automatic Fixed Size Setting
        cb_fixed_size = QCheckBox()
        cb_fixed_size.setChecked(self.settings.new_icon_fixed_size)
        default_icon_form.addRow("Neue Zeichen mit fixer Standardgröße", cb_fixed_size)

        # Default Size (only active if cb_fixed_size is enabled)
        spin_icon_size =QSpinBox()
        spin_icon_size.setMinimum(10)
        spin_icon_size.setMaximum(200)
        spin_icon_size.setValue(self.settings.new_icon_size)
        spin_icon_size.setSingleStep(1)  # Schrittweite
        default_icon_form.addRow("Fixe Standardgröße für neue Zeichen",spin_icon_size)
        def update_spin_icon_size(checked):
            spin_icon_size.setEnabled(checked)
        cb_fixed_size.stateChanged.connect(update_spin_icon_size)
        update_spin_icon_size(cb_fixed_size.isChecked())

        # Coordinate System of Label
        dropdown_crs = QComboBox()
        dropdown_crs.addItems(["MGRS","UTM"])
        current_index = dropdown_crs.findText(self.settings.new_icon_crs)
        if current_index >= 0:
            dropdown_crs.setCurrentIndex(current_index)
        # default_icon_form.addRow("Koordinantesystem für Standortbeschriftung", dropdown_crs)

        default_icon_settings_box.setLayout(default_icon_form)
        layout.addWidget(default_icon_settings_box)

        ##### Label Settings #####
        label_settings_box = QGroupBox("Label Settings")
        label_settings_form = QFormLayout()

        # Global Enable
        cb_label_enable = QCheckBox()
        cb_label_enable.setChecked(self.settings.label_enable)
        label_settings_form.addRow("Aktivierte Labels anzeigen", cb_label_enable)

        # Label Size
        sb_label_font_size = QSpinBox()
        sb_label_font_size.setMinimum(1)
        sb_label_font_size.setMaximum(100)
        sb_label_font_size.setSingleStep(1)
        sb_label_font_size.setValue(int(self.settings.label_font_size_mm * 10))
        label_settings_form.addRow("Label Schriftgröße", sb_label_font_size)

        # Buffer Size
        sb_label_buffer_size = QSpinBox()
        sb_label_buffer_size.setMinimum(1)
        sb_label_buffer_size.setMaximum(50)
        sb_label_buffer_size.setSingleStep(1)
        sb_label_buffer_size.setValue(int(self.settings.label_buffer_size_mm * 10))
        label_settings_form.addRow("Label Rahmendicke", sb_label_buffer_size)

        label_settings_box.setLayout(label_settings_form)
        layout.addWidget(label_settings_box)


        # Bestätigen / Abbrechen
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        layout.addWidget(button_box)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)

        result = dialog.exec_()
        if result == QDialog.Accepted:
            self.settings.new_icon_scaling_with_map = cb_scale.isChecked()
            self.settings.new_icon_fixed_size = cb_fixed_size.isChecked()
            self.settings.new_icon_size = spin_icon_size.value()
            self.settings.new_icon_crs = dropdown_crs.currentText()

            self.settings.label_enable = cb_label_enable.isChecked()
            self.settings.label_font_size_mm = sb_label_font_size.value() / 10.0
            self.settings.label_buffer_size_mm = sb_label_buffer_size.value() / 10.0

            self.settings.save_settings(QgsProject.instance())
            self._init_renderer(self.layer)


    def resize_feature(self, fid, size):
        if not self.layer:
            return

        idx = self.layer.fields().indexFromName("size")
        self.layer.startEditing()
        self.layer.changeAttributeValue(fid, idx, size)
        self.layer.commitChanges()
        self.layer.triggerRepaint()

        # Renderer aktualisieren
        self._update_renderer()

        # Layer ist bereits persistent, kein zusätzliches Speichern nötig

    def toggle_scale(self, fid, scale_with_map):
        if not self.layer:
            return

        idx = self.layer.fields().indexFromName("scale_with_map")
        self.layer.startEditing()
        self.layer.changeAttributeValue(fid, idx, scale_with_map)
        self.layer.commitChanges()

        # Renderer aktualisieren
        self._update_renderer()

        # Layer ist bereits persistent, kein zusätzliches Speichern nötig

    def update_feature_label(self, fid, label_text):
        """Aktualisiert das Label eines Features"""
        if not self.layer:
            return

        idx = self.layer.fields().indexFromName("label")
        self.layer.startEditing()
        self.layer.changeAttributeValue(fid, idx, label_text)
        self.layer.commitChanges()

        # Feature-Daten für Debug ausgeben
        feature = self.layer.getFeature(fid)
        if feature.isValid():
            print(
                f"DEBUG: update_feature_label - Feature {fid}: show_label={feature.attribute('show_label')}, label='{feature.attribute('label')}'"
            )

        # Labeling neu konfigurieren und Layer aktualisieren
        self._setup_labeling(self.layer)

        # Layer explizit aktualisieren
        self.layer.triggerRepaint()
        if hasattr(self.iface, "layerTreeView"):
            self.iface.layerTreeView().refreshLayerSymbology(self.layer.id())
        self.canvas.refresh()

    def toggle_label_visibility(self, fid, show_label):
        """Schaltet die Label-Anzeige für ein Feature ein/aus"""
        if not self.layer:
            return

        idx = self.layer.fields().indexFromName("show_label")
        self.layer.startEditing()
        self.layer.changeAttributeValue(fid, idx, show_label)
        self.layer.commitChanges()

        # Feature-Daten für Debug ausgeben
        feature = self.layer.getFeature(fid)
        if feature.isValid():
            print(
                f"DEBUG: toggle_label_visibility - Feature {fid}: show_label={feature.attribute('show_label')}, label='{feature.attribute('label')}'"
            )

        # Labeling neu konfigurieren und Layer aktualisieren
        self._setup_labeling(self.layer)

        # Layer explizit aktualisieren
        self.layer.triggerRepaint()
        if hasattr(self.iface, "layerTreeView"):
            self.iface.layerTreeView().refreshLayerSymbology(self.layer.id())
        self.canvas.refresh()

    def toggle_white_background(self, fid, white_background):
        """Schaltet den weißen Hintergrund für ein Feature ein/aus"""
        if not self.layer:
            return

        idx = self.layer.fields().indexFromName("white_background")
        self.layer.startEditing()
        self.layer.changeAttributeValue(fid, idx, white_background)
        self.layer.commitChanges()

        # Renderer aktualisieren für Hintergrund-Anzeige
        self._update_renderer()

    def rotate_feature(self, fid, rotation):
        """Aktualisiert die Rotation eines Features"""
        if not self.layer:
            return

        # Rotation direkt im Renderer aktualisieren für flüssige Echtzeit-Updates
        # Dies ist viel schneller als den gesamten Renderer neu zu erstellen
        renderer = self.layer.renderer()
        if renderer and isinstance(renderer, QgsCategorizedSymbolRenderer):
            # Hole das Feature, um die unique_id zu bekommen
            feat = self.layer.getFeature(fid)
            if feat.isValid():
                unique_id = (
                    feat.attribute("unique_id")
                    if "unique_id" in [field.name() for field in self.layer.fields()]
                    else str(fid)
                )
                # Finde die Kategorie für dieses Feature
                for cat in renderer.categories():
                    if cat.value() == unique_id:
                        # Aktualisiere die Rotation im Symbol
                        symbol = cat.symbol()
                        if symbol:
                            # Durchlaufe alle Symbol-Layer und aktualisiere die Rotation
                            for i in range(symbol.symbolLayerCount()):
                                layer = symbol.symbolLayer(i)
                                if isinstance(layer, QgsSvgMarkerSymbolLayer):
                                    layer.setAngle(rotation)
                                elif isinstance(layer, QgsSimpleMarkerSymbolLayer):
                                    # Für Hintergrund-Layer keine Rotation ändern
                                    pass
                        break

        # Aktualisiere auch den Wert im Feature (für Persistenz)
        idx = self.layer.fields().indexFromName("rotation")
        if not self.layer.isEditable():
            self.layer.startEditing()
        self.layer.changeAttributeValue(fid, idx, rotation)
        # Committe nicht bei jedem Update, nur visuell aktualisieren
        # Das Commit erfolgt automatisch oder bei Bedarf

        # Canvas sofort aktualisieren für flüssige Anzeige
        self.layer.triggerRepaint()

    def export_portable_package(self, export_path):
        """Exportiert das Plugin als portables Paket.

        Args:
            export_path (str): Pfad, wo das portable Paket gespeichert werden soll
        """
        import shutil
        import zipfile

        try:
            # Erstelle Export-Verzeichnis
            os.makedirs(export_path, exist_ok=True)

            # Kopiere alle SVG-Dateien
            svg_source = os.path.join(self.plugin_dir, "svgs")
            svg_dest = os.path.join(export_path, "svgs")
            if os.path.exists(svg_source):
                shutil.copytree(svg_source, svg_dest, dirs_exist_ok=True)

            # Kopiere Icons
            icon_source = os.path.join(self.plugin_dir, "icons")
            icon_dest = os.path.join(export_path, "icons")
            if os.path.exists(icon_source):
                shutil.copytree(icon_source, icon_dest, dirs_exist_ok=True)

            # Kopiere Python-Dateien
            python_files = [
                "thwtoolboxplugin.py",
                "thwtoolboxplugin_dock.py",
                "identifytool.py",
                "dock_manager.py",
                "dragmaptool.py",
                "layer_manager.py",
                "mapcanvas_dropevent_filter.py",
            ]

            for py_file in python_files:
                source = os.path.join(self.plugin_dir, py_file)
                if os.path.exists(source):
                    shutil.copy2(source, export_path)

            # Kopiere __init__.py
            init_source = os.path.join(self.plugin_dir, "__init__.py")
            if os.path.exists(init_source):
                shutil.copy2(init_source, export_path)

            # Kopiere metadata.txt
            metadata_source = os.path.join(self.plugin_dir, "metadata.txt")
            if os.path.exists(metadata_source):
                shutil.copy2(metadata_source, export_path)

            # Kopiere GeoPackage mit allen Symbolen
            if self.layer and self.layer.providerType() == "ogr":
                source_gpkg = self.layer.source().split("|")[0]
                if os.path.exists(source_gpkg):
                    dest_gpkg = os.path.join(export_path, "taktische_zeichen.gpkg")
                    shutil.copy2(source_gpkg, dest_gpkg)

            # Erstelle README-Datei
            readme_content = """THW Toolbox Plugin - Portables Paket

Installation:
1. Entpacken Sie alle Dateien in einen Ordner
2. Kopieren Sie den gesamten Ordner in Ihr QGIS Plugin-Verzeichnis:
   - Windows: %APPDATA%/QGIS/QGIS3/profiles/default/python/plugins/
   - Linux: ~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/
   - macOS: ~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/
3. Aktivieren Sie das Plugin in QGIS über Plugins -> Verwalten und installieren

Verwendung:
- Das Plugin erstellt automatisch einen Layer "THW Toolbox Marker"
- Alle Symbole werden in der GeoPackage-Datei gespeichert
- Die Symbole sind vollständig portabel und funktionieren auch ohne das Plugin

Hinweis:
- Alle SVG-Symbole sind im 'svgs' Ordner enthalten
- Die GeoPackage-Datei enthält alle gesetzten Symbole mit Koordinaten
"""

            readme_path = os.path.join(export_path, "README.txt")
            with open(readme_path, "w", encoding="utf-8") as f:
                f.write(readme_content)

            # Erstelle ZIP-Archiv
            zip_path = export_path + ".zip"
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(export_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, export_path)
                        zipf.write(file_path, arcname)

            # Erfolgsmeldung
            self.iface.messageBar().pushMessage(
                "Erfolg",
                f"Portables Paket wurde erstellt: {zip_path}",
                level=0,  # Info level
            )

            return True

        except Exception as e:
            error_msg = f"Fehler beim Erstellen des portablen Pakets: {str(e)}"
            print(error_msg)
            self._show_error_alert(
                "Export-Fehler",
                "Konnte portables Paket nicht erstellen",
                f"Export-Pfad: {export_path}\nFehler: {str(e)}",
            )
            return False

    def _export_portable_package(self):
        """Öffnet einen Dialog zum Exportieren des portablen Pakets."""
        from qgis.PyQt.QtWidgets import QFileDialog

        # Standard-Export-Pfad
        default_path = os.path.join(os.path.expanduser("~"), "Desktop", "THW_Toolbox_Portable")

        # Dialog öffnen
        export_path = QFileDialog.getExistingDirectory(
            self.iface.mainWindow(), "Verzeichnis für portables Paket auswählen", default_path
        )

        if export_path:
            # Export durchführen
            success = self.export_portable_package(export_path)
            if success:
                # Öffne den Export-Ordner
                import platform
                import subprocess

                try:
                    if platform.system() == "Windows":
                        subprocess.run(["explorer", export_path])
                    elif platform.system() == "Darwin":  # macOS
                        subprocess.run(["open", export_path])
                    else:  # Linux
                        subprocess.run(["xdg-open", export_path])
                except:
                    pass  # Ignoriere Fehler beim Öffnen des Ordners
