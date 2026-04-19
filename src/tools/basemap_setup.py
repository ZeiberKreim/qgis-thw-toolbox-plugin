"""Installation helpers for basemaps and project CRS.

Exposes small pure-ish functions the SetupDialog can call. Each basemap is
described as a dataclass; installation writes a permanent QgsSettings
connection (so the source shows up in the QGIS browser) and can optionally
also add a live layer to the current project.
"""

from dataclasses import dataclass
from typing import Callable, Optional
from urllib.parse import quote

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsProject,
    QgsRasterLayer,
    QgsRectangle,
    QgsVectorTileLayer,
)
from qgis.PyQt.QtCore import QSettings

TARGET_CRS = "EPSG:25832"
TARGET_CRS_LABEL = "ETRS89 / UTM Zone 32N"


@dataclass(frozen=True)
class Basemap:
    key: str
    name: str
    kind: str  # "xyz" | "wms" | "vtile"
    # XYZ: raw URL template like "https://.../{z}/{x}/{y}.png"
    # WMS: GetCapabilities URL + `wms_params` dict used for provider URI
    # VTILE: tile URL + style URL
    url: str
    zmin: int = 0
    zmax: int = 19
    style_url: str = ""
    wms_params: Optional[dict] = None
    description: str = ""
    category: str = "Deutschland"


_CAT_DE = "Deutschland"
_CAT_WORLD = "Weltweit"
_CAT_STATES = "Bundesländer"
_CAT_THEMED = "Fachdaten"
_CAT_DRONE = "Drohne"

BASEMAPS: tuple[Basemap, ...] = (
    # ------------------------------------------------------------ Deutschland
    Basemap(
        key="osm",
        name="OpenStreetMap",
        kind="xyz",
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        zmin=0,
        zmax=19,
        description="OpenStreetMap Standard (weltweit)",
        category=_CAT_DE,
    ),
    Basemap(
        key="topplus_web",
        name="TopPlusOpen Web (BKG)",
        kind="wms",
        url="https://sgx.geodatenzentrum.de/wms_topplus_open",
        wms_params={"layers": "web", "styles": "", "format": "image/png", "crs": TARGET_CRS},
        description="Amtliche Web-Karte des BKG (WMS)",
        category=_CAT_DE,
    ),
    Basemap(
        key="topplus_grau",
        name="TopPlusOpen Grau (BKG)",
        kind="wms",
        url="https://sgx.geodatenzentrum.de/wms_topplus_open",
        wms_params={"layers": "web_grau", "styles": "", "format": "image/png", "crs": TARGET_CRS},
        description="Graustufen-Variante (gut für Overlays)",
        category=_CAT_DE,
    ),
    Basemap(
        key="bkg_dop",
        name="BKG Sentinel-2 Mosaik",
        kind="wms",
        url="https://sgx.geodatenzentrum.de/wms_sen2europe",
        wms_params={"layers": "rgb", "styles": "", "format": "image/png", "crs": TARGET_CRS},
        description="Sentinel-2-Mosaik Europa (BKG, offen)",
        category=_CAT_DE,
    ),
    Basemap(
        key="basemapde_vektor",
        name="basemap.de Vektor (Farbe)",
        kind="vtile",
        url="https://sgx.geodatenzentrum.de/gdz_basemapde_vektor/tiles/v1/bm_web_vt/{z}/{x}/{y}.pbf",
        style_url="https://sgx.geodatenzentrum.de/gdz_basemapde_vektor/styles/bm_web_col.json",
        zmin=0,
        zmax=15,
        description="Vektorbasiskarte Deutschland (bmd)",
        category=_CAT_DE,
    ),
    Basemap(
        key="basemapde_vektor_grau",
        name="basemap.de Vektor (Grau)",
        kind="vtile",
        url="https://sgx.geodatenzentrum.de/gdz_basemapde_vektor/tiles/v1/bm_web_vt/{z}/{x}/{y}.pbf",
        style_url="https://sgx.geodatenzentrum.de/gdz_basemapde_vektor/styles/bm_web_gry.json",
        zmin=0,
        zmax=15,
        description="Vektorbasiskarte Grau",
        category=_CAT_DE,
    ),
    # ------------------------------------------------------------ Weltweit
    Basemap(
        key="esri_world_imagery",
        name="Esri World Imagery",
        kind="xyz",
        url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        zmax=19,
        description="Hochaufgelöste Satellitenbilder (Esri, frei)",
        category=_CAT_WORLD,
    ),
    Basemap(
        key="esri_world_topo",
        name="Esri World Topo",
        kind="xyz",
        url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
        zmax=19,
        description="Topografische Weltkarte (Esri)",
        category=_CAT_WORLD,
    ),
    Basemap(
        key="esri_world_street",
        name="Esri World Street",
        kind="xyz",
        url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
        zmax=19,
        description="Straßenkarte weltweit (Esri)",
        category=_CAT_WORLD,
    ),
    Basemap(
        key="cartodb_positron",
        name="CartoDB Positron",
        kind="xyz",
        url="https://basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
        zmax=20,
        description="Helle, schlichte Basiskarte – gut für Overlays",
        category=_CAT_WORLD,
    ),
    Basemap(
        key="cartodb_dark",
        name="CartoDB Dark Matter",
        kind="xyz",
        url="https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
        zmax=20,
        description="Dunkle, schlichte Basiskarte",
        category=_CAT_WORLD,
    ),
    Basemap(
        key="opentopomap",
        name="OpenTopoMap",
        kind="xyz",
        url="https://a.tile.opentopomap.org/{z}/{x}/{y}.png",
        zmax=17,
        description="Topografie mit Höhenlinien (OSM-basiert)",
        category=_CAT_WORLD,
    ),
    Basemap(
        key="s2cloudless_eox",
        name="Sentinel-2 Cloudless (EOX)",
        kind="wms",
        url="https://tiles.maps.eox.at/wms",
        wms_params={"layers": "s2cloudless-2023", "styles": "", "format": "image/jpeg", "crs": "EPSG:3857"},
        description="Wolkenfreies Sentinel-2-Mosaik (EOX)",
        category=_CAT_WORLD,
    ),
    Basemap(
        key="cyclosm",
        name="CyclOSM",
        kind="xyz",
        url="https://a.tile-cyclosm.openstreetmap.fr/cyclosm/{z}/{x}/{y}.png",
        zmax=20,
        description="Radwege-fokussierte OSM-Karte",
        category=_CAT_WORLD,
    ),
    # ------------------------------------------------------------ Bundesländer
    Basemap(
        key="by_dop",
        name="Bayern – DOP20 (Luftbild)",
        kind="wms",
        url="https://geoservices.bayern.de/od/wms/dop/v1/dop40",
        wms_params={"layers": "by_dop40c", "styles": "", "format": "image/png", "crs": TARGET_CRS},
        description="Digitale Orthophotos Bayern (LDBV, Open Data)",
        category=_CAT_STATES,
    ),
    Basemap(
        key="nw_dop",
        name="NRW – DOP (Luftbild)",
        kind="wms",
        url="https://www.wms.nrw.de/geobasis/wms_nw_dop",
        wms_params={"layers": "nw_dop_rgb", "styles": "", "format": "image/png", "crs": TARGET_CRS},
        description="Digitale Orthophotos NRW (tim-online)",
        category=_CAT_STATES,
    ),
    Basemap(
        key="nw_dtk",
        name="NRW – DTK",
        kind="wms",
        url="https://www.wms.nrw.de/geobasis/wms_nw_dtk",
        wms_params={"layers": "nw_dtk_col", "styles": "", "format": "image/png", "crs": TARGET_CRS},
        description="Topografische Karte NRW, farbig (tim-online)",
        category=_CAT_STATES,
    ),
    Basemap(
        key="bw_dop",
        name="BW – DOP (CIR-Luftbild)",
        kind="wms",
        url="https://owsproxy.lgl-bw.de/owsproxy/ows/WMS_LGL-BW_ATKIS_DOP_20_CIR",
        wms_params={"layers": "IMAGES_DOP_20_CIR", "styles": "", "format": "image/png", "crs": TARGET_CRS},
        description="Digitales Orthophoto BW, Color-Infrared (LGL)",
        category=_CAT_STATES,
    ),
    Basemap(
        key="ni_dop",
        name="Niedersachsen – DOP",
        kind="wms",
        url="https://opendata.lgln.niedersachsen.de/doorman/noauth/dop_wms",
        wms_params={"layers": "ni_dop20", "styles": "", "format": "image/png", "crs": TARGET_CRS},
        description="Orthophotos Niedersachsen (LGLN, Open Data)",
        category=_CAT_STATES,
    ),
    Basemap(
        key="sn_dop",
        name="Sachsen – DOP",
        kind="wms",
        url="https://geodienste.sachsen.de/wms_geosn_dop-rgb/guest",
        wms_params={"layers": "sn_dop_020", "styles": "", "format": "image/png", "crs": TARGET_CRS},
        description="Digitale Orthophotos Sachsen (GeoSN)",
        category=_CAT_STATES,
    ),
    Basemap(
        key="sn_webatlas",
        name="Sachsen – Webatlas",
        kind="wms",
        url="https://geodienste.sachsen.de/wms_geosn_webatlas-sn/guest",
        wms_params={
            "layers": "Vegetation,Siedlung,Gewaesser,Verkehr,Administrative_Einheiten,Beschriftung",
            "styles": "",
            "format": "image/png",
            "crs": TARGET_CRS,
        },
        description="Topografischer Webatlas Sachsen (Komposit)",
        category=_CAT_STATES,
    ),
    Basemap(
        key="he_dop",
        name="Hessen – DOP",
        kind="wms",
        url="https://www.gds-srv.hessen.de/cgi-bin/lika-services/ogc-free-images.ows",
        wms_params={"layers": "he_dop20_rgb", "styles": "", "format": "image/png", "crs": TARGET_CRS},
        description="Orthophotos Hessen 20cm RGB (HVBG, Open Data)",
        category=_CAT_STATES,
    ),
    # ------------------------------------------------------------ Fachdaten
    Basemap(
        key="bfn_schutzgebiete",
        name="Schutzgebiete (BfN)",
        kind="wms",
        url="https://geodienste.bfn.de/ogc/wms/schutzgebiet",
        wms_params={"layers": "Naturschutzgebiete", "styles": "", "format": "image/png", "crs": TARGET_CRS},
        description="INSPIRE-Schutzgebiete (Bundesamt für Naturschutz)",
        category=_CAT_THEMED,
    ),
    Basemap(
        key="openrailwaymap",
        name="OpenRailwayMap",
        kind="xyz",
        url="https://a.tiles.openrailwaymap.org/standard/{z}/{x}/{y}.png",
        zmax=19,
        description="Eisenbahn-Infrastruktur (OSM-basiert, Overlay)",
        category=_CAT_THEMED,
    ),
    Basemap(
        key="openseamap",
        name="OpenSeaMap (Overlay)",
        kind="xyz",
        url="https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png",
        zmax=18,
        description="Seezeichen als Overlay – mit OSM darunter kombinieren",
        category=_CAT_THEMED,
    ),
    Basemap(
        key="waymarked_hiking",
        name="Waymarked Trails – Wandern",
        kind="xyz",
        url="https://tile.waymarkedtrails.org/hiking/{z}/{x}/{y}.png",
        zmax=18,
        description="Wanderwege (Overlay)",
        category=_CAT_THEMED,
    ),
    Basemap(
        key="waymarked_cycling",
        name="Waymarked Trails – Rad",
        kind="xyz",
        url="https://tile.waymarkedtrails.org/cycling/{z}/{x}/{y}.png",
        zmax=18,
        description="Radrouten (Overlay)",
        category=_CAT_THEMED,
    ),
    # ------------------------------------------------------------ Drohne
    # DIPUL WMS unterstützt nur EPSG:4326/3857/7789 – QGIS reprojiziert automatisch.
    Basemap(
        key="dipul_alle_luftrecht",
        name="DIPUL – Luftrechtliche Gebiete",
        kind="wms",
        url="https://uas-betrieb.de/geoservices/dipul/wms",
        wms_params={
            "layers": "flugbeschraenkungsgebiete,kontrollzonen,temporaere_betriebseinschraenkungen,flughaefen,flugplaetze,modellflugplaetze,haengegleiter",
            "styles": "",
            "format": "image/png",
            "crs": "EPSG:3857",
        },
        description="Flugbeschränkungsgebiete, Kontrollzonen, temporäre Einschränkungen, Flughäfen/-plätze (kombinierter Layer)",
        category=_CAT_DRONE,
    ),
    Basemap(
        key="dipul_naturschutz",
        name="DIPUL – Naturschutz",
        kind="wms",
        url="https://uas-betrieb.de/geoservices/dipul/wms",
        wms_params={
            "layers": "naturschutzgebiete,nationalparks,ffh-gebiete,vogelschutzgebiete",
            "styles": "",
            "format": "image/png",
            "crs": "EPSG:3857",
        },
        description="Naturschutz-, FFH- und Vogelschutzgebiete, Nationalparks",
        category=_CAT_DRONE,
    ),
    Basemap(
        key="dipul_sensible_objekte",
        name="DIPUL – Sensible Objekte",
        kind="wms",
        url="https://uas-betrieb.de/geoservices/dipul/wms",
        wms_params={
            "layers": "krankenhaeuser,polizei,sicherheitsbehoerden,justizvollzugsanstalten,militaerische_anlagen,behoerden,diplomatische_vertretungen,internationale_organisationen",
            "styles": "",
            "format": "image/png",
            "crs": "EPSG:3857",
        },
        description="Krankenhäuser, Polizei, JVA, Militär, Behörden, Diplomatie",
        category=_CAT_DRONE,
    ),
    Basemap(
        key="dipul_infrastruktur",
        name="DIPUL – Infrastruktur",
        kind="wms",
        url="https://uas-betrieb.de/geoservices/dipul/wms",
        wms_params={
            "layers": "bundesautobahnen,bundesstrassen,bahnanlagen,binnenwasserstrassen,seewasserstrassen,kraftwerke,stromleitungen,umspannwerke,industrieanlagen,windkraftanlagen",
            "styles": "",
            "format": "image/png",
            "crs": "EPSG:3857",
        },
        description="Verkehrswege, Energieversorgung, Industrieanlagen",
        category=_CAT_DRONE,
    ),
)


def basemaps_by_category() -> dict[str, list[Basemap]]:
    """Gruppiert BASEMAPS nach Kategorie, Reihenfolge stabil."""
    order: list[str] = []
    groups: dict[str, list[Basemap]] = {}
    for bm in BASEMAPS:
        if bm.category not in groups:
            groups[bm.category] = []
            order.append(bm.category)
        groups[bm.category].append(bm)
    return {cat: groups[cat] for cat in order}


# ---------------------------------------------------------------------------
# CRS
# ---------------------------------------------------------------------------


def current_project_crs_auth_id() -> str:
    crs = QgsProject.instance().crs()
    return crs.authid() if crs.isValid() else ""


def project_crs_is_target() -> bool:
    return current_project_crs_auth_id() == TARGET_CRS


def set_project_crs_to_target() -> bool:
    crs = QgsCoordinateReferenceSystem(TARGET_CRS)
    if not crs.isValid():
        return False
    QgsProject.instance().setCrs(crs)
    return True


# Geographische Bounding Box Deutschland (WGS84): ~5.8°E–15.1°E, 47.2°N–55.1°N
GERMANY_BBOX_WGS84 = QgsRectangle(5.8, 47.2, 15.1, 55.1)


def zoom_to_germany() -> bool:
    """Zoomt die Kartenansicht auf Deutschland (transformiert in das Projekt-CRS)."""
    try:
        from qgis.utils import iface

        if iface is None:
            return False
        canvas = iface.mapCanvas()
        project = QgsProject.instance()
        src = QgsCoordinateReferenceSystem("EPSG:4326")
        dst = project.crs()
        if not dst.isValid():
            dst = QgsCoordinateReferenceSystem(TARGET_CRS)
        transform = QgsCoordinateTransform(src, dst, project)
        extent = transform.transformBoundingBox(GERMANY_BBOX_WGS84)
        canvas.setExtent(extent)
        canvas.refresh()
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Basemap detection
# ---------------------------------------------------------------------------


def _layer_source_matches(source: str, basemap: Basemap) -> bool:
    if basemap.kind == "xyz":
        encoded = quote(basemap.url, safe="")
        return basemap.url in source or encoded in source
    if basemap.kind == "wms":
        if basemap.url not in source:
            return False
        raw_layers = (basemap.wms_params or {}).get("layers", "")
        first_layer = next((name.strip() for name in raw_layers.split(",") if name.strip()), "")
        return (first_layer in source) if first_layer else True
    if basemap.kind == "vtile":
        return basemap.url in source or quote(basemap.url, safe="") in source
    return False


def basemap_loaded_in_project(basemap: Basemap) -> bool:
    for lyr in QgsProject.instance().mapLayers().values():
        if _layer_source_matches(lyr.source(), basemap):
            return True
    return False


def any_basemap_loaded() -> bool:
    return any(basemap_loaded_in_project(b) for b in BASEMAPS)


# ---------------------------------------------------------------------------
# Connections (persistent, shown in QGIS browser)
# ---------------------------------------------------------------------------


def _s() -> QSettings:
    return QSettings()


def connection_exists(basemap: Basemap) -> bool:
    s = _s()
    if basemap.kind == "xyz":
        return s.contains(f"qgis/connections-xyz/{basemap.name}/url")
    if basemap.kind == "wms":
        return s.contains(f"qgis/connections-wms/{basemap.name}/url")
    if basemap.kind == "vtile":
        return s.contains(f"qgis/connections-vector-tile/{basemap.name}/url")
    return False


def reload_browser() -> None:
    """Bittet QGIS, die Browser-Connections neu einzulesen, damit neue
    Einträge sofort in der Browser-Ansicht erscheinen."""
    try:
        from qgis.utils import iface

        if iface is not None and hasattr(iface, "reloadConnections"):
            iface.reloadConnections()
    except Exception:
        pass


def install_connection(basemap: Basemap) -> None:
    s = _s()
    if basemap.kind == "xyz":
        base = f"qgis/connections-xyz/{basemap.name}"
        s.setValue(f"{base}/url", basemap.url)
        s.setValue(f"{base}/zmin", basemap.zmin)
        s.setValue(f"{base}/zmax", basemap.zmax)
        s.setValue(f"{base}/authcfg", "")
        s.setValue(f"{base}/username", "")
        s.setValue(f"{base}/password", "")
        s.setValue(f"{base}/referer", "")
        s.setValue(f"{base}/tilePixelRatio", 0)
    elif basemap.kind == "wms":
        base = f"qgis/connections-wms/{basemap.name}"
        s.setValue(f"{base}/url", basemap.url)
        s.setValue(f"{base}/ignoreAxisOrientation", False)
        s.setValue(f"{base}/invertAxisOrientation", False)
        s.setValue(f"{base}/ignoreGetFeatureInfoURI", False)
        s.setValue(f"{base}/smoothPixmapTransform", False)
        s.setValue(f"{base}/dpiMode", 7)
    elif basemap.kind == "vtile":
        base = f"qgis/connections-vector-tile/{basemap.name}"
        s.setValue(f"{base}/url", basemap.url)
        s.setValue(f"{base}/zmin", basemap.zmin)
        s.setValue(f"{base}/zmax", basemap.zmax)
        s.setValue(f"{base}/styleUrl", basemap.style_url)
        s.setValue(f"{base}/serviceType", "")
        s.setValue(f"{base}/authcfg", "")
        s.setValue(f"{base}/username", "")
        s.setValue(f"{base}/password", "")
        s.setValue(f"{base}/referer", "")
    reload_browser()


# ---------------------------------------------------------------------------
# Layers (added to current project)
# ---------------------------------------------------------------------------


def _build_xyz_uri(basemap: Basemap) -> str:
    encoded = quote(basemap.url, safe="")
    return f"type=xyz&url={encoded}&zmin={basemap.zmin}&zmax={basemap.zmax}"


def _build_wms_uri(basemap: Basemap) -> str:
    params = basemap.wms_params or {}
    encoded_url = quote(basemap.url, safe="")
    raw_layers = params.get("layers", "")
    layers = [name.strip() for name in raw_layers.split(",") if name.strip()]
    style = params.get("styles", "")

    parts = [
        "contextualWMSLegend=0",
        f"crs={params.get('crs', 'EPSG:3857')}",
        "dpiMode=7",
        "featureCount=10",
        f"format={params.get('format', 'image/png')}",
    ]
    # Für N Layer braucht der WMS-Provider N `layers=`- und N `styles=`-Einträge.
    for layer in layers:
        parts.append(f"layers={layer}")
        parts.append(f"styles={style}")
    parts.append(f"url={encoded_url}")
    return "&".join(parts)


def _build_vtile_uri(basemap: Basemap) -> str:
    encoded_url = quote(basemap.url, safe="")
    encoded_style = quote(basemap.style_url, safe="")
    return f"type=xyz&url={encoded_url}&zmin={basemap.zmin}&zmax={basemap.zmax}&styleUrl={encoded_style}"


def create_basemap_layer(basemap: Basemap):
    if basemap.kind == "xyz":
        return QgsRasterLayer(_build_xyz_uri(basemap), basemap.name, "wms")
    if basemap.kind == "wms":
        return QgsRasterLayer(_build_wms_uri(basemap), basemap.name, "wms")
    if basemap.kind == "vtile":
        return QgsVectorTileLayer(_build_vtile_uri(basemap), basemap.name)
    return None


THW_MARKER_LAYER_NAME = "THW Toolbox Marker"


def _insert_below_marker(layer) -> None:
    """Hängt den Layer im Layer-Baum unterhalb des THW-Toolbox-Marker-Layers ein.

    Fällt auf das Ende der Wurzel zurück, falls der Marker-Layer fehlt.
    """
    project = QgsProject.instance()
    root = project.layerTreeRoot()
    project.addMapLayer(layer, False)

    marker_layers = project.mapLayersByName(THW_MARKER_LAYER_NAME)
    if marker_layers:
        marker_node = root.findLayer(marker_layers[0].id())
        if marker_node is not None:
            parent = marker_node.parent()
            children = parent.children()
            idx = children.index(marker_node) + 1
            parent.insertLayer(idx, layer)
            return
    root.addLayer(layer)


def add_basemap_to_project(basemap: Basemap, log: Optional[Callable[[str], None]] = None) -> bool:
    """Add the basemap as a layer to the current project. Returns True on success."""
    layer = create_basemap_layer(basemap)
    if not layer or not layer.isValid():
        if log:
            err = ""
            try:
                err = layer.error().summary() if layer else ""
            except Exception:
                pass
            detail = f" – {err}" if err else ""
            log(f"Layer '{basemap.name}' konnte nicht geladen werden{detail}.")
        return False
    _insert_below_marker(layer)
    return True


def install_and_add(basemap: Basemap, log: Optional[Callable[[str], None]] = None) -> bool:
    install_connection(basemap)
    return add_basemap_to_project(basemap, log=log)
