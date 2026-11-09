"""Build docs/people.json: a dot map where every dot is one synthetic persona.

Each sampled persona is placed at a random point inside its municipality. Municipality
outlines (okfse/sweden-geojson, derived from Valmyndigheten data) are downloaded to
data/geo/ and used only to position dots; the outlines are not republished. A faint
grid of "land" points is exported so the country shape reads even where people are few.
"""

import json
import math
import random
import urllib.request
from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
GEO = ROOT / "data/geo/swedish_municipalities.geojson"
URL = "https://raw.githubusercontent.com/okfse/sweden-geojson/master/swedish_municipalities.geojson"
N = 6000
SEED = 7
LAT0 = 62.0
KX = math.cos(math.radians(LAT0))


def load_geo():
    if not GEO.exists():
        GEO.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(URL, timeout=60) as response:
            GEO.write_bytes(response.read())
    return json.loads(GEO.read_text(encoding="utf-8"))["features"]


def polygons(feature):
    geometry = feature["geometry"]
    return [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]


def inside(poly, x, y):
    """Even-odd rule over all rings (outer ring plus holes)."""
    hit = False
    for ring in poly:
        j = len(ring) - 1
        for i in range(len(ring)):
            xi, yi = ring[i]
            xj, yj = ring[j]
            if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                hit = not hit
            j = i
    return hit


def sampler(feature):
    polys = polygons(feature)
    boxes = []
    for poly in polys:
        xs = [p[0] for p in poly[0]]
        ys = [p[1] for p in poly[0]]
        boxes.append((min(xs), max(xs), min(ys), max(ys), (max(xs) - min(xs)) * (max(ys) - min(ys))))
    def draw(rng):
        for _ in range(500):
            k = rng.choices(range(len(polys)), weights=[b[4] for b in boxes])[0]
            x0, x1, y0, y1, _ = boxes[k]
            x, y = rng.uniform(x0, x1), rng.uniform(y0, y1)
            if inside(polys[k], x, y):
                return x, y
        x0, x1, y0, y1, _ = boxes[0]
        return (x0 + x1) / 2, (y0 + y1) / 2
    return draw


def main():
    features = load_geo()
    by_id = {f["properties"]["id"]: f for f in features}
    names = {f["properties"]["kom_namn"]: f["properties"]["id"] for f in features}
    draw = {k: sampler(f) for k, f in by_id.items()}

    rows = pq.read_table(ROOT / "data/swedish_personas_100k.parquet").to_pylist()
    cond_counts = Counter(c["uuid"] for c in pq.read_table(ROOT / "data/swedish_personas_100k_conditions.parquet").to_pylist())
    rng = random.Random(SEED)
    picked = rng.sample(rows, N)

    lans = sorted({r["lan"] for r in rows})
    kommuner = sorted({r["kommun"] for r in rows})
    occupations = sorted({r["occupation"] for r in picked})
    lan_idx = {v: i for i, v in enumerate(lans)}
    kom_idx = {v: i for i, v in enumerate(kommuner)}
    occ_idx = {v: i for i, v in enumerate(occupations)}

    pts = []
    for r in picked:
        lon, lat = draw[names[r["kommun"]]](rng)
        pts.append((lon * KX, lat, r))
    # land mask: a coarse grid kept where it falls inside any municipality
    min_x, min_y = 11.0 * KX, 55.2
    max_x, max_y = 24.2 * KX, 69.1
    for f in features:
        for poly in polygons(f):
            for ring in poly:
                for lon, lat in ring:
                    min_x, max_x = min(min_x, lon * KX), max(max_x, lon * KX)
                    min_y, max_y = min(min_y, lat), max(max_y, lat)
    w, h = max_x - min_x, max_y - min_y
    q = 65535
    def px(x):
        return round((x - min_x) / w * q)
    def py(y):
        return round((max_y - y) / h * q)

    step = 0.085
    boxed = []
    for f in features:
        for poly in polygons(f):
            xs_, ys_ = [v[0] for v in poly[0]], [v[1] for v in poly[0]]
            boxed.append((min(xs_), max(xs_), min(ys_), max(ys_), poly))
    land = []
    lat = min_y
    while lat < max_y:
        lon = min_x / KX
        while lon < max_x / KX:
            if any(b[0] <= lon <= b[1] and b[2] <= lat <= b[3] and inside(b[4], lon, lat) for b in boxed):
                land.extend([px(lon * KX), py(lat)])
            lon += step / KX
        lat += step

    out = {
        "aspect": round(w / h, 4),
        "x": [px(p[0]) for p in pts], "y": [py(p[1]) for p in pts],
        "age": [p[2]["age"] for p in pts],
        "sex": [0 if p[2]["sex"] == "Man" else 1 for p in pts],
        "lan": [lan_idx[p[2]["lan"]] for p in pts],
        "cond": [min(3, cond_counts.get(p[2]["uuid"], 0)) for p in pts],
        "kom": [kom_idx[p[2]["kommun"]] for p in pts],
        "occ": [occ_idx[p[2]["occupation"]] for p in pts],
        "name": [p[2]["professional_persona"].split(" ")[0] + " " + p[2]["professional_persona"].split(" ")[1] for p in pts],
        "txt": [p[2]["professional_persona"] for p in pts],
        "health": [p[2]["healthcare_persona"] for p in pts],
        "lans": lans, "kommuner": kommuner, "occupations": occupations,
        "land": land,
    }
    (ROOT / "docs/people.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote docs/people.json with {N} dots and {len(land) // 2} land points")


if __name__ == "__main__":
    main()
