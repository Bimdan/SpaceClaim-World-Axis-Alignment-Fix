# Changelog

## v1.0.0 - 2026-08-14

First sanitized community release.

- Target: Ansys SpaceClaim 2021 R1 / `SpaceClaim.Api.V19`.
- Detects tiny planar datum misalignment relative to the nearest World X/Y/Z axis.
- Applies conservative two-step fixed-World-axis correction using `Move.Rotate(...)`.
- Reacquires face geometry after every move before verification.
- Performs intermediate and final post-change checks.
- Refuses large angular errors (`0.05 deg` default limit).
- Refuses ambiguous multiple component occurrences.
- Does not auto-save.
- Opens a compact result in external Notepad and writes a full diagnostic log.
- Object-name logging disabled by default for privacy.
