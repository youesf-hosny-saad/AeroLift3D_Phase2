"""PyVista scene management embedded in Qt (rendering only, no aero maths).

Each aircraft component owns ONE persistent ``PolyData`` and ONE actor for the
whole session. Parametric updates overwrite the mesh data in place, so
repeated rebuilds do not create new actors or leak render resources.
"""
from __future__ import annotations

import math
import os

os.environ.setdefault("QT_API", "pyside6")   # make qtpy/pyvistaqt use PySide6

import numpy as np
import pyvista as pv
from PySide6.QtWidgets import QVBoxLayout, QWidget
from pyvistaqt import QtInteractor

COMPONENT_STYLE = {
    # name: (display name, colour)
    "fuselage":  ("Fuselage", "#c9d6e2"),
    "wing":      ("Main wing", "#4fb3d9"),
    "htail":     ("Horizontal stabilizer", "#f2a65a"),
    "vtail":     ("Vertical stabilizer", "#e86f6f"),
    "engine":    ("Engine cowling", "#6b7683"),
    "propeller": ("Propeller", "#e8c77b"),
}

VIEWS = ("isometric", "top", "front", "side")


class AircraftViewport(QWidget):
    """Interactive 3D viewport.

    Mouse: left-drag rotate, middle-drag (or shift+left) pan,
    right-drag / wheel zoom.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.plotter = QtInteractor(self, auto_update=False)
        layout.addWidget(self.plotter.interactor if hasattr(self.plotter, "interactor")
                         and isinstance(self.plotter.interactor, QWidget) else self.plotter)

        self._meshes: dict[str, pv.PolyData] = {}
        self._actors: dict[str, object] = {}
        self._grid = pv.PolyData()
        self._grid_actor = None
        self._axes_visible = True
        self._grid_visible = True
        self._first_fit_done = False
        self._center = np.zeros(3)
        self.rebuild_count = 0

        self.plotter.set_background("#0b131b", top="#1d3045")
        self.plotter.add_axes(line_width=3, xlabel="X (aft)", ylabel="Y (right)",
                              zlabel="Z (up)", color="white")

    # -- scene content ---------------------------------------------------
    def update_meshes(self, meshes: dict[str, pv.PolyData]) -> None:
        """Create actors on first call; afterwards overwrite mesh data in place."""
        for name, new in meshes.items():
            if name not in self._meshes:
                self._meshes[name] = pv.PolyData()
                self._meshes[name].copy_from(new, deep=True)
                _, colour = COMPONENT_STYLE[name]
                self._actors[name] = self.plotter.add_mesh(
                    self._meshes[name], color=colour, smooth_shading=False,
                    specular=0.35, specular_power=20, ambient=0.25,
                    name=f"aero_{name}", reset_camera=False, render=False)
            else:
                self._meshes[name].copy_from(new, deep=True)
                self._meshes[name].Modified()
        self._update_ground(meshes)
        if not self._first_fit_done:
            self.set_view("isometric")
            self._first_fit_done = True
        self.rebuild_count += 1
        self.plotter.render()

    def _update_ground(self, meshes) -> None:
        b = np.array([m.bounds for m in meshes.values()])
        xmin, xmax = b[:, 0].min(), b[:, 1].max()
        ymin, ymax = b[:, 2].min(), b[:, 3].max()
        zmin = b[:, 4].min()
        size = 1.5 * max(xmax - xmin, ymax - ymin)
        n = int(max(4, min(40, math.ceil(size))))
        cx, cy = 0.5 * (xmin + xmax), 0.5 * (ymin + ymax)
        plane = pv.Plane(center=(cx, cy, zmin - 0.4), direction=(0, 0, 1),
                         i_size=size, j_size=size, i_resolution=n, j_resolution=n)
        self._grid.copy_from(plane, deep=True)
        self._grid.Modified()
        if self._grid_actor is None:
            self._grid_actor = self.plotter.add_mesh(
                self._grid, style="wireframe", color="#35506a", line_width=1,
                opacity=0.7, name="aero_ground", reset_camera=False, render=False,
                pickable=False)
            self._grid_actor.SetVisibility(self._grid_visible)
        self._center = np.array([cx, cy, 0.5 * (zmin + b[:, 5].max())])

    # -- camera ----------------------------------------------------------
    def set_view(self, name: str) -> None:
        """Engineering views (X aft, Y right, Z up). Top view has nose up-screen."""
        directions = {            # camera offset from focal point, view-up
            "isometric": ((-1.0, 0.9, 0.65), (0, 0, 1)),   # from front-right-above
            "top":       ((0, 0, 1), (-1, 0, 0)),
            "front":     ((-1, 0, 0), (0, 0, 1)),           # looking aft at the nose
            "side":      ((0, 1, 0), (0, 0, 1)),            # from starboard, nose left
        }
        if name not in directions:
            raise ValueError(f"Unknown view '{name}'")
        offset, up = directions[name]
        offset = np.array(offset, float)
        offset /= np.linalg.norm(offset)
        focal = self._center
        self.plotter.camera_position = [tuple(focal + 15.0 * offset), tuple(focal), up]
        if name == "isometric":
            self.plotter.disable_parallel_projection()
        else:
            self.plotter.enable_parallel_projection()
        self.plotter.reset_camera()
        self.plotter.camera.zoom(1.7)
        self.plotter.render()

    def reset_camera(self) -> None:
        self.set_view("isometric")

    # -- display options -------------------------------------------------
    def set_axes_visible(self, visible: bool) -> None:
        self._axes_visible = visible
        (self.plotter.show_axes if visible else self.plotter.hide_axes)()
        self.plotter.render()

    def set_grid_visible(self, visible: bool) -> None:
        self._grid_visible = visible
        if self._grid_actor is not None:
            self._grid_actor.SetVisibility(visible)
        self.plotter.render()

    def screenshot(self, path: str) -> None:
        self.plotter.screenshot(path)

    def shutdown(self) -> None:
        """Release VTK resources (call from the window's closeEvent)."""
        try:
            self.plotter.close()
        except Exception:
            pass
