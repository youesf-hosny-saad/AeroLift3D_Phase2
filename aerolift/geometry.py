"""Parametric geometry generation for the conceptual trainer aircraft.

Every public ``build_*`` function creates one component independently and
returns a triangulated ``pyvista.PolyData``. No GUI or aerodynamics code
is used here.

Coordinate convention (right-handed, metres):
    X longitudinal, positive AFT (nose at X = 0)
    Y lateral, positive to the pilot's right (starboard)
    Z vertical, positive UP

The geometry is a CONCEPTUAL visualisation, not a validated aircraft design.
"""
from __future__ import annotations

import math

import numpy as np
import pyvista as pv

from .aircraft_model import (
    AircraftConfig, EngineParams, FuselageParams, GeometryError,
    HorizontalStabParams, PropellerParams, VerticalStabParams, WingParams,
)

COMPONENTS = ("fuselage", "wing", "htail", "vtail", "engine", "propeller")


# --------------------------------------------------------------------------
# Generic helpers
# --------------------------------------------------------------------------
def _fan_cap(points: np.ndarray) -> pv.PolyData:
    """Planar polygon face from an ordered ring of points."""
    n = len(points)
    faces = np.hstack([[n], np.arange(n)])
    return pv.PolyData(np.asarray(points, dtype=float), faces).triangulate()


def _finish(mesh: pv.PolyData, split: bool) -> pv.PolyData:
    """Clean, triangulate and attach normals."""
    mesh = mesh.triangulate().clean(tolerance=1e-9)
    return mesh.compute_normals(
        cell_normals=False, point_normals=True, split_vertices=split,
        feature_angle=50.0, consistent_normals=True, auto_orient_normals=False,
    )


def _loft(sections: np.ndarray, cap_ends: bool = True, split: bool = True) -> pv.PolyData:
    """Skin a stack of closed cross-sections, shape (n_stations, n_pts, 3)."""
    n_st, n_pt, _ = sections.shape
    closed = np.concatenate([sections, sections[:, :1, :]], axis=1)
    grid = pv.StructuredGrid()
    grid.points = closed.reshape(-1, 3)
    grid.dimensions = (n_pt + 1, n_st, 1)
    skin = grid.extract_surface(algorithm=None)
    if cap_ends:
        skin = skin.merge([_fan_cap(sections[0]), _fan_cap(sections[-1])])
    return _finish(skin, split)


def _revolve(xs, rs, n_theta: int = 56) -> pv.PolyData:
    """Surface of revolution about the X axis from a radius profile r(x)."""
    xs = np.asarray(xs, float)
    rs = np.asarray(rs, float)
    theta = np.linspace(0.0, 2.0 * np.pi, n_theta, endpoint=False)
    sections = np.zeros((len(xs), n_theta, 3))
    sections[:, :, 0] = xs[:, None]
    sections[:, :, 1] = rs[:, None] * np.cos(theta)[None, :]
    sections[:, :, 2] = rs[:, None] * np.sin(theta)[None, :]
    grid = pv.StructuredGrid()
    closed = np.concatenate([sections, sections[:, :1, :]], axis=1)
    grid.points = closed.reshape(-1, 3)
    grid.dimensions = (n_theta + 1, len(xs), 1)
    skin = grid.extract_surface(algorithm=None)
    caps = []
    for idx in (0, -1):
        if rs[idx] > 1e-6:
            caps.append(_fan_cap(sections[idx]))
    if caps:
        skin = skin.merge(caps)
    return _finish(skin, split=True)


def _airfoil_loop(n_side: int = 24) -> tuple[np.ndarray, np.ndarray]:
    """Unit-chord symmetric (NACA 00xx style) loop: x/c and half-thickness/t."""
    beta = np.linspace(0.0, np.pi, n_side)
    x = 0.5 * (1.0 - np.cos(beta))          # 0 -> 1, dense at LE and TE
    # NACA 4-digit thickness per unit thickness ratio; last coefficient closes TE.
    yt = 5.0 * (0.2969 * np.sqrt(x) - 0.1260 * x - 0.3516 * x**2
                + 0.2843 * x**3 - 0.1036 * x**4)
    xc = np.concatenate([x[::-1], x[1:]])    # upper TE -> LE, lower LE -> TE
    zc = np.concatenate([yt[::-1], -yt[1:]])
    return xc, zc


# --------------------------------------------------------------------------
# Components
# --------------------------------------------------------------------------
def fuselage_profile(p: FuselageParams, n_nose=26, n_cabin=8, n_tail=44):
    tail_start = p.length_m - p.tail_length_m
    xs = np.unique(np.concatenate([
        np.linspace(0.0, p.nose_length_m, n_nose),
        np.linspace(p.nose_length_m, tail_start, n_cabin),
        np.linspace(tail_start, p.length_m, n_tail),
    ]))
    rs = np.array([p.radius_at(float(x)) for x in xs])
    return xs, rs


def build_fuselage(p: FuselageParams) -> pv.PolyData:
    """Smooth body of revolution: tapered nose, cylindrical cabin, tapered tail."""
    xs, rs = fuselage_profile(p)
    return _revolve(xs, rs)


def build_lifting_surface(
    span_m: float, root_chord_m: float, taper_ratio: float,
    quarter_chord_sweep_deg: float, dihedral_deg: float, incidence_deg: float,
    thickness_ratio: float, x_root_le_m: float, z_root_m: float,
    vertical: bool = False, n_span: int = 21, n_chord: int = 24,
) -> pv.PolyData:
    """Trapezoidal lifting surface lofted from symmetric airfoil sections.

    * Horizontal (``vertical=False``): both halves, span = tip-to-tip
      projected span, chord measured in the X direction. Projected planform
      area is exactly ``span/2 * (c_root + c_tip)``.
    * Vertical: one-sided, span = height measured along +Z from ``z_root_m``.
    Sweep is about the quarter-chord line; incidence is nose-up positive,
    rotating about the local quarter chord.
    """
    half = span_m if vertical else 0.5 * span_m
    if vertical:
        s = np.linspace(0.0, half, n_span)
    else:
        s = np.concatenate([-np.linspace(half, 0.0, n_span)[:-1],
                            np.linspace(0.0, half, n_span)])
    a = np.abs(s)
    chord = root_chord_m * (1.0 - (1.0 - taper_ratio) * a / half)
    xq = x_root_le_m + 0.25 * root_chord_m + a * math.tan(math.radians(quarter_chord_sweep_deg))
    zq = z_root_m + (s if vertical else a * math.tan(math.radians(dihedral_deg)))

    xc, zc = _airfoil_loop(n_chord)
    inc = math.radians(0.0 if vertical else incidence_deg)
    ci, si = math.cos(inc), math.sin(inc)
    xl = (xc[None, :] - 0.25) * chord[:, None]          # relative to quarter chord
    zl = zc[None, :] * thickness_ratio * chord[:, None]
    x_r = xl * ci + zl * si
    z_r = zl * ci - xl * si                              # nose-up for X aft

    sec = np.zeros((len(s), len(xc), 3))
    sec[:, :, 0] = xq[:, None] + x_r
    if vertical:
        sec[:, :, 1] = z_r
        sec[:, :, 2] = zq[:, None]
    else:
        sec[:, :, 1] = s[:, None]
        sec[:, :, 2] = zq[:, None] + z_r
    return _loft(sec, cap_ends=True, split=True)


def build_wing(p: WingParams) -> pv.PolyData:
    return build_lifting_surface(
        p.span_m, p.root_chord_m, p.taper_ratio, p.quarter_chord_sweep_deg,
        p.dihedral_deg, p.incidence_deg, p.thickness_ratio,
        p.x_root_leading_edge_m, p.z_position_m, vertical=False, n_span=26)


def build_horizontal_stabilizer(p: HorizontalStabParams) -> pv.PolyData:
    return build_lifting_surface(
        p.span_m, p.root_chord_m, p.taper_ratio, p.quarter_chord_sweep_deg,
        0.0, p.incidence_deg, p.thickness_ratio,
        p.x_root_leading_edge_m, p.z_position_m, vertical=False, n_span=14)


def vertical_stab_base_z(fus: FuselageParams, p: VerticalStabParams) -> float:
    """Root height: slightly inside the fuselage skin at the fin mid-root."""
    return 0.5 * fus.radius_at(p.x_root_leading_edge_m + 0.5 * p.root_chord_m)


def build_vertical_stabilizer(fus: FuselageParams, p: VerticalStabParams) -> pv.PolyData:
    return build_lifting_surface(
        p.height_m, p.root_chord_m, p.taper_ratio, p.quarter_chord_sweep_deg,
        0.0, 0.0, p.thickness_ratio, p.x_root_leading_edge_m,
        vertical_stab_base_z(fus, p), vertical=True, n_span=14)


def engine_front_x(e: EngineParams) -> float:
    return -e.protrusion_m


def build_engine(fus: FuselageParams, e: EngineParams, prop: PropellerParams) -> pv.PolyData:
    """Cowling: rounded front lip, cylindrical barrel, mounted ahead of the nose."""
    x0 = engine_front_x(e)
    r_cowl = e.cowling_radius_ratio * fus.max_radius_m
    r_front = min(prop.hub_radius_m, 0.8 * r_cowl)
    lip = 0.4 * e.cowling_length_m
    xs = np.unique(np.concatenate([
        np.linspace(x0, x0 + lip, 14), np.linspace(x0 + lip, x0 + e.cowling_length_m, 6)]))
    t = np.clip((xs - x0) / lip, 0.0, 1.0)
    rs = r_front + (r_cowl - r_front) * np.sin(0.5 * np.pi * t)
    return _revolve(xs, rs)


def build_propeller(fus: FuselageParams, e: EngineParams, p: PropellerParams) -> pv.PolyData:
    """Spinner/hub plus a two-blade propeller (visual twist, no performance data)."""
    x_base = engine_front_x(e)
    l_hub = 0.35 * p.spinner_length_m
    l_ogive = p.spinner_length_m - l_hub
    t = np.linspace(0.0, 1.0, 16)
    xs_og = x_base - l_hub - t * l_ogive
    rs_og = p.hub_radius_m * np.clip(1.0 - t**2, 0.0, 1.0) ** 0.6
    xs = np.concatenate([[x_base, x_base - l_hub], xs_og[1:]])[::-1]
    rs = np.concatenate([[p.hub_radius_m, p.hub_radius_m], rs_og[1:]])[::-1]
    spinner = _revolve(xs, rs, n_theta=40)

    x_plane = x_base - 0.5 * l_hub
    r_root = 0.7 * p.hub_radius_m
    r_tip = 0.5 * p.diameter_m
    stations = np.linspace(r_root, r_tip, 16)
    frac = (stations - r_root) / (r_tip - r_root)
    chord = p.blade_root_chord_m + (p.blade_tip_chord_m - p.blade_root_chord_m) * frac
    # Pitch angle from the plane of rotation: 14 deg at tip, more at root.
    pitch = np.radians(14.0 + p.blade_twist_deg * (1.0 - frac))
    xc, zc = _airfoil_loop(14)
    blades = []
    for k in range(2):
        az = math.radians(p.azimuth_deg + 180.0 * k)
        radial = np.array([0.0, math.cos(az), math.sin(az)])
        tang = np.array([0.0, -math.sin(az), math.cos(az)])
        xhat = np.array([1.0, 0.0, 0.0])
        sec = np.zeros((len(stations), len(xc), 3))
        for i, r in enumerate(stations):
            cdir = math.cos(pitch[i]) * tang + math.sin(pitch[i]) * xhat
            ndir = -math.sin(pitch[i]) * tang + math.cos(pitch[i]) * xhat
            u = (xc - 0.5)[:, None] * chord[i] * cdir[None, :]
            w = (zc * 0.10 * chord[i])[:, None] * ndir[None, :]
            sec[i] = np.array([x_plane, 0.0, 0.0]) + r * radial + u + w
        blades.append(_loft(sec, cap_ends=True, split=True))
    return spinner.merge(blades)


# --------------------------------------------------------------------------
# Validation and assembly
# --------------------------------------------------------------------------
def validate_mesh(name: str, mesh: pv.PolyData) -> pv.PolyData:
    """Reject empty, non-finite or degenerate meshes before rendering."""
    if mesh is None or mesh.n_points == 0 or mesh.n_cells == 0:
        raise GeometryError(f"{name}: generated mesh is empty.")
    if not np.all(np.isfinite(mesh.points)):
        raise GeometryError(f"{name}: generated mesh contains non-finite coordinates.")
    b = mesh.bounds
    if min(b[1] - b[0], b[3] - b[2], b[5] - b[4]) <= 0.0:
        raise GeometryError(f"{name}: generated mesh is degenerate (zero extent).")
    return mesh


def build_aircraft(config: AircraftConfig) -> tuple[dict[str, pv.PolyData], list[str]]:
    """Validate parameters, then generate all components independently.

    Returns ({component_name: mesh}, warnings). Raises GeometryError and
    produces no meshes if the configuration is invalid.
    """
    warnings = config.validate()
    builders = {
        "fuselage": lambda: build_fuselage(config.fuselage),
        "wing": lambda: build_wing(config.wing),
        "htail": lambda: build_horizontal_stabilizer(config.htail),
        "vtail": lambda: build_vertical_stabilizer(config.fuselage, config.vtail),
        "engine": lambda: build_engine(config.fuselage, config.engine, config.propeller),
        "propeller": lambda: build_propeller(config.fuselage, config.engine, config.propeller),
    }
    meshes = {name: validate_mesh(name, fn()) for name, fn in builders.items()}
    return meshes, warnings


def measured_planform_area(mesh: pv.PolyData, n_bins: int = 400) -> float:
    """Projected (top-view) area of an un-twisted horizontal surface from its mesh.

    Integrates chord(y) = max(x) - min(x) over y. Used by the geometry test to
    prove the mesh matches the declared area (valid for zero incidence).
    """
    pts = mesh.points
    ys = np.unique(np.round(pts[:, 1], 9))
    chords = np.array([np.ptp(pts[np.isclose(pts[:, 1], y, atol=1e-8), 0]) for y in ys])
    return float(np.trapezoid(chords, ys))
