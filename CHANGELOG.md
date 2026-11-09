# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Added

- **`opencv-python-headless` as an explicit runtime dependency** — `camelot`
  imports `cv2` at module load, but `camelot-py` declares opencv only under its
  `cv`/`base` extras, so it had only ever been present in `uv.lock`
  transitively.

### Changed

- **Development environment migrated to vigOS devkit 1.11.1** — a Nix flake +
  `direnv` dev-shell replaces the devcontainer, with flake-generated pre-commit
  hooks, `just` recipes, and GitHub Actions CI (lint, test, commit checks).
- **Dev tooling moved to a PEP 735 dependency group** — `ruff` and `pre-commit`
  are now provided by the dev-shell rather than pinned in the project.
- **CertoOne statement pages are selected by content** — the pages handed to
  `camelot` are those carrying the transaction header or the closing balance,
  instead of a page range derived from the total page count. An unreadable
  layout is now reported: a PDF with no such page raises `ValueError` where it
  used to write a CSV the importer could not read, and a dated row with no
  amount in either column is skipped instead of booked as a zero.

### Removed

- **`.devcontainer/`** — superseded by the flake dev-shell; enter it with
  `direnv allow` or `nix develop`.

### Fixed

- **`import beancount_importers` failing with `ModuleNotFoundError: No module
  named 'cv2'`** — a dependency re-resolution dropped the undeclared transitive
  `opencv-python-headless`, breaking every import of the package.
- **CertoOne statements with a quarterly cashback summary failing to parse**
  ([#11](https://github.com/c-vigo/beancount-importers/issues/11)) — the extra
  page shifted the scanned page range onto the cashback table, whose three
  columns were unpacked as the two-column balance table and raised
  `ValueError: too many values to unpack`. Since the exception escaped
  `extract()`, one such statement aborted the whole reconciler run, not just
  its own file.

### Security
