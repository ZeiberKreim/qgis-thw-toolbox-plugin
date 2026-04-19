import os
import time

from qgis.core import (
    Qgis,
    QgsMapLayer,
    QgsProject,
)
from qgis.PyQt.QtCore import QSize, Qt
from qgis.PyQt.QtGui import QIcon, QKeySequence
from qgis.PyQt.QtWidgets import QAction, QDockWidget, QMessageBox
from qgis.utils import iface

from .export.portable_export import PortableExporter
from .layer.feature_ops import FeatureOperations
from .layer.labeling import apply_labeling
from .layer.layer_manager import LayerManager
from .layer.renderer import apply_renderer
from .logging_utils import get_logger
from .paths import plugin_root
from .settings import THWToolboxSettings
from .tools.canvas_drop_filter import CanvasDropFilter
from .tools.identify_tool import IdentifyTool
from .tools.move_tool import MoveTool
from .ui.config_dialog import ConfigDialog
from .ui.nominatim_search_dialog import NominatimSearchDialog
from .ui.svg_dock import SvgDock
from .util.temp_files import cleanup_temp_files

logger = get_logger(__name__)


class THWToolboxPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.plugin_dir = plugin_root()
        self.layer = None
        self.layer_manager = None
        self.feature_ops = None
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
            logger.warning("Fehler bei _check_map_available: %s", e)
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

        # Settings-Aktion in Toolbar neben dem Toolbox-Icon
        settings_icon = QIcon(os.path.join(self.plugin_dir, "icons", "settings.svg"))
        self.settings_action = QAction(settings_icon, "THW Toolbox Einstellungen", self.iface.mainWindow())
        self.settings_action.triggered.connect(self._open_config_dialog)
        self.iface.addToolBarIcon(self.settings_action)
        self.iface.addPluginToMenu("THW Toolbox", self.settings_action)

        # Adress-Suche (Nominatim)
        search_icon = QIcon(os.path.join(self.plugin_dir, "icons", "search.svg"))
        self.search_action = QAction(search_icon, "Adresse suchen", self.iface.mainWindow())
        self.search_action.setShortcut(QKeySequence("Alt+S"))
        self.search_action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        self.search_action.triggered.connect(self._open_search_dialog)
        self.iface.addToolBarIcon(self.search_action)
        self.iface.addPluginToMenu("THW Toolbox", self.search_action)

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
        if self.settings_action:
            self.iface.removeToolBarIcon(self.settings_action)
            self.iface.removePluginMenu("THW Toolbox", self.settings_action)
        if self.search_action:
            self.iface.removeToolBarIcon(self.search_action)
            self.iface.removePluginMenu("THW Toolbox", self.search_action)
        if self.export_action:
            self.iface.removePluginMenu("THW Toolbox", self.export_action)

        # Trenne Projekt-Events
        QgsProject.instance().writeProject.disconnect(self._on_project_save)

        # Räume temporäre Dateien auf
        cleanup_temp_files(self.plugin_dir)

    def activate(self):
        logger.debug("Plugin wird aktiviert")

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
        cleanup_temp_files(self.plugin_dir)

        if self.layer_manager is None:
            self.layer_manager = LayerManager(
                self.canvas,
                self.plugin_dir,
                self.settings,
                self._show_error_alert,
                self._check_map_available,
            )
        self.layer = self.layer_manager.init_layer()
        if self.feature_ops is None:
            self.feature_ops = FeatureOperations(
                layer_provider=lambda: self.layer,
                settings=self.settings,
                plugin_dir=self.plugin_dir,
                canvas=self.canvas,
                error_alert=self._show_error_alert,
                on_renderer_dirty=self._update_renderer,
                on_labeling_dirty=self._on_labeling_dirty,
            )
        if self.layer:
            self._init_renderer(self.layer)
        logger.debug("Layer initialisiert: %s", self.layer)

        # Prüfe erneut, ob der Layer erfolgreich initialisiert wurde
        if not self.layer:
            # Layer konnte nicht initialisiert werden (z.B. wegen fehlender Karte)
            if self.action:
                self.action.setChecked(False)
            return

        self._init_dock()
        # Drag & Drop
        if not self.drop_filter:
            logger.debug("Erstelle CanvasDropFilter")
            df = CanvasDropFilter(self.canvas, self._place_feature)
            self.drop_filter = df
            self.canvas.viewport().installEventFilter(df)
            self.canvas.setAcceptDrops(True)
            logger.debug("CanvasDropFilter installiert")
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
        logger.debug("Plugin wird deaktiviert")

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

    def _init_renderer(self, layer):
        """Wendet Renderer + Labeling auf den Layer an."""
        if not layer:
            return
        apply_renderer(layer, self.plugin_dir)
        apply_labeling(layer, self.settings)

    def _setup_labeling(self, layer):
        """Wendet Labeling auf den Layer an."""
        apply_labeling(layer, self.settings)

    def _update_renderer(self):
        """Aktualisiert den Renderer mit allen Features."""
        logger.debug("_update_renderer aufgerufen")
        if not self.layer:
            logger.debug("self.layer ist None, beende _update_renderer")
            return

        logger.debug("Rufe _init_renderer auf")
        self._init_renderer(self.layer)

        # Labeling auch aktualisieren
        self._setup_labeling(self.layer)

    def _on_project_save(self):
        """Speichert Settings und delegiert das Verschieben des Layers an den LayerManager."""
        if not self.layer or not self.layer_manager:
            return
        self.settings.save_settings(QgsProject.instance())
        new_layer = self.layer_manager.on_project_save()
        if new_layer:
            self.layer = new_layer
            self._update_tool_references()
            self._init_renderer(new_layer)

    def _update_tool_references(self):
        """Aktualisiert alle Tool-Referenzen auf den aktuellen Layer."""
        if hasattr(self, "ident_tool") and self.ident_tool:
            self.ident_tool.layer = self.layer
        if hasattr(self, "move_tool") and self.move_tool:
            self.move_tool.layer = self.layer

    def _place_feature(self, svg_path, point):
        """SVG-Drop-Callback: Feature platzieren und im Dock auswählen."""
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
        if not self.feature_ops:
            return

        new_feature = self.feature_ops.place_feature(svg_path, point)
        if not new_feature:
            return

        # Feature im Dock auswählen + Move-Modus aktivieren
        if self.ident_tool and hasattr(self.ident_tool, "feature_dock"):
            self.ident_tool.feature_dock.show_feature(new_feature, self)
        if self.move_tool:
            self.move_tool.moving_feature = new_feature
            self.move_tool.set_move_mode(True)
            self.canvas.setCursor(Qt.CursorShape.ClosedHandCursor)

    # ------------------------------------------------------------------
    # Public callbacks (called from FeatureDock with legacy method names)
    # ------------------------------------------------------------------

    def delete_feature(self, fid):
        if not self.feature_ops or not self.feature_ops.delete(fid):
            return
        # Dock-Tree und Layer-Panel nach Delete refreshen
        if hasattr(self, "svg_dock_widget"):
            self.svg_dock_widget.treeWidget.clear()
            self.svg_dock_widget.populate_root_folders()
        if hasattr(self.iface, "layerTreeView") and self.layer:
            self.iface.layerTreeView().refreshLayerSymbology(self.layer.id())
        self.canvas.refresh()
        self.canvas.update()

    def resize_feature(self, fid, size):
        self.feature_ops and self.feature_ops.resize(fid, size)

    def toggle_scale(self, fid, value):
        self.feature_ops and self.feature_ops.toggle_scale(fid, value)

    def toggle_white_background(self, fid, value):
        self.feature_ops and self.feature_ops.toggle_white_background(fid, value)

    def rotate_feature(self, fid, degrees):
        self.feature_ops and self.feature_ops.rotate(fid, degrees)

    def update_feature_label(self, fid, text):
        self.feature_ops and self.feature_ops.set_label(fid, text)

    def toggle_label_visibility(self, fid, value):
        self.feature_ops and self.feature_ops.toggle_label(fid, value)

    def update_origin(self, fid, origin_x, origin_y):
        self.feature_ops and self.feature_ops.update_origin(fid, origin_x, origin_y)

    def _on_labeling_dirty(self):
        """FeatureOperations callback after a label-affecting attribute change."""
        if not self.layer:
            return
        apply_labeling(self.layer, self.settings)
        self.layer.triggerRepaint()
        if hasattr(self.iface, "layerTreeView"):
            self.iface.layerTreeView().refreshLayerSymbology(self.layer.id())
        self.canvas.refresh()

    def _open_search_dialog(self):
        NominatimSearchDialog(self.canvas, self.iface.mainWindow()).exec()

    def _open_config_dialog(self):
        if ConfigDialog(self.settings, self.iface.mainWindow()).exec_and_apply():
            self.settings.save_settings(QgsProject.instance())
            if self.layer:
                self._init_renderer(self.layer)

    def _export_portable_package(self):
        """Menüpunkt-Handler: Dialog öffnen und Export durchführen."""
        PortableExporter(
            self.plugin_dir,
            get_layer=lambda: self.layer,
            on_success=lambda zip_path: self.iface.messageBar().pushMessage(
                "Erfolg", f"Portables Paket wurde erstellt: {zip_path}", Qgis.MessageLevel.Info
            ),
            on_error=self._show_error_alert,
        ).prompt_and_export(self.iface.mainWindow())
