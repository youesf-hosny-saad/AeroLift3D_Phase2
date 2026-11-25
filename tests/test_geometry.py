"""Geometry tests (no GUI needed).  Run:  python -m unittest tests.test_geometry -v"""
import gc
import os
import unittest

import numpy as np

from aerolift.aircraft_model import AircraftConfig, GeometryError, trapezoid_chords
from aerolift.geometry import (COMPONENTS, build_aircraft, build_wing,
                               build_horizontal_stabilizer, measured_planform_area)


class GeometryTests(unittest.TestCase):
    def test_default_components_valid(self):
        meshes, warnings = build_aircraft(AircraftConfig())
        self.assertEqual(set(meshes), set(COMPONENTS))
        for name, m in meshes.items():
            self.assertGreater(m.n_cells, 100, name)
            self.assertTrue(np.all(np.isfinite(m.points)), name)

    def test_trapezoid_area_formula(self):
        cr, ct = trapezoid_chords(1.4, 0.75)
        self.assertAlmostEqual(10.0 / 2 * (cr + ct), 10.0 * 1.4)

    def test_wing_mesh_area_matches_declared_area(self):
        for span, chord, taper, sweep, dih in [(10, 1.4, 0.75, 0, 3), (12, 1.5, 0.5, 15, 5),
                                                (8, 2.0, 1.0, -10, 0), (9, 1.1, 0.3, 25, -2)]:
            c = AircraftConfig()
            w = c.wing
            w.span_m, w.mean_chord_m, w.taper_ratio = span, chord, taper
            w.quarter_chord_sweep_deg, w.dihedral_deg, w.incidence_deg = sweep, dih, 0.0
            area_mesh = measured_planform_area(build_wing(w))
            self.assertAlmostEqual(area_mesh, w.area_m2, delta=0.005 * w.area_m2,
                                   msg=f"{span},{chord},{taper}")

    def test_htail_mesh_area(self):
        c = AircraftConfig()
        c.htail.incidence_deg = 0.0
        a = measured_planform_area(build_horizontal_stabilizer(c.htail))
        self.assertAlmostEqual(a, c.htail.area_m2, delta=0.005 * c.htail.area_m2)

    def test_area_edit_keep_span(self):
        c = AircraftConfig()
        c.wing.set_area_keep_span(18.0)
        self.assertAlmostEqual(c.wing.span_m, 10.0)
        self.assertAlmostEqual(c.wing.area_m2, 18.0)
        b = build_wing(c.wing).bounds
        self.assertAlmostEqual(b[3] - b[2], 10.0, places=4)

    def test_area_edit_keep_chord(self):
        c = AircraftConfig()
        c.wing.set_area_keep_chord(18.0)
        self.assertAlmostEqual(c.wing.mean_chord_m, 1.4)
        b = build_wing(c.wing).bounds
        self.assertAlmostEqual(b[3] - b[2], 18.0 / 1.4, places=4)
        self.assertAlmostEqual(c.wing_area_m2, 18.0)

    def test_wing_change_leaves_other_components_identical(self):
        c = AircraftConfig()
        m1, _ = build_aircraft(c)
        c.wing.set_area_keep_chord(18.0)
        m2, _ = build_aircraft(c)
        for name in COMPONENTS:
            same = np.allclose(m1[name].points, m2[name].points) \
                if m1[name].n_points == m2[name].n_points else False
            self.assertEqual(same, name != "wing", name)

    def test_propeller_ahead_of_fuselage(self):
        meshes, _ = build_aircraft(AircraftConfig())
        self.assertLess(meshes["propeller"].bounds[1], meshes["fuselage"].bounds[0])

    def test_invalid_inputs_rejected(self):
        bad = []
        c = AircraftConfig(); c.wing.span_m = 0; bad.append(c)
        c = AircraftConfig(); c.wing.mean_chord_m = -1; bad.append(c)
        c = AircraftConfig(); c.wing.taper_ratio = 0; bad.append(c)
        c = AircraftConfig(); c.wing.taper_ratio = 2.5; bad.append(c)
        c = AircraftConfig(); c.wing.span_m = 1.0; bad.append(c)
        c = AircraftConfig(); c.wing.span_m = float("nan"); bad.append(c)
        c = AircraftConfig(); c.fuselage.nose_length_m = 5; c.fuselage.tail_length_m = 5; bad.append(c)
        c = AircraftConfig(); c.htail.area_m2 = 0; bad.append(c)
        c = AircraftConfig(); c.vtail.height_m = -1; bad.append(c)
        for cfg in bad:
            with self.assertRaises(GeometryError):
                build_aircraft(cfg)

    def test_repeated_rebuild_no_growth(self):
        """200 rebuilds: Python object count and RSS must stay roughly flat."""
        try:
            import psutil
            proc = psutil.Process(os.getpid())
            rss = lambda: proc.memory_info().rss / 1e6
        except ImportError:
            rss = lambda: 0.0
        c = AircraftConfig()
        for i in range(20):                     # warm-up
            c.wing.span_m = 9 + (i % 5) * 0.4
            build_aircraft(c)
        gc.collect()
        r0, n0 = rss(), len(gc.get_objects())
        for i in range(200):
            c.wing.span_m = 9 + (i % 7) * 0.4
            build_aircraft(c)
        gc.collect()
        r1, n1 = rss(), len(gc.get_objects())
        print(f"\nrebuild x200: RSS {r0:.1f} -> {r1:.1f} MB, objects {n0} -> {n1}")
        self.assertLess(n1 - n0, 2000)
        self.assertLess(r1 - r0, 40.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
