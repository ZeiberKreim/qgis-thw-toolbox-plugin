"""Setup-Dialog: Projekt-Status prüfen + Basemaps installieren."""

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QFont
from qgis.PyQt.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..tools.basemap_setup import (
    BASEMAPS,
    TARGET_CRS,
    TARGET_CRS_LABEL,
    Basemap,
    add_basemap_to_project,
    any_basemap_loaded,
    basemap_loaded_in_project,
    basemaps_by_category,
    connection_exists,
    current_project_crs_auth_id,
    install_and_add,
    install_connection,
    project_crs_is_target,
    set_project_crs_to_target,
    zoom_to_germany,
)

_OK_COLOR = "#2e7d32"
_FAIL_COLOR = "#c62828"


class SetupDialog(QDialog):
    """Dialog für Projekt-Setup und Basiskarten-Installation."""

    def __init__(self, plugin, parent=None):
        super().__init__(parent)
        self._plugin = plugin
        self.setWindowTitle("THW Toolbox Setup")
        self.resize(620, 640)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        self._content_layout = QVBoxLayout(container)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(12)
        scroll.setWidget(container)
        outer.addWidget(scroll, 1)

        self._status_group = self._build_status_group()
        self._content_layout.addWidget(self._status_group)

        self._basemaps_group = self._build_basemaps_group()
        self._content_layout.addWidget(self._basemaps_group)

        self._content_layout.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        outer.addWidget(buttons)

        self._refresh_all()

    # ---------------------------------------------------------------- status

    def _build_status_group(self) -> QGroupBox:
        box = QGroupBox("Projekt-Status")
        grid = QGridLayout()
        grid.setColumnStretch(1, 1)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        self._crs_label = QLabel()
        self._crs_label.setWordWrap(True)
        self._crs_fix_btn = QPushButton(f"Auf {TARGET_CRS} setzen")
        self._crs_fix_btn.clicked.connect(self._fix_crs)

        self._basemap_label = QLabel()
        self._basemap_label.setWordWrap(True)
        self._basemap_fix_btn = QPushButton("OSM laden")
        self._basemap_fix_btn.clicked.connect(self._fix_basemap)

        self._zoom_label = QLabel("Kartenansicht auf Deutschland zentrieren")
        self._zoom_label.setWordWrap(True)
        self._zoom_btn = QPushButton("Auf Deutschland zoomen")
        self._zoom_btn.clicked.connect(self._zoom_germany)

        row = 0
        grid.addWidget(self._title_label("Koordinatensystem"), row, 0)
        grid.addWidget(self._crs_label, row, 1)
        grid.addWidget(self._crs_fix_btn, row, 2)
        row += 1
        grid.addWidget(self._title_label("Basiskarte im Projekt"), row, 0)
        grid.addWidget(self._basemap_label, row, 1)
        grid.addWidget(self._basemap_fix_btn, row, 2)
        row += 1
        grid.addWidget(self._title_label("Kartenausschnitt"), row, 0)
        grid.addWidget(self._zoom_label, row, 1)
        grid.addWidget(self._zoom_btn, row, 2)

        box.setLayout(grid)
        return box

    def _title_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        f = QFont(lbl.font())
        f.setBold(True)
        lbl.setFont(f)
        return lbl

    def _refresh_status(self) -> None:
        if project_crs_is_target():
            self._set_status(self._crs_label, True, f"{TARGET_CRS} ({TARGET_CRS_LABEL})")
            self._crs_fix_btn.setEnabled(False)
        else:
            current = current_project_crs_auth_id() or "nicht gesetzt"
            self._set_status(
                self._crs_label,
                False,
                f"Aktuell: {current} – erwartet {TARGET_CRS} ({TARGET_CRS_LABEL})",
            )
            self._crs_fix_btn.setEnabled(True)

        if any_basemap_loaded():
            self._set_status(self._basemap_label, True, "Basiskarte geladen")
            self._basemap_fix_btn.setEnabled(False)
        else:
            self._set_status(self._basemap_label, False, "Keine bekannte Basiskarte im Projekt")
            self._basemap_fix_btn.setEnabled(True)

    @staticmethod
    def _set_status(label: QLabel, ok: bool, text: str) -> None:
        prefix = "✓" if ok else "✗"
        color = _OK_COLOR if ok else _FAIL_COLOR
        label.setText(f"<span style='color:{color}; font-weight:bold;'>{prefix}</span> {text}")

    def _fix_crs(self) -> None:
        set_project_crs_to_target()
        self._refresh_all()

    def _fix_basemap(self) -> None:
        osm = next((b for b in BASEMAPS if b.key == "osm"), None)
        if osm:
            add_basemap_to_project(osm, log=self._log_message)
        self._refresh_all()

    def _zoom_germany(self) -> None:
        if not zoom_to_germany():
            self._log_message("Konnte Kartenausschnitt nicht setzen.", critical=True)

    # ------------------------------------------------------------- basemaps

    def _build_basemaps_group(self) -> QGroupBox:
        box = QGroupBox("Basiskarten & Fachdaten installieren")
        vbox = QVBoxLayout()
        vbox.setSpacing(6)

        hint = QLabel(
            "'Zum Projekt hinzufügen' fügt die Karte als Layer hinzu und legt "
            "zusätzlich eine dauerhafte Verbindung im QGIS-Browser an. "
            "'Nur Verbindung' legt lediglich die Verbindung an."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray;")
        vbox.addWidget(hint)

        self._basemap_rows: dict[str, dict] = {}
        tabs = QTabWidget()
        for category, items in basemaps_by_category().items():
            tabs.addTab(self._build_category_tab(items), category)
        vbox.addWidget(tabs)

        box.setLayout(vbox)
        return box

    def _build_category_tab(self, items: list) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 6, 0, 0)
        page_layout.setSpacing(6)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(0, 0, 0, 0)
        inner_layout.setSpacing(4)
        for bm in items:
            inner_layout.addWidget(self._build_basemap_row(bm))
        inner_layout.addStretch(1)
        scroll.setWidget(inner)
        page_layout.addWidget(scroll, 1)
        return page

    def _build_basemap_row(self, bm: Basemap) -> QWidget:
        row = QFrame()
        row.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QGridLayout(row)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setHorizontalSpacing(8)
        layout.setColumnStretch(0, 1)

        name = QLabel(bm.name)
        f = QFont(name.font())
        f.setBold(True)
        name.setFont(f)
        layout.addWidget(name, 0, 0)

        status = QLabel()
        status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(status, 0, 1)

        desc = QLabel(bm.description)
        desc.setStyleSheet("color: gray;")
        desc.setWordWrap(True)
        layout.addWidget(desc, 1, 0, 1, 2)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        add_btn = QPushButton("Zum Projekt hinzufügen")
        add_btn.clicked.connect(lambda _=False, b=bm: self._on_install_and_add(b))
        conn_btn = QPushButton("Nur Verbindung")
        conn_btn.clicked.connect(lambda _=False, b=bm: self._on_install_connection_only(b))
        btn_row.addStretch(1)
        btn_row.addWidget(conn_btn)
        btn_row.addWidget(add_btn)
        layout.addLayout(btn_row, 2, 0, 1, 2)

        self._basemap_rows[bm.key] = {"status": status, "add": add_btn, "conn": conn_btn}
        return row

    def _refresh_basemaps(self) -> None:
        for bm in BASEMAPS:
            refs = self._basemap_rows.get(bm.key)
            if not refs:
                continue
            in_project = basemap_loaded_in_project(bm)
            has_conn = connection_exists(bm)
            parts = []
            if in_project:
                parts.append(f"<span style='color:{_OK_COLOR};'>✓ im Projekt</span>")
            if has_conn:
                parts.append(f"<span style='color:{_OK_COLOR};'>✓ Verbindung</span>")
            if not parts:
                parts.append(f"<span style='color:{_FAIL_COLOR};'>nicht installiert</span>")
            refs["status"].setText(" · ".join(parts))
            refs["add"].setEnabled(not in_project)

    def _on_install_and_add(self, bm: Basemap) -> None:
        ok = install_and_add(bm, log=self._log_message)
        if not ok:
            self._log_message(f"Fehler beim Hinzufügen von '{bm.name}'.", critical=True)
        self._refresh_all()

    def _on_install_connection_only(self, bm: Basemap) -> None:
        install_connection(bm)
        self._refresh_all()

    # ---------------------------------------------------------------- util

    def _log_message(self, msg: str, critical: bool = False) -> None:
        try:
            from qgis.core import Qgis
            from qgis.utils import iface

            level = Qgis.MessageLevel.Critical if critical else Qgis.MessageLevel.Info
            iface.messageBar().pushMessage("THW Setup", msg, level=level)
        except Exception:
            pass

    def _refresh_all(self) -> None:
        self._refresh_status()
        self._refresh_basemaps()
