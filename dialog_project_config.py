import os

from qgis.PyQt.QtCore import QObject, Qt
from qgis.PyQt.QtGui import QColor, QPixmap
from qgis.PyQt.QtWidgets import (
    QButtonGroup,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QRadioButton,
    QToolBox,
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage
)
from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsLayerTreeGroup,
    QgsMarkerSymbol,
    QgsPalLayerSettings,
    QgsProject,
    QgsProperty,
    QgsRasterLayer,
    QgsRectangle,
    QgsRuleBasedRenderer,
    QgsSvgMarkerSymbolLayer,
    QgsSymbolLayer,
    QgsTextBufferSettings,
    QgsTextFormat,
    QgsUnitTypes,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
)

class DialogProjectConfig():
    EPSGS = {
        "31* Nord": 25831,
        "32* Nord": 25832,
        "33* Nord": 25833,
    }
    EPSG_DEFAULT = "32* Nord"
    BASEMAPS = {
        "OpenStreetMap DE": {
            "layer_name": "OpenStreetMap DE",
            "url": "type=xyz&url=https://tile.openstreetmap.de/{z}/{x}/{y}.png&zmax=18&zmin=0",
            "note": "Empfohlene Hintergrundkarte für allgemeine Anwendungen.",
        },
        "OpenStreetMap": {
            "layer_name": "OpenStreetMap",
            "url": "type=xyz&url=https://tile.openstreetmap.org/{z}/{x}/{y}.png&zmax=18&zmin=0",
            "note": "Geeignet für allgemeine Anwendungen. Beschriftung nur in Landessprachen.",
        },
        "OpenTopoMap": {
            "layer_name": "OpenTopoMap",
            "url": "type=xyz&url=https://b.tile.opentopomap.org/{z}/{x}/{y}.png&zmax=17&zmin=0",
            "note": "Topographische Darstellung auf Basis von OSM. Darstellung orientiert sich an amtlichen Karten mit guter Lesbarkeit durch hohen Kontrast.",
        },
        "OSM Humanitarian Style": {
            "layer_name": "OSM Humanitarian",
            "url": "type=xyz&url=https://b.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png&zmax=18&zmin=0",
            "note": "Auf Darstellung von Points-of-Interest wie öffentliche Gebäude, Versorgungseinrichtungen etc. fokussierte Kartendarstellung. Leichte Farben erleichtern handschriftliche Notationen auf Ausdrücken.",
        },
        "Google Earth": {
            "layer_name": "Google Earth",
            "url": "type=xyz&url=https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}&zmax=18&zmin=0",
            "note": "Luftbilder ohne Eintragungen."
        },
    }
    STARTING_VIEW = {
        "xMin": -173467,
        "yMin": 5150154,
        "xMax": 1280371,
        "yMax": 6171205,
    }


    def __init__(self, toolbox_plugin: QObject):
        self.toolbox_plugin = toolbox_plugin
        self.epsg = 25832
        # This dict must be created here to be able to reference the function handles
        self.ADDITIONAL_LAYERS = {
            "UTMRef/MRGS Raster": {
                "creation_handle": self._setup_mrgs_grid,
                "note": "Fügt ein beschriftetes Raster zur Darstellung der UTM Ref / Military Grid Reference System (MGRS) Zonen hinzu.",
                "default_checked": True,
            },
            "THW Dienststellen": {
                "creation_handle": self._setup_thw_dienststellen,
                "note": "Trägt die Standort der THW Dienststellen in der Karte ein",
                "default_checked": True,
            },
            "OpenRailMap": {
                "creation_handle": self._setup_openrailmap,
                "note": "Fügt Informationen zu Bahnstrecken wie Name und Hektometermarkierungen hinzu.",
                "default_checked": False,
            }
        }

    def open_project_config_wizard(self):
        self.toolbox_plugin.action.setChecked(True)

        wizard = QWizard(self.toolbox_plugin.iface.mainWindow())
        wizard.setWindowTitle("THW Toolbox Startup")

        utm_zone_pg = self._utm_zone_page()
        base_map_pg = self._base_map_selection_page()
        add_layer_pg = self._additional_layer_selection_page()

        wizard.addPage(utm_zone_pg)
        wizard.addPage(base_map_pg)
        wizard.addPage(add_layer_pg)
        result = wizard.exec()
        print(f"Returned with result {result}")
        if result == QDialog.DialogCode.Accepted:
            crs = utm_zone_pg.zone_group.checkedButton().text()
            basemap_name = base_map_pg.map_group.checkedButton().text()
            selected_layers = [
                add_layer_pg.layers_list.item(i).text()
                for i in range(add_layer_pg.layers_list.count())
                if add_layer_pg.layers_list.item(i).checkState() == Qt.CheckState.Checked
            ]

            print(f"Completed Wizard with result CRS: {crs}, Basemap: {basemap_name}, Selected Layers: {selected_layers}")
            try:
                self.epsg = self._epsg_from_zone_string(crs)
                self._set_base_map(basemap_name)
                self._add_additional_layer(selected_layers)
                self._set_project_crs()
                self._zoom_to_germany()
                # Collapse all layers in the Layer view
                self.toolbox_plugin.iface.layerTreeView().collapseAll()
            except ValueError as e:
                msg_box = QMessageBox()
                msg_box.setIcon(QMessageBox.Icon.Critical)
                msg_box.setWindowTitle("Fehler beim Konfigurieren des Projektes")
                msg_box.setText("Es gab einen Fehler beim Konfigurieren des Projektes anhand der gewählten Einstellungen.")
                msg_box.setDetailedText(f"Fehler: {str(e)}")
                msg_box.exec()
                self.toolbox_plugin.action.setChecked(False)
            self.toolbox_plugin.iface.mapCanvas().refreshAllLayers()

    # ██████   █████   ██████  ███████      ██████  ███████ ███    ██
    # ██   ██ ██   ██ ██       ██          ██       ██      ████   ██
    # ██████  ███████ ██   ███ █████       ██   ███ █████   ██ ██  ██
    # ██      ██   ██ ██    ██ ██          ██    ██ ██      ██  ██ ██
    # ██      ██   ██  ██████  ███████      ██████  ███████ ██   ████

    def _utm_zone_page(self) -> QWizardPage:
        utm_zone_pg = QWizardPage()

        main_layout = self._setup_page_layout(
            utm_zone_pg,
            "Koordinatenreferenzsystem",
            "Bitte die UTM-Zone des relevanten Raumes anhand der Karte auswählen."
            )

        content_layout = QHBoxLayout()
        main_layout.addLayout(content_layout)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)

        info = QLabel("Koordinatenreferenzsystem")
        info.setWordWrap(True)
        left_layout.addWidget(info)

        utm_zone_pg.zone_group = QButtonGroup(utm_zone_pg)
        utm_zone_pg.zone_buttons = {}

        for label in self.EPSGS:
            btn = QRadioButton(label, utm_zone_pg)
            utm_zone_pg.zone_group.addButton(btn)
            left_layout.addWidget(btn)
            utm_zone_pg.zone_buttons[label] = btn
        default_btn = utm_zone_pg.zone_buttons[self.EPSG_DEFAULT]
        if default_btn is None:
            raise ValueError(f"Could not find default zone {self.EPSG_DEFAULT} in {utm_zone_pg.zone_buttons}")
        default_btn.setChecked(True)

        left_layout.addStretch(1)

        content_layout.addWidget(left_widget, 1)

        image_label = QLabel()
        image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image_label.setMinimumWidth(320)
        image_label.setStyleSheet("QLabel { background-color: white; }")
        image_label.setAutoFillBackground(True)

        img_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons", "utm_zone_grid.png")

        pixmap = QPixmap(img_path)
        if not pixmap.isNull():
            image_label.setPixmap(
                pixmap.scaledToWidth(360, Qt.TransformationMode.SmoothTransformation)
            )
        else:
            image_label.setText("Bild konnte nicht geladen werden.\n" + img_path)

        content_layout.addWidget(image_label, 1)

        self._setup_details_text(
            main_layout,
            "Die runde Erde muss auf eine flache Karte projiziert werden. Dafür werden unterschiedliche Systeme verwendet. Für die UTM-Projektion muss der passende Ost-West-Abschnitt gewählt werden, um die Fehler durch die Projektion niedrig zu halten."
            )

        return utm_zone_pg

    def _base_map_selection_page(self)->QWizardPage:
        base_map_pg = QWizardPage()
        main_layout = self._setup_page_layout(
            base_map_pg,
            "Hintergrundkarte",
            "Wähle die gewünschte Hintergrundkarte."
            )

        info = QLabel("Empfohlene Hintergrundkarte: OpenStreetmaps DE")
        info.setWordWrap(True)
        main_layout.addWidget(info)

        radio_row = QWidget()
        radio_layout = QVBoxLayout(radio_row)

        base_map_pg.map_group = QButtonGroup(base_map_pg)
        base_map_pg.map_buttons = {}

        for label in self.BASEMAPS:
            btn = QRadioButton(label, base_map_pg)
            base_map_pg.map_group.addButton(btn)
            radio_layout.addWidget(btn)
            base_map_pg.map_buttons[label] = btn

        first_label = next(iter(self.BASEMAPS))
        base_map_pg.map_buttons[first_label].setChecked(True)

        main_layout.addWidget(radio_row)

        details_string = "Es stehen mehrere Hintergrundkarten zur Auswahl. Es werden alle Karten als Verknüpfung hinzugefügt, aber nur die ausgewählte Karte ist aktiv. Später kann über die Layer-Ansicht die aktive Karte gewechselt werden.<br/>Das Kartenmaterial wird aus dem Internet abgerufen - eine Verbindung ist daher notwendig.<br/><br/>"
        for label, data in self.BASEMAPS.items():
            details_string += f"{label}: {data['note']}<br/><br/>"
        self._setup_details_text(
            main_layout,
            details_string
        )

        return base_map_pg

    def _additional_layer_selection_page(self)->QWizardPage:
        add_layer_pg = QWizardPage()
        main_layout = self._setup_page_layout(
            add_layer_pg,
            "Zusätzliche Ansichtsebenen",
            "Wähle die zusätzlichen Karteninhalte aus."
        )

        add_layer_pg.layers_list = QListWidget()

        for label, data in self.ADDITIONAL_LAYERS.items():
            item = QListWidgetItem(label)
            if data["default_checked"]:
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)
            add_layer_pg.layers_list.addItem(item)
        main_layout.addWidget(add_layer_pg.layers_list)

        details_string = "Über die Hintergrundkarte können weitere Informationen gelegt werden. Es werden alle Einträge als Verknüpfung hinzugefügt, aber nur die ausgewählten Lagen sind aktiv. Später können über die Layer-Ansicht die aktiven Lagen geändert werden.<br/>Das Kartenmaterial wird auch hier teilweise aus dem Internet abgerufen - eine Verbindung ist daher notwendig.<br/><br/>"
        for label, data in self.ADDITIONAL_LAYERS.items():
            details_string += f"{label}: {data['note']}<br/><br/>"
        self._setup_details_text(
            main_layout,
            details_string
        )

        return add_layer_pg

    def _setup_page_layout(self, page: QWizardPage, title: str, top_label: str) -> QVBoxLayout:
        page.setTitle(title)
        layout = QVBoxLayout(page)

        top_text = QLabel(top_label)
        top_text.setWordWrap(True)
        layout.addWidget(top_text)

        return layout

    def _setup_details_text(self, layout: QVBoxLayout, details: str):
        details_box = QToolBox()
        details_page = QWidget()
        details_layout = QVBoxLayout(details_page)

        details_text = QLabel(details)
        details_text.setWordWrap(True)
        details_layout.addWidget(details_text)
        details_layout.addStretch(1)

        details_box.addItem(details_page, "Details")
        layout.addWidget(details_box)

    #  █████  ██████  ██████  ██      ██    ██      ██████  ██████  ███    ██ ███████ ██  ██████
    # ██   ██ ██   ██ ██   ██ ██       ██  ██      ██      ██    ██ ████   ██ ██      ██ ██
    # ███████ ██████  ██████  ██        ████       ██      ██    ██ ██ ██  ██ █████   ██ ██   ███
    # ██   ██ ██      ██      ██         ██        ██      ██    ██ ██  ██ ██ ██      ██ ██    ██
    # ██   ██ ██      ██      ███████    ██         ██████  ██████  ██   ████ ██      ██  ██████

    def _set_base_map(self, basemap_name: str):
        if basemap_name not in self.BASEMAPS:
            raise ValueError(f"Unsupported basemap: {basemap_name}")

        project = QgsProject.instance()
        root = project.layerTreeRoot()
        group = root.findGroup("Hintergrundkarte")
        if group is None:
            group = root.addGroup("Hintergrundkarte")
        layers = {}

        for name, config in self.BASEMAPS.items():
            layer = QgsRasterLayer(config["url"], config["layer_name"], "wms")
            if not layer.isValid():
                raise ValueError(f"{name} base layer invalid: {layer.error().summary()}")
            project.addMapLayer(layer, False)
            group.addLayer(layer)
            layers[name] = layer

        for name, layer in layers.items():
            root.findLayer(layer.id()).setItemVisibilityChecked(name == basemap_name)

        project = QgsProject.instance()
        project.addMapLayer(layer, addToLegend=True)
        return layer

    def _set_project_crs(self):
        crs = QgsCoordinateReferenceSystem.fromEpsgId(self.epsg)
        if not crs.isValid():
            raise ValueError(f"Invalid CRS for EPSG:{self.epsg}")

        QgsProject.instance().setCrs(crs)

    def _epsg_from_zone_string(self, zone: str) -> int:
        epsg = self.EPSGS.get(zone)
        if epsg is None:
            raise ValueError(f"Unsupported zone: {zone}")
        return epsg

    def _zoom_to_germany(self):
        print("DEBUG: Zoom to Germany")
        # Magic numbers taken from QGIS when having Germany in full view with 32U
        germany_extent = QgsRectangle(
            self.STARTING_VIEW["xMin"],
            self.STARTING_VIEW["yMin"],
            self.STARTING_VIEW["xMax"],
            self.STARTING_VIEW["yMax"]
            )
        self.toolbox_plugin.canvas.setExtent(germany_extent)

    #  █████  ██████  ██████         ██       █████  ██    ██ ███████ ██████
    # ██   ██ ██   ██ ██   ██        ██      ██   ██  ██  ██  ██      ██   ██
    # ███████ ██   ██ ██   ██        ██      ███████   ████   █████   ██████
    # ██   ██ ██   ██ ██   ██        ██      ██   ██    ██    ██      ██   ██ 
    # ██   ██ ██████  ██████  ██     ███████ ██   ██    ██    ███████ ██   ██

    def _add_additional_layer(self, selected_layers:[str]):
        project = QgsProject.instance()
        root = project.layerTreeRoot()
        group = root.findGroup("Zusatz-Layer")
        if group is None:
            base_layer_group = root.findGroup("Hintergrundkarte")
            if base_layer_group is None:
                group = root.addGroup("Zusatz-Layer")
            else:
                group = root.insertGroup(root.children().index(base_layer_group), "Zusatz-Layer")

        for label, data in self.ADDITIONAL_LAYERS.items():
            active = label in selected_layers
            print(f"DEBUG: {label} has {active}")
            data["creation_handle"](project, group, label, active)

    def _setup_mrgs_grid(self, project: QgsProject, group: QgsLayerTreeGroup, label: str, active: bool):
        # Use the fitting CRS to fetch the grid
        url = f"InvertAxisOrientation=1&crs=EPSG%3A{self.epsg}&dpiMode=7&featureCount=10&format=image%2Fpng&layers=mtkn%3Amgrsgrid&styles&tilePixelRatio=0&url=https%3A%2F%2Fgeodata.meier-tkn.de%2Fgeoserver%2Fows%3Fversion%3D1.3.0"
        layer = QgsRasterLayer(url, label, "wms")

        if not layer.isValid():
            raise ValueError(f"UTMRef Raster layer invalid: {layer.error().summary()}")
        # Add to project (goes to top by default)
        project.addMapLayer(layer, False)
        group.addLayer(layer)
        project.layerTreeRoot().findLayer(layer.id()).setItemVisibilityChecked(active)

    def _setup_thw_dienststellen(self, project: QgsProject, group: QgsLayerTreeGroup, label: str, active: bool):
        plugin_dir = os.path.dirname(os.path.abspath(__file__))
        dst_json = os.path.join(plugin_dir, "data", "ovs.json")

        svg_map = [
            ("Ortsverband", os.path.join(plugin_dir, "svgs", "THW_Gebäude", "OV_Unterkunft.svg")),
            ("Regionalstelle", os.path.join(plugin_dir, "svgs", "THW_Gebäude", "Regionalstelle.svg")),
            ("Landesverband", os.path.join(plugin_dir, "svgs", "THW_Gebäude", "Landesverband.svg")),
            ("Ausbildungszentrum", os.path.join(plugin_dir, "svgs", "THW_Gebäude", "Ausbildungszentrum.svg")),
            ("Leitung", os.path.join(plugin_dir, "svgs", "THW_Gebäude", "Leitung.svg")),
        ]

        layer = QgsVectorLayer(str(dst_json), label, "ogr")
        if not layer.isValid():
            raise ValueError(f"{label} layer invalid: {layer.error().summary()}")

        root_rule = QgsRuleBasedRenderer.Rule(None)

        for key, svg_path in svg_map:
            symbol = QgsMarkerSymbol.createSimple({})
            svg_layer = QgsSvgMarkerSymbolLayer(svg_path)

            expr_size = (
                "CASE "
                "WHEN @zoom_level >= 10 AND @zoom_level <= 16 THEN scale_linear(@zoom_level, 10, 16, 300, 20) "
                "WHEN @zoom_level > 16 THEN 20 "
                "ELSE 300 "
                "END"
            )
            svg_layer.setDataDefinedProperty(
                QgsSymbolLayer.Property.Size,
                QgsProperty.fromExpression(expr_size)
            )
            svg_layer.setSizeUnit(QgsUnitTypes.RenderUnit.RenderMapUnits)

            symbol.changeSymbolLayer(0, svg_layer)

            rule = QgsRuleBasedRenderer.Rule(
                symbol=symbol,
                filterExp=f"""\"title\" ILIKE '%{key}%'""",
                label=key
            )
            root_rule.appendChild(rule)

        layer.setRenderer(QgsRuleBasedRenderer(root_rule))

        # Labels
        label_settings = QgsPalLayerSettings()
        text_format = QgsTextFormat()
        text_format.setSize(8)
        text_format.setSizeUnit(Qgis.RenderUnit.RenderMapUnits)
        text_format.setColor(QColor("black"))
        font = text_format.font()
        font.setBold(True)
        text_format.setFont(font)

        buffer_settings = QgsTextBufferSettings()
        buffer_settings.setEnabled(True)
        buffer_settings.setSize(1)
        buffer_settings.setSizeUnit(Qgis.RenderUnit.RenderMapUnits)
        buffer_settings.setColor(QColor("white"))
        text_format.setBuffer(buffer_settings)

        label_settings.setFormat(text_format)
        label_settings.fieldName = """replace("title",array('Ortsverband ','Regionalstelle ','Landesverband ','Ausbildungszentrum '),'')"""
        label_settings.isExpression = True

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
                label_settings.offsetUnits = Qgis.RenderUnit.RenderMapUnits
            size_property = QgsProperty.fromExpression("array(0,5)")
            label_settings.dataDefinedProperties().setProperty(QgsPalLayerSettings.Property.OffsetXY, size_property)
        except Exception as e:
            print(f"DEBUG: Fehler bei der Festsetzung der Position: {e}")


        label_settings.dataDefinedProperties().setProperty(QgsPalLayerSettings.Property.ScaleVisibility, True)
        label_settings.dataDefinedProperties().setProperty(QgsPalLayerSettings.Property.MinimumScale, 5000)
        label_settings.dataDefinedProperties().setProperty(QgsPalLayerSettings.Property.MaximumScale, 0)

        layer.setLabelsEnabled(True)
        layer.setLabeling(QgsVectorLayerSimpleLabeling(label_settings))

        project.addMapLayer(layer, False)
        group.addLayer(layer)
        project.layerTreeRoot().findLayer(layer.id()).setItemVisibilityChecked(active)

    def _setup_openrailmap(self, project: QgsProject, group: QgsLayerTreeGroup, label: str, active: bool):
        url = "type=xyz&url=https://a.tiles.openrailwaymap.org/standard/{z}/{x}/{y}.png&zmax=18&zmin=0"
        layer = QgsRasterLayer(url, label, "wms")
        if not layer.isValid():
            raise ValueError(f"OpenRailMap layer invalid: {layer.error().summary()}")
        project.addMapLayer(layer, False)
        group.addLayer(layer)
        project.layerTreeRoot().findLayer(layer.id()).setItemVisibilityChecked(active)
