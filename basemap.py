"""Satellite-imagery basemap for the GPS tab.

Fetches Esri World Imagery XYZ tiles (no heavy geo deps — stdlib urllib +
pillow), stitches them into one image, and returns it with its Web-Mercator
extent so it can be `imshow`-ed under a route plotted in Mercator. Tiles are
cached on disk; failures (offline) return None so the caller falls back to a
plain lat/lon plot.

Attribution: Esri, Maxar, Earthstar Geographics, and the GIS User Community.
"""
import io
import math
import os
import tempfile
import urllib.request

import numpy as np
from PIL import Image

_SAT_URL = ("https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Imagery/MapServer/tile/{z}/{y}/{x}")
# AWS Open Data "Terrain Tiles" — Terrarium-encoded elevation PNGs (XYZ scheme).
_DEM_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
_CACHE = os.path.join(tempfile.gettempdir(), "mtb_sat_tiles")
_R = 6378137.0          # Web-Mercator earth radius (m)
_TILE = 256             # tile pixel size
ATTRIBUTION = "Esri, Maxar, Earthstar Geographics"


def lonlat_to_mercator(lon, lat):
    """Vectorized lon/lat (deg) → Web-Mercator (x, y) metres (EPSG:3857)."""
    lon = np.asarray(lon, dtype=float)
    lat = np.asarray(lat, dtype=float)
    x = _R * np.radians(lon)
    y = _R * np.log(np.tan(np.pi / 4.0 + np.radians(lat) / 2.0))
    return x, y


def mercator_to_lonlat(x, y):
    """Inverse of lonlat_to_mercator: Web-Mercator metres → lon/lat (deg)."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    lon = np.degrees(x / _R)
    lat = np.degrees(2.0 * np.arctan(np.exp(y / _R)) - np.pi / 2.0)
    return lon, lat


def _lonlat_to_tile(lon, lat, z):
    n = 2 ** z
    xt = (lon + 180.0) / 360.0 * n
    yt = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n
    return xt, yt


def _tile_merc_bounds(xtile, ytile, z):
    """(left, top) Web-Mercator metres of a tile's top-left corner."""
    span = 2.0 * math.pi * _R
    ts = span / (2 ** z)
    return -math.pi * _R + xtile * ts, math.pi * _R - ytile * ts


def _pick_zoom(lon_min, lon_max, lat_min, lat_max, max_tiles=6):
    for z in range(19, 0, -1):
        x0, _ = _lonlat_to_tile(lon_min, lat_max, z)
        x1, _ = _lonlat_to_tile(lon_max, lat_min, z)
        _, y0 = _lonlat_to_tile(lon_min, lat_max, z)
        _, y1 = _lonlat_to_tile(lon_max, lat_min, z)
        if (int(x1) - int(x0) + 1) <= max_tiles and (int(y1) - int(y0) + 1) <= max_tiles:
            return z
    return 1


def _get_tile(z, x, y, url_tmpl, prefix):
    path = os.path.join(_CACHE, f"{prefix}_{z}_{x}_{y}.png")
    if os.path.exists(path):
        try:
            return Image.open(path).convert("RGB")
        except Exception:
            pass
    url = url_tmpl.format(z=z, x=x, y=y)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "MTB-DataLogger-Analyzer"})
        data = urllib.request.urlopen(req, timeout=8).read()
        img = Image.open(io.BytesIO(data)).convert("RGB")
        os.makedirs(_CACHE, exist_ok=True)
        img.save(path)
        return img
    except Exception:
        return None


def _tile_range(lat_min, lat_max, lon_min, lon_max, pad):
    """Tile grid + Web-Mercator extent for a padded bbox. The zoom/grid depend
    only on the bbox, so satellite and DEM fetches share an identical extent."""
    dlon = (lon_max - lon_min) or 1e-3
    dlat = (lat_max - lat_min) or 1e-3
    lon_min -= dlon * pad; lon_max += dlon * pad
    lat_min -= dlat * pad; lat_max += dlat * pad
    z = _pick_zoom(lon_min, lon_max, lat_min, lat_max)
    x0, _ = _lonlat_to_tile(lon_min, lat_max, z)
    x1, _ = _lonlat_to_tile(lon_max, lat_min, z)
    _, y0 = _lonlat_to_tile(lon_min, lat_max, z)
    _, y1 = _lonlat_to_tile(lon_max, lat_min, z)
    x0, x1 = int(math.floor(x0)), int(math.floor(x1))
    y0, y1 = int(math.floor(y0)), int(math.floor(y1))
    left, top = _tile_merc_bounds(x0, y0, z)
    right, bottom = _tile_merc_bounds(x1 + 1, y1 + 1, z)
    return z, x0, x1, y0, y1, (left, right, bottom, top)


def _fetch_mosaic(z, x0, x1, y0, y1, url_tmpl, prefix):
    mosaic = Image.new("RGB", ((x1 - x0 + 1) * _TILE, (y1 - y0 + 1) * _TILE))
    for ix in range(x0, x1 + 1):
        for iy in range(y0, y1 + 1):
            tile = _get_tile(z, ix, iy, url_tmpl, prefix)
            if tile is None:
                return None
            mosaic.paste(tile, ((ix - x0) * _TILE, (iy - y0) * _TILE))
    return mosaic


def fetch_satellite_basemap(lat_min, lat_max, lon_min, lon_max, pad=0.18):
    """Return (image_ndarray, (left, right, bottom, top)_mercator) covering the
    padded bbox, or None if any tile could not be fetched (e.g. offline)."""
    z, x0, x1, y0, y1, extent = _tile_range(lat_min, lat_max, lon_min, lon_max, pad)
    mosaic = _fetch_mosaic(z, x0, x1, y0, y1, _SAT_URL, "sat")
    return (np.asarray(mosaic), extent) if mosaic is not None else None


def fetch_elevation_grid(lat_min, lat_max, lon_min, lon_max, pad=0.18):
    """Return (elevation_metres_2d, (left, right, bottom, top)_mercator) decoded
    from Terrarium DEM tiles over the SAME tile grid as the satellite basemap, or
    None if offline. Decode: elev = R*256 + G + B/256 - 32768."""
    z, x0, x1, y0, y1, extent = _tile_range(lat_min, lat_max, lon_min, lon_max, pad)
    mosaic = _fetch_mosaic(z, x0, x1, y0, y1, _DEM_URL, "dem")
    if mosaic is None:
        return None
    a = np.asarray(mosaic).astype(np.float64)
    elev = a[:, :, 0] * 256.0 + a[:, :, 1] + a[:, :, 2] / 256.0 - 32768.0
    return elev, extent
