import os
import shutil
import time
import uuid
from collections.abc import Callable

from qgis.core import QgsFeature, QgsProject, QgsVectorFileWriter, QgsVectorLayer

from ..logging_utils import get_logger
from .fields import build_qgs_fields

logger = get_logger(__name__)

# Display name in the QGIS layer panel
LAYER_DISPLAY_NAME = "THW Toolbox Marker"
# Layer name inside the GeoPackage
GPKG_LAYER_NAME = "taktische_zeichen"
# Suffix appended to the project filename for the per-project GeoPackage
GPKG_SUFFIX = "_taktischezeichen"


class LayerManager:
    """Owns the THW Toolbox feature layer (GeoPackage-backed).

    Responsibilities:
    - Create or load the layer when the plugin activates, including
      schema migration for older GeoPackages that lack newer fields.
    - On project save, move the GeoPackage next to the project file so
      the layer travels with the project.

    The plugin keeps responsibility for renderer/labeling/tool wiring
    after a layer change — this manager handles layer lifecycle only.
    """

    def __init__(
        self,
        canvas,
        plugin_dir: str,
        settings,
        error_alert: Callable[[str, str, str | None], None],
        check_map_available: Callable[[], bool],
    ):
        self.canvas = canvas
        self.plugin_dir = plugin_dir
        self.settings = settings
        self._error_alert = error_alert
        self._check_map_available = check_map_available
        self.layer: QgsVectorLayer | None = None

    # ------------------------------------------------------------------
    # Layer creation / loading
    # ------------------------------------------------------------------

    def init_layer(self) -> QgsVectorLayer | None:
        """Create or load the layer; store and return it. None on failure."""
        logger.debug("init_layer wird aufgerufen")

        if not self._check_map_available():
            logger.debug("Keine Karte vorhanden, kann Layer nicht initialisieren")
            return None

        proj = QgsProject.instance()
        pfile = proj.fileName()
        logger.debug("Projektdatei: %s", pfile)

        existing_layers = proj.mapLayersByName(LAYER_DISPLAY_NAME)
        logger.debug("Bestehende Layer gefunden: %d", len(existing_layers))
        if existing_layers:
            self.layer = existing_layers[0]
            logger.debug("Verwende bestehenden Layer: %s", self.layer)
            return self.layer

        crs = self.canvas.mapSettings().destinationCrs().authid()
        gpkg = self._gpkg_path_for_project(proj, pfile)

        # Create or load
        if os.path.exists(gpkg):
            uri = f"{gpkg}|layername={GPKG_LAYER_NAME}"
            lyr = QgsVectorLayer(uri, LAYER_DISPLAY_NAME, "ogr")

            # Migrate older layers that lack newer fields
            existing_fields = [field.name() for field in lyr.fields()]
            if "scale_with_map" not in existing_fields or "svg_content" not in existing_fields:
                self._update_layer_fields(lyr, gpkg, GPKG_LAYER_NAME)
                lyr = QgsVectorLayer(uri, LAYER_DISPLAY_NAME, "ogr")
        else:
            lyr = self._create_new_layer(gpkg, GPKG_LAYER_NAME, crs)
            if lyr is None:
                return None

        self.layer = lyr
        logger.debug("Neuer Layer gesetzt: %s", self.layer)
        proj.addMapLayer(lyr)
        logger.debug("Layer zum Projekt hinzugefügt")
        return self.layer

    def _gpkg_path_for_project(self, proj: QgsProject, pfile: str) -> str:
        """Return the GeoPackage path: next to the project file, or in tmp/."""
        if pfile:
            return os.path.splitext(pfile)[0] + GPKG_SUFFIX + ".gpkg"

        # Project not yet saved — write into the plugin's tmp/ with a unique name
        tmp_dir = os.path.join(self.plugin_dir, "tmp")
        os.makedirs(tmp_dir, exist_ok=True)

        proj_id = proj.title() or "unnamed"
        safe_name = "".join(c for c in proj_id if c.isalnum() or c in (" ", "-", "_")).rstrip() or "project"
        safe_name = f"{safe_name}_{int(time.time())}"
        path = os.path.join(tmp_dir, f"{safe_name}{GPKG_SUFFIX}.gpkg")
        logger.debug("Erstelle eindeutige Datei für ungespeichertes Projekt: %s", path)
        return path

    def _create_new_layer(self, gpkg: str, lname: str, crs: str) -> QgsVectorLayer | None:
        """Create a new GeoPackage with the full schema and return its loaded layer."""
        try:
            os.makedirs(os.path.dirname(gpkg), exist_ok=True)

            mem = QgsVectorLayer(f"Point?crs={crs}", "temp", "memory")
            dp = mem.dataProvider()
            dp.addAttributes(build_qgs_fields())
            mem.updateFields()

            opts = QgsVectorFileWriter.SaveVectorOptions()
            opts.driverName = "GPKG"
            opts.layerName = lname
            result = QgsVectorFileWriter.writeAsVectorFormatV2(
                mem, gpkg, QgsProject.instance().transformContext(), opts
            )

            if result[0] != QgsVectorFileWriter.WriterError.NoError:
                self._error_alert(
                    "Layer-Erstellungsfehler",
                    f"Konnte neuen Layer nicht erstellen: {result[1]}",
                    f"Pfad: {gpkg}\nFehler: {result[1]}",
                )
                return None

            uri = f"{gpkg}|layername={lname}"
            return QgsVectorLayer(uri, LAYER_DISPLAY_NAME, "ogr")

        except Exception as e:
            logger.exception("Fehler beim Erstellen des neuen Layers")
            self._error_alert(
                "Layer-Erstellungsfehler", "Konnte neuen Layer nicht erstellen", f"Pfad: {gpkg}\nFehler: {e}"
            )
            return None

    def _update_layer_fields(self, old_layer: QgsVectorLayer, gpkg: str, lname: str) -> None:
        """Migrate features from `old_layer` into a freshly-schema'd GeoPackage at `gpkg`.

        Loads existing features, copies their attributes (defaulting where
        a field didn't exist before), writes to a `.temp` file, then swaps
        it over the original. The map-available check is repeated here
        because this runs at layer-load time and needs a CRS.
        """
        try:
            if not self._check_map_available():
                self._error_alert(
                    "Keine Karte vorhanden",
                    "Bitte ziehen Sie zuerst eine Karte in das Projekt ein.",
                    "Das Plugin benötigt eine Karte mit einem Koordinatensystem (CRS), um den Layer zu aktualisieren.\n\n"
                    "So fügen Sie eine Karte hinzu:\n"
                    "1. Gehen Sie zu 'Browser' im QGIS-Fenster\n"
                    "2. Ziehen Sie eine Karte (z.B. OpenStreetMap) in das Projekt\n"
                    "3. Versuchen Sie es erneut",
                )
                return

            if old_layer.isEditable():
                try:
                    old_layer.commitChanges()
                except Exception:
                    try:
                        old_layer.rollBack()
                    except Exception:
                        pass

            crs = self.canvas.mapSettings().destinationCrs().authid()
            mem = QgsVectorLayer(f"Point?crs={crs}", "temp", "memory")
            dp = mem.dataProvider()
            dp.addAttributes(build_qgs_fields())
            mem.updateFields()

            existing_fields = [field.name() for field in old_layer.fields()]
            for feat in old_layer.getFeatures():
                new_feat = QgsFeature(mem.fields())
                new_feat.setGeometry(feat.geometry())
                new_feat.setAttribute("name", feat.attribute("name"))
                new_feat.setAttribute("svg_path", feat.attribute("svg_path"))
                new_feat.setAttribute(
                    "svg_content", feat.attribute("svg_content") if "svg_content" in existing_fields else ""
                )
                new_feat.setAttribute("size", feat.attribute("size"))
                new_feat.setAttribute(
                    "scale_with_map",
                    feat.attribute("scale_with_map") if "scale_with_map" in existing_fields else False,
                )
                new_feat.setAttribute(
                    "unique_id",
                    feat.attribute("unique_id") if "unique_id" in existing_fields else str(uuid.uuid4()),
                )

                # Default label from filename if missing
                if "label" in existing_fields and feat.attribute("label"):
                    new_feat.setAttribute("label", feat.attribute("label"))
                else:
                    svg_name = feat.attribute("name") or os.path.basename(feat.attribute("svg_path"))
                    new_feat.setAttribute("label", os.path.splitext(svg_name)[0].replace("_", " "))

                new_feat.setAttribute(
                    "show_label", feat.attribute("show_label") if "show_label" in existing_fields else False
                )
                new_feat.setAttribute(
                    "white_background",
                    feat.attribute("white_background") if "white_background" in existing_fields else False,
                )
                new_feat.setAttribute(
                    "rotation", feat.attribute("rotation") if "rotation" in existing_fields else 0.0
                )
                mem.dataProvider().addFeature(new_feat)

            # Remove old layer from project so QGIS releases the file lock
            QgsProject.instance().removeMapLayer(old_layer.id())
            time.sleep(0.1)

            # Write to .temp first, then atomically swap
            temp_gpkg = gpkg + ".temp"
            if os.path.exists(temp_gpkg):
                try:
                    os.remove(temp_gpkg)
                except Exception:
                    pass

            opts = QgsVectorFileWriter.SaveVectorOptions()
            opts.driverName = "GPKG"
            opts.layerName = lname
            opts.actionOnExistingFile = QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteFile

            result = QgsVectorFileWriter.writeAsVectorFormatV2(
                mem, temp_gpkg, QgsProject.instance().transformContext(), opts
            )
            if result[0] != QgsVectorFileWriter.WriterError.NoError:
                self._error_alert(
                    "Layer-Aktualisierungsfehler",
                    f"Konnte Layer-Felder nicht aktualisieren: {result[1]}",
                    f"Pfad: {gpkg}\nFehler: {result[1]}",
                )
                return

            time.sleep(0.1)
            self._swap_temp_into_place(temp_gpkg, gpkg)

        except Exception as e:
            logger.exception("Fehler beim Aktualisieren der Layer-Felder")
            self._error_alert(
                "Layer-Aktualisierungsfehler",
                "Konnte Layer-Felder nicht aktualisieren",
                f"Pfad: {gpkg}\nFehler: {e}",
            )

    def _swap_temp_into_place(self, temp_gpkg: str, gpkg: str) -> None:
        """Move temp_gpkg → gpkg, falling back to copy+delete if move fails."""
        try:
            if os.path.exists(gpkg):
                try:
                    os.remove(gpkg)
                    time.sleep(0.1)
                except Exception as e:
                    logger.warning("Konnte ursprüngliche Datei nicht löschen: %s", e)
            shutil.move(temp_gpkg, gpkg)
        except Exception as e:
            try:
                shutil.copy2(temp_gpkg, gpkg)
                try:
                    os.remove(temp_gpkg)
                except Exception:
                    pass
            except Exception as e2:
                self._error_alert(
                    "Layer-Aktualisierungsfehler",
                    f"Konnte aktualisierte Datei nicht speichern: {e2}",
                    f"Pfad: {gpkg}\nFehler: {e2}",
                )
                return
            logger.warning("Temporäre Datei konnte nicht verschoben werden: %s", e)

    # ------------------------------------------------------------------
    # Project-save handling
    # ------------------------------------------------------------------

    def on_project_save(self) -> QgsVectorLayer | None:
        """Move the GeoPackage next to the project file. Returns the new layer (or None)."""
        logger.debug("Projekt wird gespeichert, verschiebe Layer-Datei zum Projektpfad")
        if not self.layer:
            return None

        if self.layer.providerType() != "ogr":
            logger.debug("Layer ist keine GeoPackage, nichts zu tun")
            return None

        proj = QgsProject.instance()
        pfile = proj.fileName()
        if not pfile:
            logger.debug("Kein Projektpfad verfügbar")
            return None

        current_source = self.layer.source().split("|")[0]
        if not os.path.exists(current_source):
            logger.debug("Aktuelle Layer-Datei existiert nicht: %s", current_source)
            return None

        new_gpkg = os.path.splitext(pfile)[0] + GPKG_SUFFIX + ".gpkg"
        if os.path.abspath(current_source) == os.path.abspath(new_gpkg):
            logger.debug("Datei ist bereits am richtigen Ort")
            return None

        try:
            target_dir = os.path.dirname(new_gpkg)
            os.makedirs(target_dir, exist_ok=True)
            if not os.access(target_dir, os.W_OK):
                raise Exception(f"Keine Schreibrechte im Zielverzeichnis: {target_dir}")

            try:
                if self.layer.isEditable():
                    logger.debug("Layer ist im Bearbeitungsmodus - committe Änderungen vor Export")
                    self.layer.commitChanges()
            except Exception as e:
                logger.debug("Hinweis beim Committen vor Export: %s", e)

            if os.path.exists(new_gpkg):
                try:
                    os.remove(new_gpkg)
                except Exception as e:
                    logger.warning("Konnte Ziel-Datei nicht löschen: %s", e)

            logger.debug("Kopiere Layer-Daten von %s nach %s", current_source, new_gpkg)
            save_options = QgsVectorFileWriter.SaveVectorOptions()
            save_options.driverName = "GPKG"
            save_options.layerName = GPKG_LAYER_NAME
            save_options.actionOnExistingFile = QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteFile

            result = QgsVectorFileWriter.writeAsVectorFormatV3(
                self.layer, new_gpkg, proj.transformContext(), save_options
            )

            if result[0] != QgsVectorFileWriter.WriterError.NoError:
                logger.warning("Writer-Export fehlgeschlagen: %s - versuche Datei-Kopie als Fallback", result[1])
                shutil.copy2(current_source, new_gpkg)

            logger.debug("Layer-Daten erfolgreich exportiert/kopiert")

            # Swap project's layer reference
            QgsProject.instance().removeMapLayer(self.layer.id())
            uri = f"{new_gpkg}|layername={GPKG_LAYER_NAME}"
            new_layer = QgsVectorLayer(uri, LAYER_DISPLAY_NAME, "ogr")
            if not new_layer.isValid():
                raise Exception(f"Neuer Layer ist nicht gültig: {new_layer.error().message()}")

            QgsProject.instance().addMapLayer(new_layer)
            self.layer = new_layer

            # Try to remove the old file (best effort — may still be locked)
            try:
                time.sleep(0.5)
                os.remove(current_source)
                logger.debug("Alte Datei gelöscht: %s", current_source)
            except Exception as e:
                logger.warning("Konnte alte Datei nicht löschen (wird beim nächsten Start bereinigt): %s", e)

            logger.debug("Layer erfolgreich zum Projektpfad verschoben")
            return new_layer

        except Exception as e:
            logger.exception("Fehler beim Verschieben der Layer-Datei")
            self._error_alert(
                "Fehler beim Projekt-Speichern",
                "Konnte Layer-Datei nicht zum Projektpfad verschieben",
                f"Von: {current_source}\nNach: {new_gpkg}\nFehler: {e}\n\n"
                "Hinweis: Die Layer-Daten bleiben im ursprünglichen Verzeichnis erhalten.",
            )
            return None
