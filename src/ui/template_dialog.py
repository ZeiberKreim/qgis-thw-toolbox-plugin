"""Dialog zum Auswählen und Öffnen mitgelieferter Druckvorlagen (.qpt)."""

import os

from qgis.core import QgsPrintLayout, QgsProject, QgsReadWriteContext
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)
from qgis.PyQt.QtXml import QDomDocument
from qgis.utils import iface


class TemplateDialog(QDialog):
    """Listet die .qpt-Dateien aus dem Plugin-Ordner `templates/` und öffnet sie im Designer."""

    def __init__(self, plugin_dir: str, parent=None):
        super().__init__(parent)
        self._templates_dir = os.path.join(plugin_dir, "templates")
        self.setWindowTitle("THW Toolbox – Druckvorlagen")
        self.resize(460, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        hint = QLabel(
            "Wählen Sie eine Druckvorlage und öffnen Sie sie im QGIS Layout-Designer. "
            "Die Vorlage wird als neues Layout im Projekt angelegt."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray;")
        layout.addWidget(hint)

        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(lambda _: self._open_selected())
        layout.addWidget(self._list, 1)

        btn_row = QHBoxLayout()
        self._open_btn = QPushButton("Im Designer öffnen")
        self._open_btn.setDefault(True)
        self._open_btn.clicked.connect(self._open_selected)
        btn_row.addStretch(1)
        btn_row.addWidget(self._open_btn)
        layout.addLayout(btn_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._populate()

    def _populate(self) -> None:
        self._list.clear()
        if not os.path.isdir(self._templates_dir):
            self._show_empty("Kein `templates/`-Ordner im Plugin gefunden.")
            return

        files = sorted(f for f in os.listdir(self._templates_dir) if f.lower().endswith(".qpt"))
        if not files:
            self._show_empty("Keine Vorlagen (.qpt) im Plugin-Ordner `templates/` vorhanden.")
            return

        for name in files:
            item = QListWidgetItem(os.path.splitext(name)[0])
            item.setData(Qt.ItemDataRole.UserRole, os.path.join(self._templates_dir, name))
            self._list.addItem(item)
        self._list.setCurrentRow(0)
        self._open_btn.setEnabled(True)

    def _show_empty(self, message: str) -> None:
        item = QListWidgetItem(message)
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        self._list.addItem(item)
        self._open_btn.setEnabled(False)

    def _open_selected(self) -> None:
        item = self._list.currentItem()
        if not item:
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError as e:
            QMessageBox.critical(self, "Fehler", f"Vorlage konnte nicht gelesen werden:\n{e}")
            return

        doc = QDomDocument()
        if not doc.setContent(content):
            QMessageBox.critical(self, "Fehler", "Vorlage ist keine gültige XML-Datei.")
            return

        project = QgsProject.instance()
        layout = QgsPrintLayout(project)
        ok, _ = layout.loadFromTemplate(doc, QgsReadWriteContext())
        if not ok:
            QMessageBox.critical(self, "Fehler", "Vorlage konnte nicht geladen werden.")
            return

        base_name = os.path.splitext(os.path.basename(path))[0]
        layout.setName(self._unique_layout_name(base_name))
        project.layoutManager().addLayout(layout)
        iface.openLayoutDesigner(layout)
        self.accept()

    @staticmethod
    def _unique_layout_name(base: str) -> str:
        manager = QgsProject.instance().layoutManager()
        existing = {lay.name() for lay in manager.layouts()}
        if base not in existing:
            return base
        i = 2
        while f"{base} ({i})" in existing:
            i += 1
        return f"{base} ({i})"
