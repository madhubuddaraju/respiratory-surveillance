"""
One-off build step: convert us-atlas `states-albers-10m.json` (TopoJSON, pre-projected to
Albers USA, 975x610) into SVG path strings per state FIPS code, stored in us_states.json.

    npm pack us-atlas@3.0.1 && tar xzf us-atlas-3.0.1.tgz
    python src/surveil/geo/build_paths.py package/states-albers-10m.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def decode_arcs(topo: dict) -> list[list[tuple[float, float]]]:
    (sx, sy), (tx, ty) = topo["transform"]["scale"], topo["transform"]["translate"]
    arcs = []
    for arc in topo["arcs"]:
        x = y = 0
        pts = []
        for dx, dy in arc:
            x, y = x + dx, y + dy
            pts.append((x * sx + tx, y * sy + ty))
        arcs.append(pts)
    return arcs


def ring(arcs, idxs) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    for i in idxs:
        a = arcs[i] if i >= 0 else arcs[~i][::-1]
        pts.extend(a if not pts else a[1:])
    return pts


def area(r) -> float:
    return 0.5 * sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(r, r[1:] + r[:1], strict=True))


def centroid(r) -> tuple[float, float]:
    a = area(r) or 1e-9
    cx = sum((x0 + x1) * (x0 * y1 - x1 * y0) for (x0, y0), (x1, y1) in zip(r, r[1:] + r[:1], strict=True)) / (6 * a)
    cy = sum((y0 + y1) * (x0 * y1 - x1 * y0) for (x0, y0), (x1, y1) in zip(r, r[1:] + r[:1], strict=True)) / (6 * a)
    return cx, cy


# hand-placed label anchors where the polygon centroid falls outside the visible land shape
LABEL_OVERRIDES = {"12": [805, 548], "22": [570, 488], "26": [693, 230]}


def main(src: str) -> None:
    topo = json.loads(Path(src).read_text())
    arcs = decode_arcs(topo)
    out = {}
    for g in topo["objects"]["states"]["geometries"]:
        polys = g["arcs"] if g["type"] == "MultiPolygon" else [g["arcs"]]
        d, rings = [], []
        for poly in polys:
            for r in poly:
                pts = ring(arcs, r)
                rings.append(pts)
                d.append("M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + "Z")
        biggest = max(rings, key=lambda r: abs(area(r)))
        xs, ys = [p[0] for p in biggest], [p[1] for p in biggest]
        out[g["id"]] = {"name": g["properties"]["name"], "d": "".join(d),
                        "label": LABEL_OVERRIDES.get(g["id"], [round(v, 1) for v in centroid(biggest)]),
                        "size": round(min(max(xs) - min(xs), max(ys) - min(ys)), 1)}
    dest = Path(__file__).with_name("us_states.json")
    dest.write_text(json.dumps(out, separators=(",", ":")))
    print(f"wrote {dest} ({dest.stat().st_size / 1024:.0f} KB, {len(out)} states)")


if __name__ == "__main__":
    main(sys.argv[1])
