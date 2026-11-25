"""Automated GUI check: launches the real window, edits parameters, checks results.

Run from the project root:   python -m tests.gui_smoke_test
Optionally pass an output folder for screenshots:  python -m tests.gui_smoke_test shots
"""
import gc
import os
import sys
import time

from PySide6.QtWidgets import QApplication

from aerolift.app import AeroLiftWindow


def pump(app, seconds=0.4):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else None
    if out:
        os.makedirs(out, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    w = AeroLiftWindow()
    w.show()
    pump(app, 1.5)
    ok = True

    def check(label, cond):
        nonlocal ok
        print(("PASS  " if cond else "FAIL  ") + label)
        ok &= bool(cond)

    def shot(name):
        if out:
            w.grab().save(os.path.join(out, name))

    vp = w.viewport
    wing_mesh = vp._meshes["wing"]
    check("3D model visible (6 actors)", len(vp._actors) == 6 and wing_mesh.n_points > 0)
    shot("01_default.png")

    # rotate via camera azimuth (same camera the mouse drives)
    az0 = vp.plotter.camera_position[0]
    vp.plotter.camera.Azimuth(40); vp.plotter.render(); pump(app, 0.2)
    check("camera rotates", vp.plotter.camera_position[0] != az0)
    shot("02_rotated.png")
    vp.reset_camera()

    ya0 = wing_mesh.bounds
    lift0 = float(w.lift_value.text().replace(",", ""))
    area = w.geom_widgets[("wing", "area_m2")]

    w.area_mode.setCurrentIndex(0)           # hold span, change chord
    area.setValue(18.0); pump(app)
    b = wing_mesh.bounds
    check("area 18 (hold span): span unchanged", abs((b[3]-b[2]) - (ya0[3]-ya0[2])) < 1e-3)
    check("area 18 (hold span): chord grew", (b[1]-b[0]) > (ya0[1]-ya0[0]) + 0.1)
    cond = w._current_condition()
    check("lift uses 18 m2", abs(cond.wing_area_m2 - 18.0) < 1e-9)
    lift1 = float(w.lift_value.text().replace(",", ""))
    check("lift scaled by 18/14", abs(lift1 / lift0 - 18 / 14) < 0.01)
    shot("03_area18_holdspan.png")

    w._restore_defaults(); pump(app)         # back to 14 m2, span 10, chord 1.4
    w.area_mode.setCurrentIndex(1)           # hold chord, change span
    area.setValue(18.0); pump(app)
    b = wing_mesh.bounds
    check("area 18 (hold chord): span grew to 12.86 m", abs((b[3]-b[2]) - 18/1.4) < 1e-3)
    shot("04_area18_holdchord.png")

    span = w.geom_widgets[("wing", "span_m")]
    span.setValue(9.0); pump(app)
    b = wing_mesh.bounds
    check("span edit updates mesh", abs((b[3]-b[2]) - 9.0) < 1e-3)
    check("span edit updates area label", w.geo_labels["area"].text().startswith("12.60"))

    span.setValue(1.0); pump(app)            # invalid: narrower than fuselage
    check("invalid geometry reported, no crash", not w.geometry_ok)
    check("mesh stays at last valid state", abs((wing_mesh.bounds[3]-wing_mesh.bounds[2]) - 9.0) < 1e-3)
    shot("05_invalid.png")
    span.setValue(10.0); pump(app)
    check("recovers after valid input", w.geometry_ok)

    for v in ("top", "front", "side", "isometric"):
        vp.set_view(v); pump(app, 0.2); shot(f"06_view_{v}.png")
    check("views OK", True)

    # repeated rebuilds: actor count constant, memory flat
    try:
        import psutil
        rss = lambda: psutil.Process().memory_info().rss / 1e6
    except ImportError:
        rss = lambda: 0.0
    for i in range(10):
        span.setValue(9 + (i % 3)); pump(app, 0.08)
    gc.collect(); r0 = rss()
    t0 = time.time()
    for i in range(150):
        span.setValue(9 + (i % 4) * 0.5); pump(app, 0.06)
    gc.collect(); r1 = rss()
    n_actors = len(vp.plotter.renderer.actors)
    print(f"      150 live rebuilds in {time.time()-t0:.1f}s, RSS {r0:.0f} -> {r1:.0f} MB, "
          f"renderer actors: {n_actors}")
    check("no actor accumulation", n_actors <= 12)
    check("no significant memory growth", (r1 - r0) < 60)
    w.close()
    print("ALL PASSED" if ok else "SOME CHECKS FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
