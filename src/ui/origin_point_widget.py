from qgis.PyQt.QtCore import QSize, Qt, pyqtSignal
from qgis.PyQt.QtWidgets import QGridLayout, QPushButton, QSizePolicy, QWidget


class OriginPointWidget(QWidget):
    """3x3 Grid-Widget zur Auswahl des Origin-Points (Ankerpunkt) fuer Transformationen.

    Origin-Point Mapping:
        (0,0) = oben-links     (1,0) = oben-mitte     (2,0) = oben-rechts
        (0,1) = mitte-links    (1,1) = mitte           (2,1) = mitte-rechts
        (0,2) = unten-links    (1,2) = unten-mitte     (2,2) = unten-rechts
    """

    # Signal: (origin_x, origin_y)
    origin_changed = pyqtSignal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._origin_x = 1  # Default: Mitte
        self._origin_y = 1

        self._buttons = {}
        self._setup_ui()
        self._update_buttons()

    def _setup_ui(self):
        layout = QGridLayout(self)
        layout.setSpacing(2)
        layout.setContentsMargins(0, 0, 0, 0)

        for row in range(3):
            for col in range(3):
                btn = QPushButton()
                btn.setFixedSize(QSize(24, 24))
                btn.setCheckable(True)
                btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
                btn.setStyleSheet(self._button_style(False))
                btn.clicked.connect(lambda checked, c=col, r=row: self._on_click(c, r))
                layout.addWidget(btn, row, col)
                self._buttons[(col, row)] = btn

        self.setFixedSize(QSize(80, 80))

    def _button_style(self, selected):
        if selected:
            return (
                "QPushButton { background-color: #2E86AB; border: 1px solid #1a5276; "
                "border-radius: 3px; }"
            )
        return (
            "QPushButton { background-color: #ddd; border: 1px solid #aaa; "
            "border-radius: 3px; }"
            "QPushButton:hover { background-color: #bbb; }"
        )

    def _on_click(self, x, y):
        if x == self._origin_x and y == self._origin_y:
            return
        self._origin_x = x
        self._origin_y = y
        self._update_buttons()
        self.origin_changed.emit(x, y)

    def _update_buttons(self):
        for (col, row), btn in self._buttons.items():
            selected = col == self._origin_x and row == self._origin_y
            btn.setChecked(selected)
            btn.setStyleSheet(self._button_style(selected))

    def set_origin(self, x, y):
        """Setzt den Origin-Point programmatisch (ohne Signal)."""
        self._origin_x = x
        self._origin_y = y
        self._update_buttons()

    def origin(self):
        """Gibt den aktuellen Origin-Point als (x, y) Tuple zurueck."""
        return self._origin_x, self._origin_y
