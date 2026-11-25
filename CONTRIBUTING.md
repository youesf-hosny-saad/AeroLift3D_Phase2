# Contributing

1. Fork the repository and create a feature branch.
2. Install in editable mode with the test extras: `pip install -e ".[dev]"`.
3. Keep the architecture rules: aerodynamics, geometry and GUI stay in separate modules; the wing area has one source of truth (`WingParams.area_m2`).
4. Run `python -m unittest tests.test_geometry -v` before opening a pull request.
5. Keep the educational disclaimer: do not present results as validated aircraft performance.
