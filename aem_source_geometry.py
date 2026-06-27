"""Framework-free geometry algorithms from the reference AEM source designer."""

import math

import numpy as np
from shapely.geometry import Point, Polygon as ShapelyPolygon


DEFAULT_CONC = 10.0
MIN_RADIUS = 0.003


def _distance_to_boundary(x, y, poly):
    """Signed distance from (x,y) to polygon boundary (positive = inside)."""
    p = Point(x, y)
    d = poly.exterior.distance(p)
    return d if poly.contains(p) else -d


def _max_radius_at(x, y, placed, poly, abs_max=0.06):
    """Largest radius at (x,y) that doesn't overlap anything."""
    r = _distance_to_boundary(x, y, poly)
    if r <= 0:
        return 0
    for cx, cy, cr in placed:
        r = min(r, math.hypot(x - cx, y - cy) - cr)
        if r <= MIN_RADIUS:
            return 0
    return min(r, abs_max)


def greedy_circle_pack(vertices, default_c=DEFAULT_CONC, max_circles=80):
    """
    Greedy packing: scatter candidate points, repeatedly place the largest
    possible circle, then re-evaluate. Produces varied circle sizes.
    """
    poly = ShapelyPolygon(vertices)
    if not poly.is_valid or poly.area == 0:
        return []

    minx, miny, maxx, maxy = poly.bounds
    abs_max_r = min(maxx - minx, maxy - miny) * 0.25

    placed = []
    circles = []

    step = MIN_RADIUS * 2
    cand_xs = np.arange(minx + MIN_RADIUS, maxx - MIN_RADIUS + step, step)
    cand_ys = np.arange(miny + MIN_RADIUS, maxy - MIN_RADIUS + step, step)
    candidates = []
    for x in cand_xs:
        for y in cand_ys:
            if poly.contains(Point(x, y)):
                candidates.append((x, y))

    for _ in range(max_circles):
        best_r, best_x, best_y = 0, 0, 0
        surviving = []
        for (x, y) in candidates:
            r = _max_radius_at(x, y, placed, poly, abs_max_r)
            if r > MIN_RADIUS:
                surviving.append((x, y))
                if r > best_r:
                    best_r, best_x, best_y = r, x, y
        candidates = surviving
        if best_r <= MIN_RADIUS:
            break
        placed.append((best_x, best_y, best_r))
        circles.append({"x": round(best_x, 5), "y": round(best_y, 5),
                        "r": round(best_r, 5), "c": default_c})

    return circles


def repack_after_resize(circles, changed_idx, polygon_vertices):
    """
    After one circle is resized, resolve overlaps (push apart) then grow
    neighbours into any freed space. The changed circle stays fixed.
    """
    poly = ShapelyPolygon(polygon_vertices)
    if not poly.is_valid:
        return circles

    for _it in range(80):
        moved = False
        for i in range(len(circles)):
            for j in range(i + 1, len(circles)):
                ci, cj = circles[i], circles[j]
                dx = ci["x"] - cj["x"]
                dy = ci["y"] - cj["y"]
                dist = math.hypot(dx, dy)
                need = ci["r"] + cj["r"]
                if dist < need and dist > 1e-9:
                    overlap = need - dist
                    nx, ny = dx / dist, dy / dist
                    if i == changed_idx:
                        cj["x"] = round(cj["x"] - nx * overlap, 5)
                        cj["y"] = round(cj["y"] - ny * overlap, 5)
                    elif j == changed_idx:
                        ci["x"] = round(ci["x"] + nx * overlap, 5)
                        ci["y"] = round(ci["y"] + ny * overlap, 5)
                    else:
                        ci["x"] = round(ci["x"] + nx * overlap * 0.5, 5)
                        ci["y"] = round(ci["y"] + ny * overlap * 0.5, 5)
                        cj["x"] = round(cj["x"] - nx * overlap * 0.5, 5)
                        cj["y"] = round(cj["y"] - ny * overlap * 0.5, 5)
                    moved = True
        for i, ci in enumerate(circles):
            if i == changed_idx:
                continue
            p = Point(ci["x"], ci["y"])
            if not poly.contains(p):
                nearest = poly.exterior.interpolate(poly.exterior.project(p))
                ci["x"] = round((ci["x"] + nearest.x) / 2, 5)
                ci["y"] = round((ci["y"] + nearest.y) / 2, 5)
                moved = True
            while ci["r"] > MIN_RADIUS and not poly.contains(
                    Point(ci["x"], ci["y"]).buffer(ci["r"] * 0.8)):
                ci["r"] = round(ci["r"] * 0.9, 5)
                moved = True
        if not moved:
            break

    changed_obj = circles[changed_idx]
    circles = [c for i, c in enumerate(circles)
               if c["r"] >= MIN_RADIUS and (
                   c is changed_obj or poly.contains(Point(c["x"], c["y"])))]
    changed_idx = next(i for i, c in enumerate(circles) if c is changed_obj)

    ch = circles[changed_idx]
    for _round in range(40):
        grew = False
        for i, ci in enumerate(circles):
            if i == changed_idx:
                continue
            max_r = _distance_to_boundary(ci["x"], ci["y"], poly)
            for j, cj in enumerate(circles):
                if j == i:
                    continue
                gap = math.hypot(ci["x"] - cj["x"], ci["y"] - cj["y"]) - cj["r"]
                max_r = min(max_r, gap)
            target = max_r * 0.95
            if target > ci["r"] + 0.0002:
                ci["r"] = round(ci["r"] + (target - ci["r"]) * 0.6, 5)
                grew = True

            dx = ch["x"] - ci["x"]
            dy = ch["y"] - ci["y"]
            dist_to_ch = math.hypot(dx, dy)
            if dist_to_ch < 1e-9:
                continue
            edge_gap = dist_to_ch - ci["r"] - ch["r"]
            if edge_gap > 0.001:
                step = min(edge_gap * 0.3, 0.002)
                nx, ny = dx / dist_to_ch, dy / dist_to_ch
                new_x = ci["x"] + nx * step
                new_y = ci["y"] + ny * step
                if poly.contains(Point(new_x, new_y).buffer(ci["r"] * 0.8)):
                    ok = True
                    for j, cj in enumerate(circles):
                        if j == i or j == changed_idx:
                            continue
                        if math.hypot(new_x - cj["x"], new_y - cj["y"]) < ci["r"] + cj["r"]:
                            ok = False
                            break
                    if ok:
                        ci["x"] = round(new_x, 5)
                        ci["y"] = round(new_y, 5)
                        grew = True
        if not grew:
            break

    return circles
