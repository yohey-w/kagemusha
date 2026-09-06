"""Marks tests/ as a package so `python3 -m unittest tests/unit_codex_logs.py`
resolves THIS directory.

Without it, `tests` is only a namespace portion, and any regular `tests`
package that an editable install has put on sys.path wins instead — the test
run then fails with "no module named tests.unit_codex_logs" on a machine where
nothing is wrong with this repo. An empty package file is cheaper than that
half-hour.
"""
