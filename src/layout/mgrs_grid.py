"""MGRS-/UTMRef-Umrechnung: Punkt ↔ Koordinatentext inkl. 100-km-Quadrat.

Gemeinsame Bausteine (Breitenband, UTM-Zone, 100-km-Quadrat) nutzt auch ``util.coordinates``.
"""

from __future__ import annotations

import math
import re

from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsPointXY, QgsProject

BAND_LETTERS = "CDEFGHJKLMNPQRSTUVWX"
COL_SETS = ("ABCDEFGH", "JKLMNPQR", "STUVWXYZ")
ROW_ODD = "ABCDEFGHJKLMNPQRSTUV"
ROW_EVEN = "FGHJKLMNPQRSTUVABCDE"


def _latitude_band(lat: float) -> str:
    if lat >= 84:
        return "X"
    if lat < -80:
        return "C"
    return BAND_LETTERS[min(int((lat + 80) // 8), 19)]


def _utm_zone(lon: float) -> int:
    return int((lon + 180) // 6) + 1


def _utm_epsg(zone: int, lat: float) -> int:
    return (32600 if lat >= 0 else 32700) + zone


def _mgrs_100km(zone: int, easting: float, northing: float) -> str:
    col_idx = max(0, min(7, int(easting // 100_000) - 1))
    col = COL_SETS[(zone - 1) % 3][col_idx]
    rowset = ROW_ODD if zone % 2 == 1 else ROW_EVEN
    row = rowset[int((northing % 2_000_000) // 100_000)]
    return col + row


# MGRS-Auflösungen (Meter) und zugehörige Stellenzahl je Rechts-/Hochwert
MGRS_RESOLUTIONS_M = (0.1, 1.0, 10.0, 100.0)


def _utm_zone_for_position(lat: float, lon: float) -> int:
    """UTM-Zone eines Punktes inkl. der Sonderzonen Norwegen (32V) und Spitzbergen (31X–37X)."""
    zone = _utm_zone(lon)
    if 56 <= lat < 64 and 3 <= lon < 12:
        zone = 32
    elif 72 <= lat < 84 and lon >= 0:
        if lon < 9:
            zone = 31
        elif lon < 21:
            zone = 33
        elif lon < 33:
            zone = 35
        elif lon < 42:
            zone = 37
    return min(max(zone, 1), 60)


def point_to_mgrs(point: QgsPointXY, crs: QgsCoordinateReferenceSystem, resolution_m: float = 1.0) -> str | None:
    """MGRS/UTMRef-Koordinate eines Punktes, z. B. ``32U MB 12345 98765`` (bei 1 m Auflösung).

    ``resolution_m`` (0,1 / 1 / 10 / 100 m) bestimmt die Stellenzahl von Rechts- und
    Hochwert (6 / 5 / 4 / 3); wie bei MGRS üblich wird abgeschnitten, nicht gerundet.
    Gibt None zurück, wenn der Punkt außerhalb des UTM-Bereichs (80° S – 84° N) liegt.
    """
    project = QgsProject.instance()
    wgs84 = QgsCoordinateReferenceSystem.fromEpsgId(4326)
    lonlat = QgsCoordinateTransform(crs, wgs84, project).transform(point)
    lon, lat = lonlat.x(), lonlat.y()
    if not -80 <= lat < 84:
        return None

    zone = _utm_zone_for_position(lat, lon)
    utm_crs = QgsCoordinateReferenceSystem.fromEpsgId(_utm_epsg(zone, lat))
    utm = QgsCoordinateTransform(wgs84, utm_crs, project).transform(lonlat)

    digits = 5 - int(round(math.log10(resolution_m)))  # 0.1→6, 1→5, 10→4, 100→3
    # Kleiner Zuschlag gegen Gleitkomma-Artefakte (z. B. 12344,9999… statt 12345)
    easting = int(math.floor((utm.x() % 100_000) / resolution_m + 1e-6))
    northing = int(math.floor((utm.y() % 100_000) / resolution_m + 1e-6))
    square = _mgrs_100km(zone, utm.x(), utm.y())
    return f"{zone}{_latitude_band(lat)} {square} {easting:0{digits}d} {northing:0{digits}d}"


def _parse_mgrs(text: str) -> tuple[int, str, str, str, float, float] | None:
    """Zerlegt eine MGRS-Angabe in (Zone, Band, Spalte, Zeile, Rechts-, Hochwert innerhalb des 100-km-Quadrats).

    Akzeptiert z. B. ``32U MB 12345 98765``, ``32umb1234598765`` oder ``32U MB 123 987``
    (2–10 Ziffern, gleich viele für Rechts- und Hochwert). None bei ungültiger Eingabe.
    """
    compact = "".join(text.split()).upper()
    match = re.fullmatch(r"(\d{1,2})([C-HJ-NP-X])([A-HJ-NP-Z])([A-HJ-NP-V])(\d*)", compact)
    if not match:
        return None
    zone_s, band, col, row, digits = match.groups()
    zone = int(zone_s)
    if not 1 <= zone <= 60 or len(digits) % 2 or len(digits) > 10:
        return None
    half = len(digits) // 2
    scale = 10 ** (5 - half)
    east = int(digits[:half]) * scale if half else 0
    north = int(digits[half:]) * scale if half else 0
    return zone, band, col, row, float(east), float(north)


def mgrs_to_point(text: str, crs: QgsCoordinateReferenceSystem) -> QgsPointXY | None:
    """Gegenstück zu ``point_to_mgrs``: MGRS/UTMRef-Text → Punkt in ``crs`` (None bei ungültiger Angabe).

    Die Angabe bezeichnet wie bei MGRS üblich die Südwest-Ecke der Gitterzelle.
    """
    parsed = _parse_mgrs(text)
    if parsed is None:
        return None
    zone, band, col, row, east_in_square, north_in_square = parsed

    col_set = COL_SETS[(zone - 1) % 3]
    row_set = ROW_ODD if zone % 2 == 1 else ROW_EVEN
    if col not in col_set or row not in row_set:
        return None
    easting = (col_set.index(col) + 1) * 100_000 + east_in_square
    northing_in_cycle = row_set.index(row) * 100_000 + north_in_square

    # The row letters repeat every 2000 km: pick the cycle that falls into the latitude band.
    # The band's southern edge on the central meridian gives a lower bound (with some margin
    # for the curvature of the parallels away from the central meridian).
    band_south = -80 + BAND_LETTERS.index(band) * 8
    north_hemisphere = band >= "N"
    project = QgsProject.instance()
    wgs84 = QgsCoordinateReferenceSystem.fromEpsgId(4326)
    utm_crs = QgsCoordinateReferenceSystem.fromEpsgId((32600 if north_hemisphere else 32700) + zone)
    central_meridian = zone * 6 - 183
    band_min_northing = (
        QgsCoordinateTransform(wgs84, utm_crs, project).transform(QgsPointXY(central_meridian, band_south)).y()
    )
    northing = northing_in_cycle
    while northing < band_min_northing - 100_000:
        northing += 2_000_000

    return QgsCoordinateTransform(utm_crs, crs, project).transform(QgsPointXY(easting, northing))
