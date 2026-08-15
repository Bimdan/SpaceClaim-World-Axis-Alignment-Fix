# SpaceClaim World-Axis Alignment Fix v1.0

A community utility for Ansys SpaceClaim 2021 R1 / `SpaceClaim.Api.V19` that detects and corrects very small body/component orientation errors relative to the World X/Y/Z axes.

## Why this exists

Ansys documents a drawing problem where diameter/radius dimensions may not behave correctly when the 3D geometry is not aligned with the default drawing views / World coordinate planes. Their documented workaround is to use the Move tool and manually orient the component or solid body to the World origin axes.

Official Ansys reference:

https://innovationspace.ansys.com/knowledge/forums/topic/faq-discovery-spaceclaim-unable-to-create-diameter-radius-dimensions-only-linear-dimensions-appear/

This script automates a conservative version of that alignment workflow for legacy/imported parts where the misalignment can be too small to see reliably by eye.

In the validation case that led to this tool, the problematic planar face was only about `0.001688104 deg` away from World Z. The geometry otherwise appeared normal, but drawing circular-dimension/centreline behaviour was affected. After alignment to the World axis, the drawing behaviour recovered.

## Tested environment

- Ansys SpaceClaim 2021 R1
- SpaceClaim version: `2021.1.0.11221`
- Script header/API: `SpaceClaim.Api.V19`
- Windows

This package does **not** claim compatibility with later SpaceClaim or Discovery releases. Later APIs should be reviewed and tested separately.

## What the script does

1. You select exactly one planar datum face that is intended to be square to a World axis.
2. The script reads the face normal and transforms it to the current master/World orientation using `DesignFace.GetTransformToMaster()`.
3. It identifies the nearest World X, Y or Z axis.
4. If the face is already aligned within tolerance, it changes nothing.
5. If the misalignment is small enough for automatic correction, it resolves the owning body/component and applies fixed-World-axis corrections using `Move.Rotate(...)`.
6. After the first rotation, it **reacquires the face geometry and normal from SpaceClaim** before checking the result.
7. It only applies the second rotation if the first move matches the mathematically predicted orientation.
8. It reacquires the geometry again and performs a final post-change verification.
9. It never saves the SpaceClaim document automatically.

The fresh geometry reacquisition is important in SpaceClaim 2021 R1: keeping a pre-move `Geometry.Direction` reference can make an immediate post-move check appear unchanged even though `Move.Rotate` physically succeeded.

## Safety limits

The public release is deliberately conservative.

- Exactly one planar face must be selected.
- The selected face must be a true analytic Plane.
- Default automatic-fix limit: `0.05 deg` from the nearest World axis.
- The tool refuses to guess if the same Part is used by multiple component occurrences.
- Step 2 is not applied unless Step 1 passes verification.
- A failed final verification does not trigger another automatic correction.
- The document is never auto-saved.
- Work on a copy until you are comfortable with the tool.

The `0.05 deg` limit is a safety guardrail, not a known SpaceClaim technical limit.

## How to use

1. Open the affected part in SpaceClaim 2021 R1.
2. Open SpaceClaim's Scripting editor and load `SpaceClaim_WorldAxis_Alignment_Fix_v1_0.py`.
3. Select **one planar datum face** that should be aligned with one of the World axes.
   - Good choice: a large machined/top/bottom planar face whose intended orientation is known.
   - Do not select the whole body, an edge, or a cylindrical face.
4. Run the script.
5. The script writes a full diagnostic log and opens a compact action/result file in Windows Notepad.
6. If the result says `AUTO-FIX VERIFIED - ALIGNED`, save the SpaceClaim document manually and test/create the drawing.
7. If the result says `AUTO-FIX CHECK FAILED`, do not repeatedly rerun the tool. Review/undo the issued move(s) as appropriate and inspect the full diagnostic log.

## Output files

The script writes files to the current Windows user's Desktop:

- `SpaceClaim_WorldAxis_Alignment_Fix_v1_0_YYYYMMDD_HHMMSS.txt` — full diagnostic log
- `SpaceClaim_WorldAxis_Alignment_Action.txt` — compact result/action summary opened automatically in Notepad

For privacy, CAD object names are not logged by default. Set:

```python
LOG_TARGET_NAME = True
```

only if you specifically need object names for local debugging.

## Typical successful result

```text
PRE-CHECK deviation:
  0.001688104 deg

Calculated automatic correction:
  Step 1: World X +0.001446317 deg
  Step 2: World Y +0.000870552 deg

STEP 1 CHECK: PASS

FINAL FRESH POST-CHANGE CHECK
Final nearest World axis:
  World Z
Final deviation:
  0.000000000 deg

STATUS: AUTO-FIX VERIFIED - ALIGNED
```

The exact numbers depend on the selected face and part orientation.

## Important limitations

This is **not** a general-purpose CAD orientation solver.

It assumes the selected planar datum face is genuinely intended to be aligned with its nearest World X/Y/Z axis. If a part is intentionally angled, do not use this tool to "fix" it.

The script has been validated against the specific SpaceClaim 2021 R1/API V19 workflow described above. It should be treated as a community utility, not an Ansys-supported product.

## Technical notes for other script authors

The core API operations used are:

- `Selection.GetActive()` / `ConvertToFaces()`
- `face.Shape.Geometry.Frame.DirZ`
- `face.GetTransformToMaster()`
- `Move.Rotate(selection, axisLine, DEG(angle), MoveOptions())`
- `Component.Content` ownership resolution where applicable

The automatic move implementation follows the same `Move.Rotate` scripting pattern shown in Ansys community examples. An Ansys employee example for API V18 uses a World-axis `Line`, `MoveOptions()` and `Move.Rotate(...)` to rotate components:

https://innovationspace.ansys.com/forum/forums/topic/scripting-select-all-geometry-in-file/

## Disclaimer

This script modifies CAD geometry/component placement when an automatic correction is accepted by its checks. Use a working copy and verify the resulting model/drawing before production use. It is provided as-is, without warranty and without official Ansys support.
