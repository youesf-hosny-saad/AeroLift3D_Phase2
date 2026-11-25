"""Preliminary aerodynamic calculations for AeroLift 3D.

The lift-coefficient model is an educational, configurable approximation.
It is not an airfoil polar and must not be used for aircraft certification
or flight-safety decisions.
"""
from dataclasses import dataclass
import math


@dataclass
class FlightCondition:
    wing_area_m2: float = 14.0
    air_density_kg_m3: float = 1.225
    airspeed_m_s: float = 50.0
    angle_of_attack_deg: float = 5.0
    lift_curve_slope_per_deg: float = 0.1
    zero_lift_angle_deg: float = -2.0
    max_lift_coefficient: float = 1.4
    stall_angle_deg: float = 16.0


@dataclass
class LiftResult:
    dynamic_pressure_pa: float
    lift_coefficient: float
    lift_newtons: float
    lift_kgf: float
    lift_curve_region: str


def calculate_lift(condition: FlightCondition) -> LiftResult:
    """Calculate lift using L = q * S * CL and a simple CL(alpha) model."""
    values = vars(condition)
    if any(not math.isfinite(float(v)) for v in values.values()):
        raise ValueError("All inputs must be finite numbers.")
    if condition.wing_area_m2 <= 0:
        raise ValueError("Wing area must be greater than zero.")
    if condition.air_density_kg_m3 <= 0:
        raise ValueError("Air density must be greater than zero.")
    if condition.airspeed_m_s < 0:
        raise ValueError("Airspeed cannot be negative.")
    if condition.lift_curve_slope_per_deg <= 0:
        raise ValueError("Lift-curve slope must be greater than zero.")
    if condition.max_lift_coefficient <= 0:
        raise ValueError("Maximum lift coefficient must be greater than zero.")
    if condition.stall_angle_deg <= condition.zero_lift_angle_deg:
        raise ValueError("Stall angle must exceed zero-lift angle.")

    alpha = condition.angle_of_attack_deg
    raw_cl = condition.lift_curve_slope_per_deg * (
        alpha - condition.zero_lift_angle_deg
    )

    if alpha >= condition.stall_angle_deg:
        cl = condition.max_lift_coefficient
        region = "Beyond nominal stall angle — CL held at configured cap"
    elif raw_cl >= condition.max_lift_coefficient:
        cl = condition.max_lift_coefficient
        region = "CL cap reached"
    else:
        cl = max(0.0, raw_cl)
        region = "Linear pre-stall approximation"

    q = 0.5 * condition.air_density_kg_m3 * condition.airspeed_m_s**2
    lift = q * condition.wing_area_m2 * cl
    return LiftResult(
        dynamic_pressure_pa=q,
        lift_coefficient=cl,
        lift_newtons=lift,
        lift_kgf=lift / 9.80665,
        lift_curve_region=region,
    )


def lift_vs_airspeed(condition: FlightCondition, speeds_m_s) -> list[float]:
    """Lift (N) at each airspeed, all other inputs held at ``condition``.

    Added in Phase 2 so the GUI chart reuses ``calculate_lift`` instead of
    duplicating the lift equation.
    """
    lifts = []
    for speed in speeds_m_s:
        point = FlightCondition(**{**vars(condition), "airspeed_m_s": float(speed)})
        lifts.append(calculate_lift(point).lift_newtons)
    return lifts
