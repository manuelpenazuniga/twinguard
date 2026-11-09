# Contributing

- Use Python 3.12 and the standard library only.
- External services and collaborators are passed in as arguments (constructor or function parameters), so the code can be exercised with fakes in tests; keep it that way.
- Add or update a test under tests/ with every fix.
- Run `python -m pytest -q tests` before opening a merge request.
