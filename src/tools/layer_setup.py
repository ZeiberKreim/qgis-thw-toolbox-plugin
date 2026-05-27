"""Installation helper for basemaps and additional layers

Exposes small pure-ish functions the SetupDialog can call. Each basemap is
described as a dataclass; installation writes a permanent QgsSettings
connection (so the source shows up in the QGIS browser) and can optionally
also add a live layer to the current project.
"""

from dataclasses import dataclass
from typing import Callable, Optional

from qgis.core import QgsProject

from ..logging_utils import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class MapLayer:
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


_CBM_WORLD = "Allg. Karten Weltweit"
_CBM_AERIAL = "Luftbilder Weltweit"

BASEMAPS: tuple[MapLayer, ...] = (
    MapLayer(
        key="osm",
        name="OpenStreetMap",
        kind="xyz",
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        zmin=0,
        zmax=19,
        description="OpenStreetMap Standard (weltweit)",
        category=_CBM_WORLD,
    ),
    MapLayer(
        key="topplus_web",
        name="TopPlusOpen Web (BKG)",
        kind="wms",
        url="https://sgx.geodatenzentrum.de/wms_topplus_open",
        wms_params={"layers": "web", "styles": "", "format": "image/png", "crs": ""},
        description="Amtliche Web-Karte des BKG (WMS)",
        category=_CBM_WORLD,
    ),
    MapLayer(
        key="topplus_grau",
        name="TopPlusOpen Grau (BKG)",
        kind="wms",
        url="https://sgx.geodatenzentrum.de/wms_topplus_open",
        wms_params={"layers": "web_grau", "styles": "", "format": "image/png", "crs": ""},
        description="Graustufen-Variante (gut für Overlays)",
        category=_CBM_WORLD,
    ),
    MapLayer(
        key="bkg_dop",
        name="BKG Sentinel-2 Mosaik",
        kind="wms",
        url="https://sgx.geodatenzentrum.de/wms_sen2europe",
        wms_params={"layers": "rgb", "styles": "", "format": "image/png", "crs": ""},
        description="Sentinel-2-Mosaik Europa (BKG, offen)",
        category=_CBM_AERIAL,
    ),
    MapLayer(
        key="basemapde_vektor",
        name="basemap.de Vektor (Farbe)",
        kind="vtile",
        url="https://sgx.geodatenzentrum.de/gdz_basemapde_vektor/tiles/v1/bm_web_vt/{z}/{x}/{y}.pbf",
        style_url="https://sgx.geodatenzentrum.de/gdz_basemapde_vektor/styles/bm_web_col.json",
        zmin=0,
        zmax=15,
        description="Vektorbasiskarte Deutschland (bmd)",
        category=_CBM_WORLD,
    ),
    MapLayer(
        key="basemapde_vektor_grau",
        name="basemap.de Vektor (Grau)",
        kind="vtile",
        url="https://sgx.geodatenzentrum.de/gdz_basemapde_vektor/tiles/v1/bm_web_vt/{z}/{x}/{y}.pbf",
        style_url="https://sgx.geodatenzentrum.de/gdz_basemapde_vektor/styles/bm_web_gry.json",
        zmin=0,
        zmax=15,
        description="Vektorbasiskarte Grau",
        category=_CBM_WORLD,
    ),
    MapLayer(
        key="esri_world_imagery",
        name="Esri World Imagery",
        kind="xyz",
        url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        zmax=19,
        description="Hochaufgelöste Satellitenbilder (Esri, frei)",
        category=_CBM_AERIAL,
    ),
    MapLayer(
        key="esri_world_topo",
        name="Esri World Topo",
        kind="xyz",
        url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
        zmax=19,
        description="Topografische Weltkarte (Esri)",
        category=_CBM_WORLD,
    ),
    MapLayer(
        key="esri_world_street",
        name="Esri World Street",
        kind="xyz",
        url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
        zmax=19,
        description="Straßenkarte weltweit (Esri)",
        category=_CBM_WORLD,
    ),
    MapLayer(
        key="cartodb_positron",
        name="CartoDB Positron",
        kind="xyz",
        url="https://basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
        zmax=20,
        description="Helle, schlichte Basiskarte – gut für Overlays",
        category=_CBM_WORLD,
    ),
    MapLayer(
        key="cartodb_dark",
        name="CartoDB Dark Matter",
        kind="xyz",
        url="https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
        zmax=20,
        description="Dunkle, schlichte Basiskarte",
        category=_CBM_WORLD,
    ),
    MapLayer(
        key="opentopomap",
        name="OpenTopoMap",
        kind="xyz",
        url="https://a.tile.opentopomap.org/{z}/{x}/{y}.png",
        zmax=17,
        description="Topografie mit Höhenlinien (OSM-basiert)",
        category=_CBM_WORLD,
    ),
    MapLayer(
        key="s2cloudless_eox",
        name="Sentinel-2 Cloudless (EOX)",
        kind="wms",
        url="https://tiles.maps.eox.at/wms",
        wms_params={"layers": "s2cloudless-2023", "styles": "", "format": "image/jpeg", "crs": "EPSG:3857"},
        description="Wolkenfreies Sentinel-2-Mosaik (EOX)",
        category=_CBM_AERIAL,
    ),
    MapLayer(
        key="cyclosm",
        name="CyclOSM",
        kind="xyz",
        url="https://a.tile-cyclosm.openstreetmap.fr/cyclosm/{z}/{x}/{y}.png",
        zmax=20,
        description="Radwege-fokussierte OSM-Karte",
        category=_CBM_WORLD,
    ),
)


def basemaps_by_category() -> dict[str, list[MapLayer]]:
    """Gruppiert BASEMAPS nach Kategorie, Reihenfolge stabil."""
    order: list[str] = []
    groups: dict[str, list[MapLayer]] = {}
    for bm in BASEMAPS:
        if bm.category not in groups:
            groups[bm.category] = []
            order.append(bm.category)
        groups[bm.category].append(bm)
    return {cat: groups[cat] for cat in order}


_CAL_THEMED = "Fachdaten"
_CAL_AERIAL_STATE = "Luftbilder Länder"
_CAL_DRONE = "Drohne"

ADD_LAYERS: tuple[MapLayer, ...] = (
    MapLayer(
        key="bfn_schutzgebiete",
        name="Schutzgebiete (BfN)",
        kind="wms",
        url="https://geodienste.bfn.de/ogc/wms/schutzgebiet",
        wms_params={"layers": "Naturschutzgebiete", "styles": "", "format": "image/png", "crs": ""},
        description="INSPIRE-Schutzgebiete (Bundesamt für Naturschutz)",
        category=_CAL_THEMED,
    ),
    MapLayer(
        key="openrailwaymap",
        name="OpenRailwayMap",
        kind="xyz",
        url="https://a.tiles.openrailwaymap.org/standard/{z}/{x}/{y}.png",
        zmax=19,
        description="Eisenbahn-Infrastruktur (OSM-basiert, Overlay)",
        category=_CAL_THEMED,
    ),
    MapLayer(
        key="openseamap",
        name="OpenSeaMap (Overlay)",
        kind="xyz",
        url="https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png",
        zmax=18,
        description="Seezeichen als Overlay – mit OSM darunter kombinieren",
        category=_CAL_THEMED,
    ),
    MapLayer(
        key="waymarked_hiking",
        name="Waymarked Trails – Wandern",
        kind="xyz",
        url="https://tile.waymarkedtrails.org/hiking/{z}/{x}/{y}.png",
        zmax=18,
        description="Wanderwege (Overlay)",
        category=_CAL_THEMED,
    ),
    MapLayer(
        key="waymarked_cycling",
        name="Waymarked Trails – Rad",
        kind="xyz",
        url="https://tile.waymarkedtrails.org/cycling/{z}/{x}/{y}.png",
        zmax=18,
        description="Radrouten (Overlay)",
        category=_CAL_THEMED,
    ),
    MapLayer(
        key="by_dop",
        name="Bayern – DOP20 (Luftbild)",
        kind="wms",
        url="https://geoservices.bayern.de/od/wms/dop/v1/dop40",
        wms_params={"layers": "by_dop40c", "styles": "", "format": "image/png", "crs": ""},
        description="Digitale Orthophotos Bayern (LDBV, Open Data)",
        category=_CAL_AERIAL_STATE,
    ),
    MapLayer(
        key="nw_dop",
        name="NRW – DOP (Luftbild)",
        kind="wms",
        url="https://www.wms.nrw.de/geobasis/wms_nw_dop",
        wms_params={"layers": "nw_dop_rgb", "styles": "", "format": "image/png", "crs": ""},
        description="Digitale Orthophotos NRW (tim-online)",
        category=_CAL_AERIAL_STATE,
    ),
    MapLayer(
        key="nw_dtk",
        name="NRW – DTK",
        kind="wms",
        url="https://www.wms.nrw.de/geobasis/wms_nw_dtk",
        wms_params={"layers": "nw_dtk_col", "styles": "", "format": "image/png", "crs": ""},
        description="Topografische Karte NRW, farbig (tim-online)",
        category=_CAL_AERIAL_STATE,
    ),
    MapLayer(
        key="bw_dop",
        name="BW – DOP (CIR-Luftbild)",
        kind="wms",
        url="https://owsproxy.lgl-bw.de/owsproxy/ows/WMS_LGL-BW_ATKIS_DOP_20_CIR",
        wms_params={"layers": "IMAGES_DOP_20_CIR", "styles": "", "format": "image/png", "crs": ""},
        description="Digitales Orthophoto BW, Color-Infrared (LGL)",
        category=_CAL_AERIAL_STATE,
    ),
    MapLayer(
        key="ni_dop",
        name="Niedersachsen – DOP",
        kind="wms",
        url="https://opendata.lgln.niedersachsen.de/doorman/noauth/dop_wms",
        wms_params={"layers": "ni_dop20", "styles": "", "format": "image/png", "crs": ""},
        description="Orthophotos Niedersachsen (LGLN, Open Data)",
        category=_CAL_AERIAL_STATE,
    ),
    MapLayer(
        key="sn_dop",
        name="Sachsen – DOP",
        kind="wms",
        url="https://geodienste.sachsen.de/wms_geosn_dop-rgb/guest",
        wms_params={"layers": "sn_dop_020", "styles": "", "format": "image/png", "crs": ""},
        description="Digitale Orthophotos Sachsen (GeoSN)",
        category=_CAL_AERIAL_STATE,
    ),
    MapLayer(
        key="sn_webatlas",
        name="Sachsen – Webatlas",
        kind="wms",
        url="https://geodienste.sachsen.de/wms_geosn_webatlas-sn/guest",
        wms_params={
            "layers": "Vegetation,Siedlung,Gewaesser,Verkehr,Administrative_Einheiten,Beschriftung",
            "styles": "",
            "format": "image/png",
            "crs": "",
        },
        description="Topografischer Webatlas Sachsen (Komposit)",
        category=_CAL_AERIAL_STATE,
    ),
    MapLayer(
        key="he_dop",
        name="Hessen – DOP",
        kind="wms",
        url="https://www.gds-srv.hessen.de/cgi-bin/lika-services/ogc-free-images.ows",
        wms_params={"layers": "he_dop20_rgb", "styles": "", "format": "image/png", "crs": ""},
        description="Orthophotos Hessen 20cm RGB (HVBG, Open Data)",
        category=_CAL_AERIAL_STATE,
    ),
    MapLayer(
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
        category=_CAL_DRONE,
    ),
    MapLayer(
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
        category=_CAL_DRONE,
    ),
    MapLayer(
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
        category=_CAL_DRONE,
    ),
    MapLayer(
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
        category=_CAL_DRONE,
    ),
)


def additional_layers_by_category() -> dict[str, list[MapLayer]]:
    """Gruppiert ADD_LAYERS nach Kategorie, Reihenfolge stabil."""
    order: list[str] = []
    groups: dict[str, list[MapLayer]] = {}
    for al in ADD_LAYERS:
        if al.category not in groups:
            groups[al.category] = []
            order.append(al.category)
        groups[al.category].append(al)
    return {cat: groups[cat] for cat in order}
