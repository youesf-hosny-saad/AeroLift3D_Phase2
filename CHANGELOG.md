# Changelog

## 0.2.0 — Phase 2: Parametric 3D trainer aircraft
- Added `aircraft_model.py`, `geometry.py`, `visualization.py`.
- Embedded interactive PyVista/VTK viewport in the PySide6 window.
- Parametric fuselage, wing, horizontal/vertical stabilizers, engine cowling, two-blade propeller.
- Wing area derived from span x mean chord; two independent area-edit modes.
- Live geometry + lift update with debounced mesh rebuilds.
- Geometry validation with on-screen error reporting.
- Added `lift_vs_airspeed()` helper to `aerodynamics.py` (Phase 1 functions unchanged).
- Added geometry unit tests and a GUI smoke test.

## 0.1.0 — Phase 1: Aerodynamics core
- PySide6 desktop shell, lift calculation `L = 1/2 rho V^2 S CL`, lift-vs-airspeed chart.
