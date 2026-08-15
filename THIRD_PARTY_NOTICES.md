# Third-party notices

## Last30Days

- Repository: <https://github.com/mvanhorn/last30days-skill>
- Imported version: `3.21.0` (`v3.21.0`)
- Imported commit: `c7460f6114449ddfe6ea3fc2f23c3d910c0e740c`
- Import date: 2026-08-14
- Destination: `third_party/last30days/`
- License: MIT, Copyright (c) 2026 Matt Van Horn

The directory is a byte-identical copy of every file tracked at the recorded commit. It
includes the upstream source, tests, fixtures, manifests, documentation, lockfile, and
license, including paths that upstream excludes from release archives. Git metadata and
untracked machine state such as environments, caches, credentials, configuration, and
generated research output are not included.

SRD-specific execution restrictions and data conversion live outside the vendor tree in
`src/srd/recent.py`. Refreshes must replace the complete archive, update
`third_party/last30days.manifest.json`, and pass the vendor-integrity test; do not patch the
vendored files silently.
