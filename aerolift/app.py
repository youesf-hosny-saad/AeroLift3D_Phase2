"""AeroLift 3D - main window (Phase 2: parametric 3D trainer aircraft).

GUI only: parameters are stored in ``AircraftConfig``, lift is computed by
``aerodynamics.calculate_lift`` and meshes by ``geometry.build_aircraft``.
"""
from __future__ import annotations

import os
import sys
from copy import deepcopy

os.environ.setdefault("QT_API", "pyside6")

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QFrame,
    QGridLayout, QGroupBox, QHBoxLayout, QLabel, QMainWindow, QPushButton,
    QScrollArea, QSplitter, QStatusBar, QVBoxLayout, QWidget,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from .aerodynamics import FlightCondition, calculate_lift, lift_vs_airspeed
from .aircraft_model import AircraftConfig, GeometryError
from .geometry import build_aircraft
from .visualization import COMPONENT_STYLE, AircraftViewport

# (key, label, component or None, attribute, min, max, decimals, step, unit)
# component None -> FlightCondition field.
FLIGHT_FIELDS = [
    ("air_density_kg_m3", "Air density", 0.1, 2.0, 3, 0.01, "kg/m³"),
    ("airspeed_m_s", "True airspeed", 0.0, 250.0, 2, 1.0, "m/s"),
    ("angle_of_attack_deg", "Angle of attack", -10.0, 35.0, 1, 0.5, "deg"),
]
LIFT_MODEL_FIELDS = [
    ("lift_curve_slope_per_deg", "Lift-curve slope", 0.01, 0.2, 3, 0.005, "1/deg"),
    ("zero_lift_angle_deg", "Zero-lift angle", -15.0, 10.0, 1, 0.5, "deg"),
    ("max_lift_coefficient", "Configured CL max", 0.2, 3.0, 2, 0.05, "—"),
    ("stall_angle_deg", "Nominal stall angle", 5.0, 30.0, 1, 0.5, "deg"),
]
# (component, attribute, label, min, max, decimals, step, unit)
GEOMETRY_GROUPS = {
    "FUSELAGE": [
        ("fuselage", "length_m", "Length", 3.0, 15.0, 2, 0.1, "m"),
        ("fuselage", "max_diameter_m", "Max diameter", 0.5, 3.0, 2, 0.05, "m"),
        ("fuselage", "nose_length_m", "Nose taper length", 0.2, 6.0, 2, 0.1, "m"),
        ("fuselage", "tail_length_m", "Tail taper length", 0.5, 8.0, 2, 0.1, "m"),
    ],
    "HORIZONTAL STABILIZER": [
        ("htail", "span_m", "Span", 0.3, 8.0, 2, 0.1, "m"),
        ("htail", "area_m2", "Area", 0.1, 15.0, 2, 0.1, "m²"),
        ("htail", "quarter_chord_sweep_deg", "Sweep (c/4)", -45.0, 45.0, 1, 1.0, "deg"),
        ("htail", "incidence_deg", "Incidence", -15.0, 15.0, 1, 0.5, "deg"),
        ("htail", "x_root_leading_edge_m", "X position (LE)", 0.0, 15.0, 2, 0.1, "m"),
        ("htail", "z_position_m", "Z position", -1.5, 1.5, 2, 0.05, "m"),
    ],
    "VERTICAL STABILIZER": [
        ("vtail", "height_m", "Height", 0.2, 4.0, 2, 0.1, "m"),
        ("vtail", "root_chord_m", "Root chord", 0.2, 4.0, 2, 0.05, "m"),
        ("vtail", "taper_ratio", "Taper ratio", 0.0, 1.5, 2, 0.05, "—"),
        ("vtail", "quarter_chord_sweep_deg", "Sweep (c/4)", -60.0, 60.0, 1, 1.0, "deg"),
        ("vtail", "x_root_leading_edge_m", "X position (LE)", 0.0, 15.0, 2, 0.1, "m"),
    ],
    "ENGINE & PROPELLER": [
        ("engine", "cowling_length_m", "Cowling length", 0.2, 3.0, 2, 0.05, "m"),
        ("propeller", "diameter_m", "Propeller diameter", 0.5, 3.5, 2, 0.05, "m"),
        ("propeller", "azimuth_deg", "Blade azimuth", 0.0, 180.0, 0, 5.0, "deg"),
    ],
}
WING_EXTRA_FIELDS = [
    ("taper_ratio", "Taper ratio (ct/cr)", 0.0, 1.5, 2, 0.05, "—"),
    ("quarter_chord_sweep_deg", "Sweep (c/4)", -45.0, 45.0, 1, 1.0, "deg"),
    ("dihedral_deg", "Dihedral", -20.0, 20.0, 1, 0.5, "deg"),
    ("incidence_deg", "Incidence", -10.0, 10.0, 1, 0.5, "deg"),
    ("x_root_leading_edge_m", "X position (root LE)", 0.0, 15.0, 2, 0.1, "m"),
    ("z_position_m", "Z position (vs. axis)", -1.5, 1.5, 2, 0.05, "m"),
]

HOLD_SPAN, HOLD_CHORD = 0, 1


class WheelGuardSpinBox(QDoubleSpinBox):
    """Ignore the mouse wheel unless focused, so scrolling the panel is safe."""

    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setKeyboardTracking(False)

    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class AeroLiftWindow(QMainWindow):
    REBUILD_DELAY_MS = 40

    def __init__(self):
        super().__init__()
        self.setWindowTitle("AeroLift 3D | Phase 2 — Parametric 3D Trainer Model")
        self.resize(1640, 960)
        self.setMinimumSize(1280, 760)

        self.config = AircraftConfig()
        self.valid_config = deepcopy(self.config)
        self.flight = FlightCondition()
        self.geometry_ok = True
        self.last_warnings: list[str] = []
        self.last_result = None
        self.mesh_stats = ""
        self._geom_dirty = True
        self._chart_dirty = True
        self.geom_widgets: dict[tuple[str, str], QDoubleSpinBox] = {}
        self.flight_widgets: dict[str, QDoubleSpinBox] = {}

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 12, 14, 10)
        root.setSpacing(8)
        root.addLayout(self._build_header())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_center_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([380, 820, 420])
        splitter.setChildrenCollapsible(False)
        root.addWidget(splitter, 1)

        self.setStatusBar(QStatusBar())
        self.setStyleSheet(STYLESHEET)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(self.REBUILD_DELAY_MS)
        self._timer.timeout.connect(self._apply_deferred)

        self._sync_widgets()
        self._update_results()
        self._apply_deferred()      # first geometry build + chart

    # ------------------------------------------------------------------ UI
    def _build_header(self):
        header = QHBoxLayout()
        box = QVBoxLayout()
        title = QLabel("AeroLift 3D")
        title.setObjectName("appTitle")
        sub = QLabel("TRAINER AIRCRAFT  •  PARAMETRIC 3D MODEL  •  PRELIMINARY LIFT ANALYSIS")
        sub.setObjectName("subtitle")
        box.addWidget(title)
        box.addWidget(sub)
        header.addLayout(box)
        header.addStretch()
        tag = QLabel("PHASE 2  |  CONCEPTUAL GEOMETRY")
        tag.setObjectName("phaseTag")
        header.addWidget(tag, alignment=Qt.AlignmentFlag.AlignVCenter)
        return header

    def _make_spin(self, lo, hi, dec, step, unit):
        spin = WheelGuardSpinBox()
        spin.setRange(lo, hi)
        spin.setDecimals(dec)
        spin.setSingleStep(step)
        spin.setSuffix(f"  {unit}")
        return spin

    def _add_flight_row(self, form, key, label, lo, hi, dec, step, unit):
        spin = self._make_spin(lo, hi, dec, step, unit)
        spin.setValue(getattr(self.flight, key))
        spin.valueChanged.connect(lambda v, k=key: self._on_flight_changed(k, v))
        self.flight_widgets[key] = spin
        form.addRow(label, spin)

    def _add_geom_row(self, form, comp, attr, label, lo, hi, dec, step, unit):
        spin = self._make_spin(lo, hi, dec, step, unit)
        spin.valueChanged.connect(lambda v, c=comp, a=attr: self._on_geom_changed(c, a, v))
        self.geom_widgets[(comp, attr)] = spin
        form.addRow(label, spin)
        return spin

    def _build_left_panel(self):
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(0, 0, 8, 0)
        lay.setSpacing(8)

        flight = QGroupBox("FLIGHT CONDITION")
        form = QFormLayout(flight)
        for f in FLIGHT_FIELDS:
            self._add_flight_row(form, *f)
        lay.addWidget(flight)

        wing = QGroupBox("WING CONFIGURATION")
        wform = QFormLayout(wing)
        self.area_mode = QComboBox()
        self.area_mode.addItems(["Hold span",
                                 "Hold chord"])
        self.area_mode.setToolTip(
            "How an edit of the wing AREA is realised in the geometry.\n"
            "Hold span: span fixed, chord changes.  Hold chord: chord fixed, span changes.\n"
            "Editing span or mean chord directly always changes the area.")
        wform.addRow("Area edit mode", self.area_mode)
        self._add_geom_row(wform, "wing", "area_m2", "Wing reference area",
                           0.5, 200.0, 2, 0.5, "m²")
        self._add_geom_row(wform, "wing", "span_m", "Wingspan", 1.0, 30.0, 2, 0.1, "m")
        self._add_geom_row(wform, "wing", "mean_chord_m", "Mean geometric chord",
                           0.1, 6.0, 3, 0.05, "m")
        for attr, label, lo, hi, dec, step, unit in WING_EXTRA_FIELDS:
            self._add_geom_row(wform, "wing", attr, label, lo, hi, dec, step, unit)
        self.chord_label = QLabel("—")
        self.chord_label.setObjectName("derived")
        wform.addRow("Root / tip chord", self.chord_label)
        lay.addWidget(wing)

        for title, rows in GEOMETRY_GROUPS.items():
            g = QGroupBox(title)
            f = QFormLayout(g)
            for comp, attr, label, lo, hi, dec, step, unit in rows:
                self._add_geom_row(f, comp, attr, label, lo, hi, dec, step, unit)
            lay.addWidget(g)

        model = QGroupBox("LIFT-COEFFICIENT MODEL")
        mform = QFormLayout(model)
        for f in LIFT_MODEL_FIELDS:
            self._add_flight_row(mform, *f)
        lay.addWidget(model)
        lay.addStretch()

        reset = QPushButton("Restore default aircraft")
        reset.clicked.connect(self._restore_defaults)
        lay.addWidget(reset)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        scroll.setMinimumWidth(340)
        return scroll

    def _build_center_panel(self):
        panel = QWidget()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        bar = QHBoxLayout()
        for label, view in (("Isometric", "isometric"), ("Top", "top"),
                            ("Front", "front"), ("Side", "side")):
            b = QPushButton(label)
            b.clicked.connect(lambda _=False, v=view: self.viewport.set_view(v))
            bar.addWidget(b)
        reset = QPushButton("Reset camera")
        reset.clicked.connect(lambda: self.viewport.reset_camera())
        bar.addWidget(reset)
        bar.addStretch()
        self.axes_box = QCheckBox("Axes")
        self.axes_box.setChecked(True)
        self.grid_box = QCheckBox("Ground grid")
        self.grid_box.setChecked(True)
        bar.addWidget(self.axes_box)
        bar.addWidget(self.grid_box)
        lay.addLayout(bar)

        self.viewport = AircraftViewport()
        self.axes_box.toggled.connect(lambda on: self.viewport.set_axes_visible(on))
        self.grid_box.toggled.connect(lambda on: self.viewport.set_grid_visible(on))
        frame = QFrame()
        frame.setObjectName("viewportFrame")
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(1, 1, 1, 1)
        fl.addWidget(self.viewport)
        lay.addWidget(frame, 1)

        legend = QHBoxLayout()
        for _, (name, colour) in COMPONENT_STYLE.items():
            dot = QLabel(f"<span style='color:{colour}'>■</span> {name}")
            dot.setObjectName("legend")
            legend.addWidget(dot)
        legend.addStretch()
        hint = QLabel("Left-drag: rotate  •  Middle-drag: pan  •  Wheel / right-drag: zoom"
                      "  •  X aft, Y right, Z up")
        hint.setObjectName("legend")
        legend.addWidget(hint)
        lay.addLayout(legend)
        return panel

    def _make_metric(self, layout, heading, unit):
        frame = QFrame()
        frame.setObjectName("metricCard")
        box = QVBoxLayout(frame)
        box.setSpacing(0)
        h = QLabel(heading)
        h.setObjectName("metricHeading")
        v = QLabel("—")
        v.setObjectName("metricValue")
        u = QLabel(unit)
        u.setObjectName("metricUnit")
        for w in (h, v, u):
            box.addWidget(w)
        layout.addWidget(frame, 1)
        return v

    def _build_right_panel(self):
        panel = QWidget()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(8, 0, 0, 0)
        lay.setSpacing(8)

        cards = QHBoxLayout()
        self.lift_value = self._make_metric(cards, "TOTAL LIFT", "N")
        self.cl_value = self._make_metric(cards, "LIFT COEFF.", "CL")
        self.q_value = self._make_metric(cards, "DYN. PRESSURE", "Pa")
        lay.addLayout(cards)
        self.kgf_label = QLabel("Equivalent lift: — kgf")
        self.kgf_label.setObjectName("secondaryResult")
        self.region_label = QLabel("Lift model region: —")
        self.region_label.setObjectName("region")
        self.region_label.setWordWrap(True)
        lay.addWidget(self.kgf_label)
        lay.addWidget(self.region_label)

        geo = QGroupBox("CURRENT AIRCRAFT GEOMETRY")
        grid = QGridLayout(geo)
        grid.setColumnStretch(1, 1)
        self.geo_labels = {}
        for row, (key, text) in enumerate([
                ("area", "Wing area S"), ("span", "Wingspan b"),
                ("chord", "Mean chord c̄"), ("rt", "Root / tip chord"),
                ("ar", "Aspect ratio"), ("fus", "Fuselage L × Ø"),
                ("ht", "H-stab span / area"), ("vt", "V-stab height / area")]):
            name = QLabel(text)
            name.setObjectName("geoName")
            val = QLabel("—")
            val.setObjectName("geoValue")
            val.setAlignment(Qt.AlignmentFlag.AlignRight)
            grid.addWidget(name, row, 0)
            grid.addWidget(val, row, 1)
            self.geo_labels[key] = val
        lay.addWidget(geo)

        status = QGroupBox("MODEL STATUS")
        sl = QVBoxLayout(status)
        self.model_status = QLabel("—")
        self.model_status.setWordWrap(True)
        self.model_status.setObjectName("modelOk")
        sl.addWidget(self.model_status)
        lay.addWidget(status)

        chart = QGroupBox("LIFT VS. AIRSPEED")
        cl = QVBoxLayout(chart)
        self.figure = Figure(figsize=(4.5, 2.6), dpi=100, facecolor="#101923")
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setMinimumHeight(240)
        cl.addWidget(self.canvas)
        lay.addWidget(chart, 1)

        note = QLabel(
            "Educational tool. The 3D model is a conceptual geometric "
            "visualisation, not a validated aircraft design. Lift comes from a "
            "simple linear CL model applied to the wing area of the model; it "
            "does not predict real aircraft performance.")
        note.setObjectName("note")
        note.setWordWrap(True)
        lay.addWidget(note)
        return panel

    # ----------------------------------------------------------- handlers
    def _on_flight_changed(self, key, value):
        setattr(self.flight, key, value)
        self._update_results()
        self._chart_dirty = True
        self._timer.start()

    def _on_geom_changed(self, comp, attr, value):
        obj = getattr(self.config, comp)
        try:
            if comp == "wing" and attr == "area_m2":
                if value <= 0:
                    raise GeometryError("Wing area must be greater than zero.")
                if self.area_mode.currentIndex() == HOLD_SPAN:
                    obj.set_area_keep_span(value)
                else:
                    obj.set_area_keep_chord(value)
            else:
                setattr(obj, attr, value)
        except GeometryError as exc:
            self._show_error(exc)
            return
        self._sync_widgets()
        self._geom_changed()

    def _geom_changed(self):
        """Validate immediately; lift always matches the last VALID geometry."""
        try:
            self.last_warnings = self.config.validate()
        except GeometryError as exc:
            self._show_error(exc)
            return
        self.geometry_ok = True
        self.valid_config = deepcopy(self.config)
        self._update_results()
        self._geom_dirty = True
        self._chart_dirty = True
        self._timer.start()

    def _restore_defaults(self):
        self.config = AircraftConfig()
        self._sync_widgets()
        self._geom_changed()

    def _sync_widgets(self):
        """Push config values into the spin boxes without re-triggering edits."""
        for (comp, attr), spin in self.geom_widgets.items():
            value = getattr(getattr(self.config, comp), attr)
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)
        w = self.config.wing
        self.chord_label.setText(f"{w.root_chord_m:.3f} m  /  {w.tip_chord_m:.3f} m")

    # ------------------------------------------------------------ results
    def _show_error(self, exc):
        self.geometry_ok = False
        text = "INVALID GEOMETRY — showing last valid model\n• " + "\n• ".join(
            getattr(exc, "problems", [str(exc)]))
        self.model_status.setObjectName("modelBad")
        self.model_status.setText(text)
        self.model_status.style().unpolish(self.model_status)
        self.model_status.style().polish(self.model_status)
        self.statusBar().showMessage("Geometry error: " + str(exc))

    def _current_condition(self) -> FlightCondition:
        cond = deepcopy(self.flight)
        cond.wing_area_m2 = self.valid_config.wing_area_m2   # single source of area
        return cond

    def _update_results(self):
        cond = self._current_condition()
        try:
            res = calculate_lift(cond)
        except ValueError as exc:
            self.statusBar().showMessage(f"Input error: {exc}")
            return
        self.last_result = res
        self.lift_value.setText(f"{res.lift_newtons:,.0f}")
        self.cl_value.setText(f"{res.lift_coefficient:.3f}")
        self.q_value.setText(f"{res.dynamic_pressure_pa:,.1f}")
        self.kgf_label.setText(f"Equivalent lift: {res.lift_kgf:,.1f} kgf")
        self.region_label.setText(f"Lift model region: {res.lift_curve_region}")

        c = self.valid_config
        w = c.wing
        g = self.geo_labels
        g["area"].setText(f"{w.area_m2:.2f} m²")
        g["span"].setText(f"{w.span_m:.2f} m")
        g["chord"].setText(f"{w.mean_chord_m:.3f} m")
        g["rt"].setText(f"{w.root_chord_m:.2f} / {w.tip_chord_m:.2f} m")
        g["ar"].setText(f"{w.aspect_ratio:.2f}")
        g["fus"].setText(f"{c.fuselage.length_m:.2f} m × {c.fuselage.max_diameter_m:.2f} m")
        g["ht"].setText(f"{c.htail.span_m:.2f} m / {c.htail.area_m2:.2f} m²")
        g["vt"].setText(f"{c.vtail.height_m:.2f} m / {c.vtail.area_m2:.2f} m²")

    def _apply_deferred(self):
        """Debounced heavy work: mesh rebuild and chart redraw."""
        if self._geom_dirty:
            self._geom_dirty = False
            try:
                meshes, warnings = build_aircraft(self.valid_config)
                self.viewport.update_meshes(meshes)
                tris = sum(m.n_cells for m in meshes.values())
                self.mesh_stats = (f"Meshes: {len(meshes)} components, {tris:,} triangles, "
                                   f"rebuild #{self.viewport.rebuild_count}")
                self._set_model_ok(warnings)
            except GeometryError as exc:
                self._show_error(exc)
            except Exception as exc:     # never crash the GUI on a rendering fault
                self._show_error(GeometryError(f"Unexpected rendering error: {exc}"))
        if self._chart_dirty:
            self._chart_dirty = False
            self._draw_chart()

    def _set_model_ok(self, warnings):
        lines = ["MODEL VALID — geometry updated", self.mesh_stats,
                 "Area shown = span × mean chord of the generated wing."]
        lines += [f"Warning: {w}" for w in warnings]
        self.model_status.setObjectName("modelOk")
        self.model_status.setText("\n".join(lines))
        self.model_status.style().unpolish(self.model_status)
        self.model_status.style().polish(self.model_status)
        self.statusBar().showMessage(
            f"Ready • Wing area {self.valid_config.wing_area_m2:.2f} m² • "
            "Change any parameter to update geometry and lift")

    def _draw_chart(self):
        cond = self._current_condition()
        if self.last_result is None:
            return
        speeds = list(range(0, 251, 2))
        lifts = lift_vs_airspeed(cond, speeds)
        fig = self.figure
        fig.clear()
        ax = fig.add_subplot(111)
        ax.set_facecolor("#101923")
        ax.plot(speeds, lifts, linewidth=2.2, color="#70d9c5", label="Calculated lift")
        ax.scatter([cond.airspeed_m_s], [self.last_result.lift_newtons], s=45,
                   zorder=3, color="#f2a65a", label="Current condition")
        ax.set_xlabel("True airspeed (m/s)", color="#c5d6e4", fontsize=8)
        ax.set_ylabel("Lift (N)", color="#c5d6e4", fontsize=8)
        ax.tick_params(colors="#9bb1c3", labelsize=8)
        for spine in ax.spines.values():
            spine.set_color("#304252")
        ax.grid(True, alpha=0.2)
        ax.legend(frameon=False, fontsize=8, labelcolor="#c5d6e4")
        fig.tight_layout(pad=0.5)
        self.canvas.draw_idle()

    def closeEvent(self, event):
        self.viewport.shutdown()
        super().closeEvent(event)


STYLESHEET = """
QMainWindow, QWidget { background: #101923; color: #e7eef5; font-family: "Segoe UI"; font-size: 10pt; }
QLabel#appTitle { font-size: 22pt; font-weight: 700; color: #f4f8fc; }
QLabel#subtitle { color: #8da4b8; font-size: 8pt; letter-spacing: 1px; }
QLabel#phaseTag { color: #75d6c3; border: 1px solid #28675f; border-radius: 7px; padding: 7px 12px; font-weight: 600; }
QGroupBox { border: 1px solid #304252; border-radius: 10px; margin-top: 12px; padding: 10px; padding-top: 14px; font-weight: 600; color: #a9c1d4; font-size: 9pt; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; }
QDoubleSpinBox, QComboBox { background: #1b2a38; border: 1px solid #3b5367; border-radius: 6px; padding: 5px; min-width: 110px; color: #f5f8fb; }
QDoubleSpinBox:focus, QComboBox:focus { border: 1px solid #54c6b2; }
QComboBox QAbstractItemView { background: #1b2a38; selection-background-color: #28675f; }
QPushButton { background: #1d3347; border: 1px solid #3b5367; border-radius: 6px; padding: 7px 14px; color: #e7eef5; font-weight: 600; }
QPushButton:hover { background: #28475f; border-color: #54c6b2; }
QPushButton:pressed { background: #28675f; }
QCheckBox { color: #c5d6e4; spacing: 6px; }
QFrame#viewportFrame { border: 1px solid #30495d; border-radius: 8px; background: #0b131b; }
QFrame#metricCard { background: #1a2a39; border: 1px solid #30495d; border-radius: 10px; }
QLabel#metricHeading { color: #9bb1c3; font-size: 8pt; font-weight: 600; background: transparent; }
QLabel#metricValue { color: #70d9c5; font-size: 20pt; font-weight: 700; background: transparent; }
QLabel#metricUnit { color: #9bb1c3; background: transparent; }
QLabel#note { color: #e8c77b; background: #302b20; border-radius: 7px; padding: 8px; font-size: 8pt; }
QLabel#region { color: #9fb4c5; padding: 2px 4px; font-size: 9pt; }
QLabel#secondaryResult { color: #c5d6e4; font-size: 12pt; font-weight: 600; padding: 2px 4px; }
QLabel#derived { color: #70d9c5; font-weight: 600; }
QLabel#geoName { color: #9bb1c3; font-weight: 400; }
QLabel#geoValue { color: #f4f8fc; font-weight: 600; }
QLabel#legend { color: #9bb1c3; font-size: 8pt; }
QLabel#modelOk { color: #8fe0b0; font-weight: 400; font-size: 9pt; }
QLabel#modelBad { color: #ff9b9b; background: #3a2024; border-radius: 6px; padding: 6px; font-weight: 600; font-size: 9pt; }
QStatusBar { color: #a9bdcd; background: #0b131b; }
QScrollBar:vertical { background: #101923; width: 10px; }
QScrollBar::handle:vertical { background: #30495d; border-radius: 5px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QToolTip { background: #1b2a38; color: #e7eef5; border: 1px solid #3b5367; }
"""


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = AeroLiftWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
