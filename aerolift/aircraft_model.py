"""Aircraft configuration and component parameters (no GUI, no rendering).

Coordinate convention (right-handed, SI units, metres):
    X : longitudinal axis, positive AFT. Nose is at X = 0 (fuselage station).
    Y : lateral axis, positive to the pilot's RIGHT (starboard).
    Z : vertical axis, positive UP. Fuselage centreline is Z = 0.

The wing is defined by span b, mean geometric chord c_bar and taper ratio.
Area is always DERIVED (S = b * c_bar = b/2 * (c_root + c_tip)), so the
displayed area and the generated geometry can never disagree.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math


class GeometryError(ValueError):
    """Raised when aircraft parameters are physically or geometrically invalid."""

    def __init__(self, problems):
        self.problems = list(problems) if not isinstance(problems, str) else [problems]
        super().__init__("; ".join(self.problems))


def _finite(*values) -> bool:
    return all(isinstance(v, (int, float)) and math.isfinite(v) for v in values)


def trapezoid_chords(mean_chord: float, taper: float) -> tuple[float, float]:
    """Return (root, tip) chord for a mean chord and taper ratio ct/cr.

    From S = b/2 (cr + ct) = b * c_bar  ->  cr = 2 c_bar / (1 + taper).
    """
    root = 2.0 * mean_chord / (1.0 + taper)
    return root, root * taper


@dataclass
class FuselageParams:
    length_m: float = 7.0
    max_diameter_m: float = 1.2
    nose_length_m: float = 1.4
    tail_length_m: float = 3.2
    nose_start_radius_ratio: float = 0.78   # radius at X=0 relative to max radius
    tail_end_radius_ratio: float = 0.06     # radius at the tail tip

    @property
    def max_radius_m(self) -> float:
        return 0.5 * self.max_diameter_m

    @property
    def cabin_length_m(self) -> float:
        return self.length_m - self.nose_length_m - self.tail_length_m

    def radius_at(self, x: float) -> float:
        """Fuselage radius at station x (shared by geometry and tail placement)."""
        r_max = self.max_radius_m
        r0 = self.nose_start_radius_ratio * r_max
        r1 = self.tail_end_radius_ratio * r_max
        if x <= 0.0:
            return r0
        if x < self.nose_length_m:
            t = x / self.nose_length_m
            return r0 + (r_max - r0) * math.sin(0.5 * math.pi * t)  # smooth blend
        tail_start = self.length_m - self.tail_length_m
        if x <= tail_start:
            return r_max
        if x < self.length_m:
            t = (x - tail_start) / self.tail_length_m
            s = 0.5 * (1.0 + math.cos(math.pi * t))  # 1 -> 0, zero slope at both ends
            return r1 + (r_max - r1) * s ** 0.8
        return r1


@dataclass
class WingParams:
    span_m: float = 10.0
    mean_chord_m: float = 1.4
    taper_ratio: float = 0.75
    quarter_chord_sweep_deg: float = 0.0
    dihedral_deg: float = 3.0
    incidence_deg: float = 2.0
    thickness_ratio: float = 0.12
    x_root_leading_edge_m: float = 2.3
    z_position_m: float = -0.35   # root chord-line height relative to fuselage axis

    @property
    def area_m2(self) -> float:
        return self.span_m * self.mean_chord_m

    @property
    def root_chord_m(self) -> float:
        return trapezoid_chords(self.mean_chord_m, self.taper_ratio)[0]

    @property
    def tip_chord_m(self) -> float:
        return trapezoid_chords(self.mean_chord_m, self.taper_ratio)[1]

    @property
    def planform_area_m2(self) -> float:
        """S = b/2 (cr + ct); equals span * mean chord by construction."""
        return 0.5 * self.span_m * (self.root_chord_m + self.tip_chord_m)

    @property
    def aspect_ratio(self) -> float:
        return self.span_m ** 2 / self.area_m2

    # --- the two independent ways to change wing area -------------------
    def set_area_keep_span(self, area_m2: float) -> None:
        """Change area by changing chord; wingspan is held constant."""
        self.mean_chord_m = area_m2 / self.span_m

    def set_area_keep_chord(self, area_m2: float) -> None:
        """Change area by changing wingspan; mean chord (and taper) are held."""
        self.span_m = area_m2 / self.mean_chord_m


@dataclass
class HorizontalStabParams:
    span_m: float = 3.2
    area_m2: float = 2.6
    taper_ratio: float = 0.6
    quarter_chord_sweep_deg: float = 5.0
    incidence_deg: float = -1.0
    thickness_ratio: float = 0.10
    x_root_leading_edge_m: float = 5.75
    z_position_m: float = 0.12

    @property
    def mean_chord_m(self) -> float:
        return self.area_m2 / self.span_m

    @property
    def root_chord_m(self) -> float:
        return trapezoid_chords(self.mean_chord_m, self.taper_ratio)[0]

    @property
    def tip_chord_m(self) -> float:
        return trapezoid_chords(self.mean_chord_m, self.taper_ratio)[1]


@dataclass
class VerticalStabParams:
    height_m: float = 1.4
    root_chord_m: float = 1.3
    taper_ratio: float = 0.55
    quarter_chord_sweep_deg: float = 28.0
    thickness_ratio: float = 0.09
    x_root_leading_edge_m: float = 5.0

    @property
    def tip_chord_m(self) -> float:
        return self.root_chord_m * self.taper_ratio

    @property
    def area_m2(self) -> float:
        return 0.5 * self.height_m * (self.root_chord_m + self.tip_chord_m)


@dataclass
class EngineParams:
    cowling_length_m: float = 0.9
    cowling_radius_ratio: float = 0.78   # relative to fuselage max radius
    protrusion_m: float = 0.7            # how far the cowling nose is ahead of X=0


@dataclass
class PropellerParams:
    diameter_m: float = 1.75
    hub_radius_m: float = 0.12
    spinner_length_m: float = 0.3
    blade_root_chord_m: float = 0.16
    blade_tip_chord_m: float = 0.07
    blade_twist_deg: float = 20.0        # root-to-tip pitch reduction (visual only)
    azimuth_deg: float = 90.0            # blade position (90 = blades vertical)


@dataclass
class AircraftConfig:
    fuselage: FuselageParams = field(default_factory=FuselageParams)
    wing: WingParams = field(default_factory=WingParams)
    htail: HorizontalStabParams = field(default_factory=HorizontalStabParams)
    vtail: VerticalStabParams = field(default_factory=VerticalStabParams)
    engine: EngineParams = field(default_factory=EngineParams)
    propeller: PropellerParams = field(default_factory=PropellerParams)

    @property
    def wing_area_m2(self) -> float:
        """The single source of wing area used by the aerodynamics module."""
        return self.wing.area_m2

    def validate(self) -> list[str]:
        """Raise GeometryError on invalid input; return a list of soft warnings."""
        f, w, h, v, e, p = (self.fuselage, self.wing, self.htail,
                            self.vtail, self.engine, self.propeller)
        errors: list[str] = []
        warnings: list[str] = []

        for name, obj in (("fuselage", f), ("wing", w), ("horizontal stabilizer", h),
                          ("vertical stabilizer", v), ("engine", e), ("propeller", p)):
            if not _finite(*vars(obj).values()):
                errors.append(f"All {name} parameters must be finite numbers.")
        if errors:
            raise GeometryError(errors)

        # Fuselage
        if f.length_m <= 0 or f.max_diameter_m <= 0:
            errors.append("Fuselage length and diameter must be positive.")
        if f.nose_length_m <= 0 or f.tail_length_m <= 0:
            errors.append("Nose and tail lengths must be positive.")
        if f.length_m > 0 and f.cabin_length_m < 0.5:
            errors.append(
                "Nose + tail taper leave less than 0.5 m of cabin section; "
                "increase fuselage length or shorten the tapers.")
        if f.length_m > 0 and f.max_diameter_m > 0 and f.length_m < 2.0 * f.max_diameter_m:
            errors.append("Fuselage length must be at least twice its diameter.")

        # Wing
        if w.span_m <= 0:
            errors.append("Wingspan must be greater than zero.")
        if w.mean_chord_m <= 0:
            errors.append("Wing mean chord must be greater than zero.")
        if w.span_m > 0 and w.mean_chord_m > 0 and w.area_m2 <= 0:
            errors.append("Wing area must be greater than zero.")
        if not 0.1 <= w.taper_ratio <= 1.0:
            errors.append("Wing taper ratio must be between 0.1 and 1.0.")
        if not 0.04 <= w.thickness_ratio <= 0.25:
            errors.append("Wing thickness ratio must be between 0.04 and 0.25.")
        if abs(w.quarter_chord_sweep_deg) > 45 or abs(w.dihedral_deg) > 20:
            errors.append("Wing sweep must be within ±45° and dihedral within ±20°.")
        if not errors:
            if abs(w.planform_area_m2 - w.area_m2) > 1e-9 * max(1.0, w.area_m2):
                errors.append("Wing planform area is inconsistent with span x chord.")
            if w.span_m <= f.max_diameter_m:
                errors.append("Wingspan must exceed the fuselage diameter.")
            if w.x_root_leading_edge_m < 0 or \
                    w.x_root_leading_edge_m + w.root_chord_m > f.length_m:
                errors.append("Wing root chord must lie within the fuselage length.")
            if w.aspect_ratio < 3 or w.aspect_ratio > 14:
                warnings.append(
                    f"Wing aspect ratio {w.aspect_ratio:.1f} is outside the usual "
                    "3-14 range for a trainer.")

        # Horizontal stabilizer
        if h.span_m <= 0 or h.area_m2 <= 0:
            errors.append("Horizontal stabilizer span and area must be positive.")
        elif not 0.1 <= h.taper_ratio <= 1.0:
            errors.append("Horizontal stabilizer taper ratio must be between 0.1 and 1.0.")
        elif h.x_root_leading_edge_m < 0 or \
                h.x_root_leading_edge_m + h.root_chord_m > f.length_m + 0.3:
            errors.append("Horizontal stabilizer must lie within the fuselage length.")
        elif abs(h.quarter_chord_sweep_deg) > 45 or abs(h.incidence_deg) > 15:
            errors.append("Horizontal stabilizer sweep within ±45° and incidence within ±15°.")

        # Vertical stabilizer
        if v.height_m <= 0 or v.root_chord_m <= 0:
            errors.append("Vertical stabilizer height and root chord must be positive.")
        elif not 0.1 <= v.taper_ratio <= 1.0:
            errors.append("Vertical stabilizer taper ratio must be between 0.1 and 1.0.")
        elif v.x_root_leading_edge_m < 0 or \
                v.x_root_leading_edge_m + v.root_chord_m > f.length_m + 0.3:
            errors.append("Vertical stabilizer must lie within the fuselage length.")
        elif abs(v.quarter_chord_sweep_deg) > 60:
            errors.append("Vertical stabilizer sweep must be within ±60°.")

        # Engine / propeller
        if e.cowling_length_m <= 0 or e.protrusion_m < 0 or \
                not 0.3 <= e.cowling_radius_ratio <= 1.2:
            errors.append("Engine cowling length must be positive, protrusion non-negative, "
                          "and radius ratio between 0.3 and 1.2.")
        if p.diameter_m <= 0 or p.hub_radius_m <= 0 or p.spinner_length_m <= 0 \
                or p.blade_root_chord_m <= 0 or p.blade_tip_chord_m <= 0:
            errors.append("Propeller dimensions must be positive.")
        elif p.hub_radius_m * 2 >= p.diameter_m:
            errors.append("Propeller hub must be smaller than the propeller disc.")
        elif p.diameter_m * 0.5 > 0.9 * w.span_m * 0.5:
            errors.append("Propeller is unreasonably large compared with the wing.")

        if errors:
            raise GeometryError(errors)

        # Soft checks
        if h.x_root_leading_edge_m < w.x_root_leading_edge_m + w.root_chord_m:
            warnings.append("Horizontal stabilizer overlaps the wing root in X.")
        if 0.5 * p.diameter_m > f.max_radius_m + 1.0 and p.diameter_m > 2.5:
            warnings.append("Propeller diameter is large for a two-seat trainer.")
        return warnings
