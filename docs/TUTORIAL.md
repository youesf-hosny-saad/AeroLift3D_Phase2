# AeroLift 3D — Design Tutorial

**How Engineer Youssef Hosny Saad designed AeroLift 3D, step by step, and how
every library in the project works.**

This tutorial walks through the application in the order it was designed:
first the engineering problem, then the architecture, then each module, and
finally the testing. It is written so that a student or engineer who knows
basic Python can rebuild the application, understand every design decision,
and extend it.

> **Reminder.** AeroLift 3D is an educational tool. The 3D aircraft is a
> conceptual visualisation and the lift model is a teaching approximation. See
> the disclaimer in the [README](../README.md).

## Contents

1. [The problem and the design goals](#1-the-problem-and-the-design-goals)
2. [Design workflow overview](#2-design-workflow-overview)
3. [Step 1 — The aerodynamic core (Phase 1)](#3-step-1--the-aerodynamic-core-phase-1)
4. [Step 2 — Architecture and coordinate system](#4-step-2--architecture-and-coordinate-system)
5. [Step 3 — Aircraft parameters (`aircraft_model.py`)](#5-step-3--aircraft-parameters-aircraft_modelpy)
6. [Step 4 — Geometry generation (`geometry.py`)](#6-step-4--geometry-generation-geometrypy)
7. [Step 5 — The 3D viewport (`visualization.py`)](#7-step-5--the-3d-viewport-visualizationpy)
8. [Step 6 — The main window (`app.py`)](#8-step-6--the-main-window-apppy)
9. [Step 7 — Live parametric update](#9-step-7--live-parametric-update)
10. [Step 8 — Validation and error handling](#10-step-8--validation-and-error-handling)
11. [Step 9 — Testing](#11-step-9--testing)
12. [Step 10 — Packaging for GitHub](#12-step-10--packaging-for-github)
13. [The libraries in detail](#13-the-libraries-in-detail)
14. [Extending the application](#14-extending-the-application)
15. [Glossary](#15-glossary)

---

## 1. The problem and the design goals

The goal is a desktop tool in which a student can change the dimensions of a
trainer aircraft, **see** the aircraft change in 3D, and **see** the effect on
lift immediately. Phase 1 delivered the numbers; Phase 2 delivers the 3D model
and connects it to them.

The design goals, in priority order:

1. **Correctness of the relationship between geometry and numbers.** If the
   screen says the wing area is 18 m², the wing that is drawn must have an area
   of 18 m².
2. **Separation of concerns.** The aerodynamic maths must not depend on the GUI
   or on the 3D library, so each can be tested and replaced independently.
3. **Preserve working code.** The Phase 1 lift engine worked and had been tested
   by the user, so it was kept as is (one small helper was added).
4. **Robustness.** Bad input must produce a message, not a crash.
5. **Honesty.** The interface and documentation must distinguish geometric
   visualisation from aerodynamic simulation.

## 2. Design workflow overview

The application was designed in an incremental, inspect-then-extend workflow:

| Step | Action | Result |
|---|---|---|
| 1 | Inspect the existing Phase 1 code | Understood the lift engine and the GUI before changing anything |
| 2 | Decide architecture and coordinate system | Five modules with one responsibility each |
| 3 | Model the aircraft as data | `aircraft_model.py` dataclasses |
| 4 | Generate each component independently | `geometry.py` builders |
| 5 | Embed a 3D viewport | `visualization.py` |
| 6 | Rebuild the window around three panels | `app.py` |
| 7 | Connect controls to geometry and lift | Single source of truth and debounced updates |
| 8 | Add validation | `AircraftConfig.validate()` and mesh checks |
| 9 | Test geometry, GUI and memory | `tests/` |
| 10 | Package for GitHub | `pyproject.toml`, CI, docs |

The data flow of the finished application:

```text
 spin boxes (app.py)
        │ valueChanged
        ▼
 AircraftConfig  (aircraft_model.py)  ──validate()──► errors → red status panel
        │ valid
        ├──────────────► wing_area_m2 ─► calculate_lift()  (aerodynamics.py) ─► result cards
        │
        └── (40 ms debounce)
              ▼
        build_aircraft()  (geometry.py)  ─► 6 PolyData meshes
              ▼
        AircraftViewport.update_meshes()  (visualization.py) ─► PyVista/VTK render
```

## 3. Step 1 — The aerodynamic core (Phase 1)

Phase 1 produced `aerodynamics.py`. It was inspected first and deliberately left
unchanged because it was working.

### The physics

Lift is calculated from the lift equation:

\[
L = \tfrac{1}{2}\,\rho\,V^2\,S\,C_L
\]

where ρ is air density (kg/m³), V is true airspeed (m/s), S is the wing
reference area (m²) and C_L is the lift coefficient. The term
q = ½ρV² is the dynamic pressure in pascals, so L = q · S · C_L.

C_L comes from a deliberately simple, configurable model:

\[
C_L = a\,(\alpha - \alpha_0)
\]

with lift-curve slope *a* (per degree), angle of attack α and zero-lift angle
α₀, capped at a configured C_Lmax. At or beyond the nominal stall angle, C_L is
held at the cap. This is a teaching approximation, **not** an airfoil polar.

### The code structure

```python
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

def calculate_lift(condition: FlightCondition) -> LiftResult: ...
```

Design decisions worth noting:

- **Inputs and outputs are dataclasses.** The function takes one object and
  returns one object, so there is no hidden state and it is trivial to test.
- **Validation lives in the function.** It raises `ValueError` for non-finite
  values, non-positive area or density, and inconsistent stall settings.
- **No imports from the GUI or geometry.** This is the rule that keeps
  aerodynamics independent.

### The only Phase 2 change

The Phase 1 chart evaluated the lift equation again inside the GUI. To avoid
duplicate calculations, one helper was added to `aerodynamics.py`:

```python
def lift_vs_airspeed(condition, speeds_m_s):
    lifts = []
    for speed in speeds_m_s:
        point = FlightCondition(**{**vars(condition), "airspeed_m_s": float(speed)})
        lifts.append(calculate_lift(point).lift_newtons)
    return lifts
```

Now the chart calls the same `calculate_lift` function as the result cards.

## 4. Step 2 — Architecture and coordinate system

### Module responsibilities

| Module | Responsibility |
|---|---|
| `aerodynamics.py` | Lift maths only |
| `aircraft_model.py` | What the aircraft *is*: dimensions, relations, validation |
| `geometry.py` | How the aircraft *looks*: dimensions → meshes |
| `visualization.py` | How meshes are *displayed*: viewport, actors, cameras |
| `app.py` | How the user *interacts*: widgets and wiring |

The dependency rules are strict: `aerodynamics.py` and `aircraft_model.py` use
only the standard library; `geometry.py` knows nothing about Qt;
`visualization.py` knows nothing about aerodynamics. Only `app.py` imports all
of them.

### Coordinate system

All 3D code uses a single right-handed convention (metres):

| Axis | Direction |
|---|---|
| X | Longitudinal, positive **aft** (nose at X = 0, like fuselage stations) |
| Y | Lateral, positive to the pilot's **right** |
| Z | Vertical, positive **up** |

Why X aft? Engineers measure fuselage stations from the nose backwards, so
positions such as "wing root leading edge at 2.3 m" read naturally. With X aft,
Y right and Z up, the system remains right-handed because
aft × right = up. The engine and propeller therefore sit at negative X.

The standard views follow from it:

| View | Camera looks | Screen up |
|---|---|---|
| Top | down −Z | −X (nose points up the screen) |
| Front | along +X (toward the aft) | +Z |
| Side | along −Y (from starboard) | +Z (nose on the left) |
| Isometric | from front-right-above | +Z |

## 5. Step 3 — Aircraft parameters (`aircraft_model.py`)

The aircraft is stored as plain data. There are six parameter classes and one
container:

```python
@dataclass
class AircraftConfig:
    fuselage:  FuselageParams
    wing:      WingParams
    htail:     HorizontalStabParams
    vtail:     VerticalStabParams
    engine:    EngineParams
    propeller: PropellerParams
```

### The key design decision: area is derived, never stored

A common bug in parametric tools is to store area, span and chord separately and
let them drift apart. Here the **stored** wing parameters are span *b*, mean
geometric chord *c̄* and taper ratio λ = c_t / c_r. Area is a property:

```python
@property
def area_m2(self) -> float:
    return self.span_m * self.mean_chord_m
```

For a trapezoidal wing the area is

\[
S = \frac{b}{2}\,(c_r + c_t) = b\,\bar c
\]

Root and tip chord follow from the mean chord and taper. Substituting
c_t = λ c_r into S = b c̄ gives:

\[
c_r = \frac{2\,\bar c}{1+\lambda}, \qquad c_t = \lambda\,c_r
\]

```python
def trapezoid_chords(mean_chord, taper):
    root = 2.0 * mean_chord / (1.0 + taper)
    return root, root * taper
```

`WingParams.planform_area_m2` computes ½·b·(c_r + c_t) independently, and
validation checks that it equals `area_m2`. This makes the identity an executable
check rather than a comment.

### Two independent ways to change area

Since area is derived, "set the area to 18 m²" has to be translated into a
change in span or chord. Two methods implement the two required modes:

```python
def set_area_keep_span(self, area_m2):    # change chord, span fixed
    self.mean_chord_m = area_m2 / self.span_m

def set_area_keep_chord(self, area_m2):   # change span, chord and taper fixed
    self.span_m = area_m2 / self.mean_chord_m
```

Example from 14 m² (b = 10 m, c̄ = 1.4 m) to 18 m²:

| Mode | Span | Mean chord |
|---|---|---|
| Hold span | 10.00 m | 1.800 m |
| Hold chord | 12.86 m | 1.400 m |

### Other useful definitions

- **Aspect ratio:** AR = b² / S.
- **Fuselage radius profile:** `FuselageParams.radius_at(x)` returns the radius at
  any station. It is shared by the mesh generator and by the vertical-stabilizer
  placement, so both always agree about the skin position.

  The profile has three zones:
  - *Nose* (0 → nose length): radius rises from 78 % of the maximum radius to the
    maximum with a sine blend, `r = r0 + (R − r0)·sin(πt/2)`, which ends with zero slope.
  - *Cabin*: constant maximum radius.
  - *Tail*: a cosine blend `0.5(1 + cos πt)`, raised to a 0.8 power, from the
    maximum radius down to 6 % of it.

- **Why dataclasses?** They give typed fields, defaults, a free `__init__` and
  readable `repr`, with no boilerplate. A parameter set can be copied with
  `copy.deepcopy`, which the GUI uses to keep a "last valid" snapshot.

## 6. Step 4 — Geometry generation (`geometry.py`)

Every component has its own builder and returns a `pyvista.PolyData` (a surface
made of points and triangles). Builders are independent: changing the wing does
not run any other builder's code on that component's data.

```python
builders = {
    "fuselage":  build_fuselage(config.fuselage),
    "wing":      build_wing(config.wing),
    "htail":     build_horizontal_stabilizer(config.htail),
    "vtail":     build_vertical_stabilizer(config.fuselage, config.vtail),
    "engine":    build_engine(config.fuselage, config.engine, config.propeller),
    "propeller": build_propeller(config.fuselage, config.engine, config.propeller),
}
```

Three small helpers do the heavy lifting.

### 6.1 `_revolve` — bodies of revolution

The fuselage, engine cowling and spinner are surfaces of revolution about the X
axis. Given stations `xs` and radii `rs`:

1. Build a NumPy array `sections` of shape `(n_stations, n_theta, 3)`. Each station
   is a ring: `(x, r·cosθ, r·sinθ)`.
2. Close each ring by repeating its first point.
3. Wrap the points in a `pyvista.StructuredGrid` whose dimensions are
   `(n_theta + 1, n_stations, 1)`. A structured grid is a regular mesh, which
   is the natural fit for a lofted surface.
4. `extract_surface()` turns it into `PolyData`.
5. Add planar end caps (a fan of triangles) where the radius is non-zero.
6. `_finish()` triangulates, merges duplicate points (`clean`) and computes normals.

The fuselage radius at each station comes from `FuselageParams.radius_at`.
Because stations are denser in the nose and tail (26 and 44 samples) than in the
cabin (8), curved regions look smooth while the cylinder stays cheap.

### 6.2 `_loft` and `_airfoil_loop` — wings and tails

Lifting surfaces are a stack of airfoil sections joined together ("lofting").

**Airfoil.** A symmetric NACA 4-digit-style thickness distribution is used for a
unit chord. With x the chordwise fraction and t the thickness ratio, the half
thickness is

\[
y_t = 5\,t\,\bigl(0.2969\sqrt{x} - 0.1260\,x - 0.3516\,x^2 + 0.2843\,x^3 - 0.1036\,x^4\bigr)
\]

`_airfoil_loop` samples x with a cosine distribution
(`0.5·(1 − cos β)`), which puts more points near the leading and trailing edges
where curvature is high. It returns a closed loop: upper surface from trailing
edge to leading edge, then lower surface back. The loop is not an exact
closed trailing edge (the last coefficient gives a very thin edge), and the
wrap-around in `_loft` closes it.

**Station definitions.** `build_lifting_surface` handles the wing, horizontal
stabilizer and vertical stabilizer with one function:

- Spanwise stations *s* run from −b/2 to +b/2 for horizontal surfaces and from 0
  to the height *h* for the fin (`vertical=True`).
- Chord varies linearly: `c(s) = c_r·(1 − (1 − λ)·|s|/half_span)`.
- Sweep is about the **quarter-chord line**:
  `x_q(s) = x_root_LE + 0.25·c_r + |s|·tan(sweep)`.
- Dihedral raises the quarter chord: `z_q(s) = z_root + |s|·tan(dihedral)`.
- Incidence rotates each section about its quarter chord (nose-up positive).
  For X aft, with local coordinates `x_l` (relative to the quarter chord) and
  `z_l`:

  \[
  x = x_l\cos i + z_l\sin i, \qquad z = z_l\cos i - x_l\sin i
  \]

  A leading-edge point has x_l < 0, so z increases: the nose goes up.

**Why the area is exact.** The chord is measured along X and the span along Y.
Sweep and dihedral move sections in X and Z but never change a section's chord
or its Y position. The projected planform area is therefore exactly
∫ c(y) dy = ½·b·(c_r + c_t), whatever the sweep or dihedral. The helper
`measured_planform_area(mesh)` integrates the *actual mesh* (maximum minus
minimum X at each Y station, using `np.trapezoid`) and the tests assert that it
matches the declared area. This is the proof that "the displayed area and the
generated wing are consistent". (It applies at zero incidence, because
incidence slightly shortens the projected chord.)

**Tips are capped** with fan triangles so every surface is a closed solid.

### 6.3 Engine and propeller

- **Cowling:** a revolved profile whose front is a rounded lip. The radius grows
  from the hub radius to the cowling radius with `sin(πt/2)` over the first 40 %
  of its length, then stays constant. The cowling protrudes ahead of the nose
  (negative X).
- **Spinner (hub):** a short cylinder followed by an ogive,
  `r = r_hub·(1 − t²)^0.6`.
- **Blades:** two lofted sections, 180° apart. Each blade station has its own
  chord (linear taper) and pitch angle (larger at the root, smaller at the tip,
  a visual twist). The section is built in the plane spanned by the tangential
  direction and the X axis, rotated by the pitch angle. The `azimuth_deg` parameter
  rotates the blade about the X axis.

### 6.4 Validation and assembly

`build_aircraft(config)` first calls `config.validate()`, then builds each
component, then calls `validate_mesh()` on each result. A mesh is rejected if it
is `None`, empty, has non-finite coordinates, or has zero extent along any axis.
Nothing invalid is ever handed to the renderer.

## 7. Step 5 — The 3D viewport (`visualization.py`)

`AircraftViewport` is a `QWidget` that contains a `pyvistaqt.QtInteractor`. This
is the PyVista render window as a Qt widget, so the 3D scene sits inside the
PySide6 layout rather than in a separate window.

### Persistent meshes — avoiding leaks

A naive approach removes and re-adds actors on every update. That creates a new
VTK mapper and actor each time and can leak GPU and Python resources. Instead:

```python
if name not in self._meshes:
    self._meshes[name] = pv.PolyData()
    self._meshes[name].copy_from(new, deep=True)
    self._actors[name] = self.plotter.add_mesh(self._meshes[name], ...)
else:
    self._meshes[name].copy_from(new, deep=True)
    self._meshes[name].Modified()
```

Each component keeps **one** `PolyData` and **one** actor for the whole session.
An update copies new point and cell data into the existing mesh and marks it as
modified so VTK re-renders it. The smoke test confirms that after 150 rebuilds
the renderer's actor count and the process memory stay flat.

### Camera and views

`set_view(name)` places the camera on a direction vector from the model centre
and assigns the view-up vector from the table in section 4. It then calls
`reset_camera()` to fit the scene and `camera.zoom()` to frame it. Top, front and
side use **parallel projection** (true engineering views with no perspective);
isometric uses perspective. Updating the mesh does **not** reset the camera, so
a user's rotation survives parameter changes. Only the first build fits the view.

### Interaction

`QtInteractor` provides PyVista's default trackball style: left-drag rotates,
middle-drag pans, wheel or right-drag zooms. The viewport adds the axes widget
(labelled X (aft), Y (right), Z (up)), a ground reference grid that follows the
model's lowest point, and show/hide toggles.

### Component colours

| Component | Colour |
|---|---|
| Fuselage | light grey-blue `#c9d6e2` |
| Main wing | cyan `#4fb3d9` |
| Horizontal stabilizer | orange `#f2a65a` |
| Vertical stabilizer | red `#e86f6f` |
| Engine cowling | slate `#6b7683` |
| Propeller | amber `#e8c77b` |

The same table drives the legend under the viewport.

### Cleanup

`shutdown()` calls `plotter.close()` and the window calls it from `closeEvent`, so
the OpenGL context is released when the window closes.

## 8. Step 6 — The main window (`app.py`)

### Layout

`AeroLiftWindow` uses a horizontal `QSplitter` with three parts:

- **Left (scroll area):** group boxes for flight condition, wing, fuselage,
  stabilizers, engine/propeller and the lift model.
- **Centre:** toolbar (views, axes, grid), the 3D viewport, a colour legend and
  a mouse hint.
- **Right:** three result cards (lift, C_L, dynamic pressure), equivalent kgf, the
  current geometry summary, the model status box, the chart and a disclaimer.

### Table-driven widgets

Instead of writing forty spin boxes by hand, the parameters are described as data:

```python
("fuselage", "length_m", "Length", 3.0, 15.0, 2, 0.1, "m"),
```

A loop creates each `QDoubleSpinBox` with its range, decimals, step and unit
suffix, and connects it to one handler with the component and attribute name.
Adding a parameter is one line.

### Two widget details that matter

- **`WheelGuardSpinBox`.** The panel is scrollable, and a spin box under the
  mouse would otherwise change value while the user scrolls. It ignores the wheel
  unless it has keyboard focus.
- **`setKeyboardTracking(False)`.** While typing "12.5", the value must not be
  processed as "1" and then "12". The signal fires only on Enter or focus loss.

### Visual theme

A single Qt stylesheet (QSS, similar to CSS) defines the dark navy theme, the
card style, buttons, the scrollbar and the legend. Colour roles: background
`#101923`, cards `#1a2a39`, accent teal `#70d9c5`, warning amber, error red.

## 9. Step 7 — Live parametric update

This is the heart of Phase 2. The flow, from `_on_geom_changed`:

1. The handler receives the component, attribute and new value.
2. For wing area it applies `set_area_keep_span` or `set_area_keep_chord`
   depending on the **Area edit mode** combo box; otherwise it uses `setattr`.
3. `_sync_widgets()` pushes the config back into **all** spin boxes with
   `blockSignals(True)` around each, so derived values (area, root/tip chord)
   update without triggering the handler again.
4. `_geom_changed()` validates. If valid, it stores a `deepcopy` as
   `valid_config`, recalculates the lift immediately (it is cheap), marks the
   geometry and chart dirty and (re)starts the timer.
5. After 40 ms of quiet, `_apply_deferred()` rebuilds the meshes, updates the
   viewport and redraws the chart.

### Why the debounce

Rebuilding six meshes takes tens of milliseconds, and the chart redraw takes
more. Holding an arrow key on a spin box fires many `valueChanged` events. A
single-shot `QTimer` that restarts on every event ensures only the **last**
value triggers a rebuild, keeping the application responsive. The lift numbers
are not debounced, so they respond instantly.

### One source of truth for area

The flight condition used for lift is always built like this:

```python
def _current_condition(self):
    cond = deepcopy(self.flight)
    cond.wing_area_m2 = self.valid_config.wing_area_m2
    return cond
```

There is no independent "area" input feeding the lift calculation. The only way
to change lift via area is to change geometry, so "never change the displayed
area without changing the generated wing" is enforced structurally.

### Results always match the drawing

If the user types an invalid value, the displayed lift and the 3D model both stay
on `valid_config`, the last valid state. The spin boxes show what the user typed;
the status box explains what is wrong.

## 10. Step 8 — Validation and error handling

`AircraftConfig.validate()` returns a list of **warnings** and raises
`GeometryError` (a `ValueError` subclass carrying a list of problems) for errors.

| Check | Rule |
|---|---|
| Finite values | No `NaN` or `inf` in any parameter |
| Wing area, span, mean chord | Greater than zero |
| Wing taper ratio | 0.1 ≤ λ ≤ 1.0 |
| Planform consistency | ½·b·(c_r + c_t) = b·c̄ |
| Wingspan | Greater than fuselage diameter |
| Wing root | Inside the fuselage length |
| Fuselage | Length ≥ 2 × diameter; cabin section ≥ 0.5 m after nose and tail tapers |
| Tails | Positive dimensions, taper 0.1–1.0, positioned within the fuselage |
| Propeller | Positive dimensions, hub smaller than disc, not larger than the wing allows |
| Aspect ratio | *Warning* only if outside 3–14 |

Errors are shown as a red box listing every problem, plus the status bar. Two
layers prevent a crash:

1. Validation before building (`GeometryError`).
2. In `_apply_deferred`, a `GeometryError` handler and a general `Exception`
   handler around mesh building and rendering, so unexpected faults are reported
   in the status panel instead of closing the window.

## 11. Step 9 — Testing

### Unit tests — `tests/test_geometry.py`

These run without a display and use `unittest` from the standard library.

| Test | What it proves |
|---|---|
| default components valid | All six meshes exist, are finite and non-trivial |
| trapezoid area formula | `b/2·(c_r + c_t) = b·c̄` |
| wing mesh area matches | Mesh planform area equals declared area within 0.5 % for four span/chord/taper/sweep/dihedral combinations |
| h-stab mesh area | Same check for the stabilizer |
| keep span / keep chord | The right dimension changes, mesh bounds confirm it |
| other components identical | Changing the wing alters only the wing's points |
| propeller ahead of fuselage | The propeller lies forward of the nose |
| invalid inputs rejected | Zero span, negative chord, taper 0 or 2.5, too-narrow span, `NaN`, impossible fuselage, zero tail area |
| repeated rebuild | 200 rebuilds do not grow memory or Python object count |

### GUI smoke test — `tests/gui_smoke_test.py`

It launches the real window, runs the Qt event loop with a small `pump()` helper,
and edits the widgets exactly as a user would. It checks the viewport, rotation,
the two area modes (including lift scaling by 18/14), wingspan, an invalid
wingspan, recovery, all four views, and 150 live rebuilds with memory and actor
count.

### Visual inspection

Automated checks cannot judge appearance, so screenshots were examined for
every view, for the area edits and for the error state (`docs/images/`).

### A bug found by testing

The first GUI run exposed an error: `PolyData` has no `overwrite` in the PyVista
version used. The error handling reported it in the status panel instead of
crashing, which was a useful demonstration of the validation layer. The fix was
to use `copy_from(new, deep=True)`.

## 12. Step 10 — Packaging for GitHub

| File | Purpose |
|---|---|
| `README.md` | Overview, install, usage, structure |
| `docs/TUTORIAL.md` | This tutorial |
| `LICENSE` | MIT licence with an educational-use note |
| `pyproject.toml` | Package metadata, dependencies, `aerolift3d` launcher |
| `requirements.txt`, `requirements-dev.txt` | Runtime and test dependencies |
| `.gitignore` | Excludes `.venv`, caches, screenshots |
| `.github/workflows/ci.yml` | Runs the geometry tests on Windows and Linux with Python 3.13 |
| `CHANGELOG.md`, `CONTRIBUTING.md` | Project history and contribution rules |

Publishing:

```powershell
git init
git add .
git commit -m "AeroLift 3D Phase 2: parametric 3D trainer aircraft"
git branch -M main
git remote add origin https://github.com/<your-username>/AeroLift3D.git
git push -u origin main
```

---

## 13. The libraries in detail

### 13.1 PySide6 — the desktop GUI

**What it is.** PySide6 is the official Python binding for Qt 6, a mature C++
toolkit for desktop interfaces. It supplies windows, widgets, layouts, event
handling, styling and timers. Qt is cross-platform, and PySide6 is distributed
by the Qt Company under the LGPL licence.

**Why it was chosen.** The requirement was a Windows desktop application that
could host a 3D viewport and a Matplotlib chart. Qt is the standard answer, and
both PyVista (through PyVistaQt) and Matplotlib have first-class Qt integration.

**Core concepts used in this project:**

| Concept | Meaning | Where it appears |
|---|---|---|
| `QApplication` | The application object that owns the event loop | `main()` creates it and calls `app.exec()` |
| Event loop | Waits for user events and dispatches them | Keeps the GUI alive; tests call `processEvents()` manually |
| `QMainWindow` | A window with a central widget and status bar | `AeroLiftWindow` |
| `QWidget` | Base class of all visual elements | The viewport, panels, `WheelGuardSpinBox` parent |
| Layouts (`QVBoxLayout`, `QHBoxLayout`, `QFormLayout`, `QGridLayout`) | Arrange widgets automatically as the window resizes | Panels, parameter forms, geometry summary |
| `QSplitter` | A resizable divider between panels | Left / centre / right |
| `QScrollArea` | Scrolls content too tall for the window | The parameter panel |
| `QGroupBox` | Titled frame | "WING CONFIGURATION" etc. |
| `QDoubleSpinBox` | Numeric input with arrows, range, decimals, suffix | All parameters |
| `QComboBox` | Drop-down list | Area edit mode |
| `QCheckBox`, `QPushButton`, `QLabel` | Basic controls | Axes/grid toggles, view buttons, results |
| `QStatusBar` | Message strip at the bottom | Status messages |
| Signals and slots | Event wiring: `spin.valueChanged.connect(handler)` | Every control |
| `QTimer` | Delayed or repeated callbacks | The single-shot 40 ms debounce |
| `Qt.Orientation`, `Qt.AlignmentFlag`, … | Enumerations | Layout configuration |
| Style sheets (QSS) | CSS-like styling | The dark navy theme |
| `closeEvent` | Override to run clean-up | Release the 3D context |

**Signals and slots.** A *signal* is an event a widget emits; a *slot* is any
callable that reacts. `valueChanged(float)` is emitted when a spin box's value
changes. `blockSignals(True)` temporarily prevents emission, which is how the
program updates derived values without causing loops.

**Pitfalls handled.** Lambdas in a loop capture variables late, so the code binds
them as default arguments (`lambda v, c=comp, a=attr: ...`). Widgets must be
used only on the GUI thread, which is why the debounce uses a `QTimer` instead
of a worker thread.

**Install:** `pip install PySide6`

### 13.2 PyVista — meshes and 3D visualisation

**What it is.** PyVista is a high-level Python interface to the Visualization
Toolkit (VTK). VTK is a powerful but verbose C++ library; PyVista provides
Pythonic objects with NumPy integration, so a mesh's points are simply a NumPy
array.

**Data types used:**

| Type | Meaning | Use here |
|---|---|---|
| `pyvista.PolyData` | A surface or set of points/lines/polygons | Every aircraft component |
| `pyvista.StructuredGrid` | A grid defined by an array of points and dimensions `(nx, ny, nz)` | Raw skin of revolved and lofted surfaces |
| `pyvista.Plane` | A flat rectangular mesh | The ground grid |

**Functions and methods used:**

| Call | What it does |
|---|---|
| `StructuredGrid.points`, `.dimensions` | Define a curved grid from points |
| `extract_surface()` | Converts a grid into `PolyData` |
| `PolyData(points, faces)` | Builds a polygon from a ring of points; used for caps |
| `merge()` | Combines meshes into one |
| `triangulate()` | Converts all polygons to triangles |
| `clean()` | Merges coincident points and removes degenerate cells |
| `compute_normals()` | Calculates surface normals for lighting; `split_vertices` keeps sharp edges crisp, smooth otherwise |
| `copy_from(mesh, deep=True)` | Copies data into an existing mesh (used for in-place updates) |
| `.bounds`, `.n_points`, `.n_cells` | Mesh diagnostics used in validation and tests |
| `plotter.add_mesh()` | Adds a mesh to the scene and returns an actor |
| `plotter.camera_position`, `camera.zoom()`, `enable_parallel_projection()` | Camera control |
| `plotter.add_axes()`, `set_background()`, `screenshot()` | Scene decoration and capture |

**Concepts.**

- *Point:* a 3D coordinate. *Cell:* a polygon or triangle referencing points.
- *Normal:* the direction a surface faces; lighting calculations use it, and
  smooth shading interpolates normals across a surface.
- *Actor:* VTK's representation of an object in a scene (mesh + colour +
  lighting properties). Keeping a persistent actor per component is what prevents
  leaks.
- *Parallel projection:* an orthographic camera without perspective, used for
  engineering views.

**Why not draw with Matplotlib 3D?** Matplotlib's 3D is not a real-time renderer;
it is slow with tens of thousands of triangles and has weak depth sorting. VTK
uses OpenGL for fast, correct hidden-surface removal and lighting.

**Install:** `pip install pyvista` (also installs `vtk`).

### 13.3 VTK — the rendering engine behind PyVista

You do not import VTK directly, but it explains behaviour: `Modified()` tells
the VTK pipeline that data changed; the render window uses OpenGL; the default
interaction style is trackball camera. VTK is installed as a dependency of
PyVista.

### 13.4 PyVistaQt — embedding PyVista in Qt

**What it is.** A small library that provides `QtInteractor`, a PyVista plotter
that is also a Qt widget. It handles the connection between Qt's mouse and
keyboard events and VTK's interactor, and between the Qt window and the OpenGL
render window.

**How it is used.** `AircraftViewport` creates `QtInteractor(self, auto_update=False)`
and puts it in a layout like any other widget. `auto_update=False` disables
periodic redraws; the code calls `plotter.render()` only when something changes,
which saves CPU. PyVistaQt chooses the Qt binding through the `QT_API`
environment variable (through the `qtpy` abstraction), which is why the code
sets `os.environ.setdefault("QT_API", "pyside6")` before importing it.

**Install:** `pip install pyvistaqt` (also installs `qtpy`).

### 13.5 NumPy — numerical arrays

**What it is.** NumPy provides the n-dimensional array and vectorised
mathematics that scientific Python is built on. Operations run in compiled code,
so they are fast and concise.

**How it is used here:**

| NumPy feature | Use in AeroLift 3D |
|---|---|
| `np.linspace`, `np.concatenate`, `np.unique` | Spanwise, chordwise and axial stations, merged and de-duplicated |
| Broadcasting (`xc[None, :] * chord[:, None]`) | Builds every airfoil section at every span station without Python loops |
| `np.cos`, `np.sin`, `np.sqrt`, `np.clip`, `np.radians` | Rotation, airfoil thickness, hub profile |
| Array slicing (`sections[:, :, 1] = ...`) | Filling coordinates of 3D point arrays |
| `np.hstack`, `np.arange` | Building face arrays |
| `np.isfinite`, `np.all` | Mesh validation |
| `np.trapezoid` | Numerical integration of chord over span in `measured_planform_area` (NumPy 2.0 or newer) |
| `np.allclose`, `np.ptp` | Tests and chord measurement |

**Broadcasting explained.** To get every point of every section, the code uses
arrays of shape `(n_stations, 1)` and `(1, n_points)`. Multiplying them yields
`(n_stations, n_points)` without a loop, e.g.
`xl = (xc[None, :] - 0.25) * chord[:, None]`.

**Install:** `pip install numpy`

### 13.6 Matplotlib — the lift chart

**What it is.** Matplotlib is Python's standard plotting library. It has a Qt
backend, `FigureCanvasQTAgg`, which is a Qt widget that displays a Matplotlib
figure.

**How it is used.** A `Figure` and `FigureCanvasQTAgg` are created once. On each
chart update, `figure.clear()` empties it and a new `Axes` is added, then
`canvas.draw_idle()` schedules a redraw. The line shows lift versus airspeed
(from `lift_vs_airspeed`) and a marker shows the current condition. The chart is
styled with the same navy palette as the rest of the interface. `draw_idle()`
rather than `draw()` lets Qt merge multiple requests into one repaint.

**Install:** `pip install matplotlib`

### 13.7 Python standard library modules

| Module | Used for |
|---|---|
| `dataclasses` | `@dataclass` parameter and result classes; `field(default_factory=...)` for nested defaults |
| `math` | `tan`, `radians`, `sin`, `cos`, `ceil`, `isfinite` for scalar maths |
| `copy` | `deepcopy` for the last-valid snapshot and flight-condition copy |
| `os`, `sys` | Environment variable for `QT_API`; `sys.argv` and `sys.exit` for the application entry point |
| `__future__.annotations` | Lets type hints such as `list[str]` and `tuple[float, float]` refer to later definitions |
| `gc` | Forced garbage collection in the memory tests |
| `time` | Timing and event-loop pumping in the smoke test |
| `unittest` | Test framework for the geometry tests |

**Dataclasses in practice.** The decorator generates `__init__`, `__repr__` and
`__eq__` from annotated fields. Mutable defaults such as nested dataclass
instances use `field(default_factory=FuselageParams)` so each `AircraftConfig`
gets its own objects. `vars(obj)` returns a dataclass's fields as a dictionary,
used by validation and by `lift_vs_airspeed`.

### 13.8 psutil (optional, tests only)

`psutil` reads process information. The tests use
`psutil.Process().memory_info().rss` (resident set size) to measure memory
before and after repeated rebuilds. If it is missing, the tests still run with
the memory check reporting 0 MB and rely on the Python-object count.

### 13.9 How the libraries fit together

```text
      NumPy arrays ──► PyVista meshes ──► VTK renderer (OpenGL)
                              │                    ▲
                              ▼                    │
                       PyVistaQt QtInteractor ─────┘  (a Qt widget)
                              │
                              ▼
        PySide6 window ◄── Matplotlib FigureCanvasQTAgg (another Qt widget)
```

## 14. Extending the application

| Goal | Where to start |
|---|---|
| Add a parameter | Add a field to the dataclass in `aircraft_model.py`; add one tuple in `GEOMETRY_GROUPS`; use it in the builder |
| Add a component (e.g. landing gear) | Add a parameter class and `build_*` function; add it to `build_aircraft`, `COMPONENTS` and `COMPONENT_STYLE` |
| Cambered airfoils | Replace `_airfoil_loop` with a NACA 4-digit generator that adds a camber line |
| Lift vector (Phase 3) | Add an arrow mesh in `geometry.py` scaled from `LiftResult`; render it as a new actor |
| STL export | `pyvista.merge(list(meshes.values())).save("aircraft.stl")` |
| Better wing–fuselage junction | Add a fillet component or a boolean union (`PolyData.boolean_union`) |
| Different aerodynamic model | Replace the body of `calculate_lift`; the GUI depends only on `LiftResult` |

## 15. Glossary

| Term | Meaning |
|---|---|
| Planform area (S) | Wing area as seen from above |
| Mean geometric chord (c̄) | S / b |
| Root / tip chord | Chord at the fuselage centreline / at the wing tip |
| Taper ratio (λ) | c_tip / c_root |
| Quarter-chord sweep | Angle of the 25 %-chord line relative to the lateral axis |
| Dihedral | Upward angle of the wing relative to horizontal |
| Incidence | Angle between a surface's chord line and the fuselage axis |
| Aspect ratio (AR) | b² / S |
| Dynamic pressure (q) | ½ρV² |
| Lift coefficient (C_L) | Non-dimensional lift, L / (q·S) |
| Mesh / PolyData | A surface made of points and triangles |
| Actor | A renderable object in VTK/PyVista |
| Loft | Creating a surface through a stack of cross-sections |
| Debounce | Delaying an action until events stop arriving |
| Signal / slot | Qt's event emission and event handler |

---

**Author:** Engineer Youssef Hosny Saad. Educational use only; see the disclaimer
in the [README](../README.md).
