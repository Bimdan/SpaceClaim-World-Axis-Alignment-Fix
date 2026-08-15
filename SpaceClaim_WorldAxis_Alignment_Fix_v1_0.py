# Python Script, API Version = V19
# -*- coding: utf-8 -*-
#
# SpaceClaim World-Axis Alignment Fix - Community Release v1.0.0
#
# Compatibility
# ---------------------------------------------------------------------------
# Tested with Ansys SpaceClaim 2021 R1 / SpaceClaim.Api.V19.
# Developed and validated against SpaceClaim 2021.1.0.11221.
# Later SpaceClaim/Discovery releases and API versions are NOT claimed/tested.
#
# Purpose
# ---------------------------------------------------------------------------
# Ansys documents a drawing issue where diameter/radius dimensions can fail
# when 3D geometry is not aligned with the default drawing views / World axes.
# This script automates a conservative version of that alignment workflow.
#
# Usage
# ---------------------------------------------------------------------------
# 1) Work on a copy until you are comfortable with the tool.
# 2) Select exactly ONE planar datum face that is intended to be square to
#    one of the World X/Y/Z axes.
# 3) Run the script.
# 4) If already aligned, nothing is changed.
# 5) If a small misalignment is detected, the script calculates and applies
#    fixed-World-axis Move.Rotate corrections to the owning body/component.
# 6) After EACH rotation it reacquires the face geometry and verifies that
#    the actual result matches the predicted result.
# 7) It performs a final alignment verification and NEVER auto-saves.
#
# Safety limits
# ---------------------------------------------------------------------------
# - Only a true planar face is accepted.
# - Automatic correction is refused above MAX_AUTO_FIX_DEG.
# - Multiple component occurrences are not guessed.
# - Step 2 is not applied unless Step 1 verifies.
# - No automatic retry is attempted after a failed verification.
# - The document is never saved automatically.
#
# Privacy
# ---------------------------------------------------------------------------
# LOG_TARGET_NAME defaults to False so logs do not unnecessarily include
# internal CAD object names. Change it to True locally if needed for debugging.
#
# Community release: provided as-is, without warranty.
# See README.md in the release package before use.

import math
import os
import datetime

RELEASE_VERSION = "1.0.0"
ALIGN_TOL_DEG = 0.000001
LOG_TARGET_NAME = False
MAX_AUTO_FIX_DEG = 0.050000
STEP_VERIFY_TOL_DEG = 0.000005
ANGLE_DP = 9
OPEN_ACTION_IN_NOTEPAD = True

_lines = []
_action = []
_moves_issued = 0


def out(text=""):
    try:
        print(text)
    except:
        pass
    try:
        _lines.append(str(text))
    except:
        pass


def act(text=""):
    try:
        _action.append(str(text))
    except:
        pass


def type_name(obj):
    if obj is None:
        return "<None>"
    try:
        return obj.GetType().FullName
    except:
        try:
            return type(obj).__name__
        except:
            return "<unknown>"


def object_name(obj):
    if obj is None:
        return "<None>"
    for prop in ("Name", "DisplayName"):
        try:
            value = getattr(obj, prop)
            if value is not None and str(value) != "":
                return str(value)
        except:
            pass
    return type_name(obj)


def same_object(a, b):
    if a is None or b is None:
        return False
    try:
        return bool(a == b)
    except:
        return id(a) == id(b)


def selection_items(sel):
    if sel is None:
        return []
    try:
        return list(sel.Items)
    except:
        pass
    try:
        return list(sel)
    except:
        pass
    return []


def xyz(obj):
    if obj is None:
        raise Exception("XYZ object is None")
    try:
        return (float(obj.X), float(obj.Y), float(obj.Z))
    except:
        pass
    try:
        return (float(obj.x), float(obj.y), float(obj.z))
    except:
        pass
    raise Exception("Could not read X/Y/Z from %s" % type_name(obj))


def normalize(v):
    x, y, z = v
    m = math.sqrt(x*x + y*y + z*z)
    if m <= 0.0:
        raise Exception("Zero-length vector")
    return (x/m, y/m, z/m)


def clamp(v, lo, hi):
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


def deg(rad):
    return rad * 180.0 / math.pi


def fmt_angle(v):
    return ("%+." + str(ANGLE_DP) + "f") % v


def print_normal(label, n):
    out(label)
    out("  X = %.12f" % n[0])
    out("  Y = %.12f" % n[1])
    out("  Z = %.12f" % n[2])


def get_face_surface(face):
    attempts = []
    try:
        shape = face.Shape
        attempts.append("face.Shape = %s" % type_name(shape))
    except Exception as ex:
        return None, ["face.Shape failed: %s" % str(ex)]

    try:
        g = shape.Geometry
        if g is not None:
            return g, attempts
    except Exception as ex:
        attempts.append("face.Shape.Geometry failed: %s" % str(ex))

    try:
        g = shape.GetGeometry()
        if g is not None:
            return g, attempts
    except Exception as ex:
        attempts.append("face.Shape.GetGeometry() failed: %s" % str(ex))

    return None, attempts


def get_surface_normal(surface):
    attempts = []
    if surface is None:
        return None, attempts

    s_type = type_name(surface)
    attempts.append("surface type = %s" % s_type)

    if "Plane" not in s_type:
        attempts.append("Safety stop: selected surface is not a Plane")
        return None, attempts

    try:
        frame = surface.Frame
        attempts.append("surface.Frame = %s" % type_name(frame))
        for name in ("DirZ", "DirectionZ", "ZDirection"):
            try:
                n = getattr(frame, name)
                if n is not None:
                    attempts.append("normal = surface.Frame.%s" % name)
                    return n, attempts
            except:
                pass
    except Exception as ex:
        attempts.append("surface.Frame failed: %s" % str(ex))

    return None, attempts


def transform_existing_direction(matrix, direction_obj):
    attempts = []
    try:
        transformed = matrix * direction_obj
        return transformed, normalize(xyz(transformed)), "matrix * existing Direction", attempts
    except Exception as ex:
        attempts.append("matrix * Direction failed: %s" % str(ex))

    try:
        transformed = direction_obj * matrix
        return transformed, normalize(xyz(transformed)), "existing Direction * matrix", attempts
    except Exception as ex:
        attempts.append("Direction * matrix failed: %s" % str(ex))

    return None, None, None, attempts


def read_current_world_normal(face, local_normal_obj):
    matrix = face.GetTransformToMaster()
    transformed_obj, n, method, attempts = transform_existing_direction(matrix, local_normal_obj)
    if n is None:
        raise Exception("Could not transform face normal to master: %s" % "; ".join(attempts))
    return n, method, matrix


def reacquire_face_state(face, stage_label):
    """
    Important: reacquire the surface and Direction after every Move.Rotate.
    No pre-move Geometry.Direction object is reused for verification.
    """
    surface, surface_attempts = get_face_surface(face)
    if surface is None:
        raise Exception(
            "%s: could not reacquire face surface: %s"
            % (stage_label, "; ".join(surface_attempts))
        )

    normal_obj, normal_attempts = get_surface_normal(surface)
    if normal_obj is None:
        raise Exception(
            "%s: could not reacquire planar face normal: %s"
            % (stage_label, "; ".join(normal_attempts))
        )

    local_n = normalize(xyz(normal_obj))
    world_n, method, matrix = read_current_world_normal(face, normal_obj)

    return surface, normal_obj, local_n, world_n, method, matrix


def rot_x(n, a):
    x, y, z = n
    c = math.cos(a)
    s = math.sin(a)
    return (x, y*c - z*s, y*s + z*c)


def rot_y(n, a):
    x, y, z = n
    c = math.cos(a)
    s = math.sin(a)
    return (x*c + z*s, y, -x*s + z*c)


def rot_z(n, a):
    x, y, z = n
    c = math.cos(a)
    s = math.sin(a)
    return (x*c - y*s, x*s + y*c, z)


def rotate_theoretical(n, axis, angle_deg):
    a = angle_deg * math.pi / 180.0
    if axis == "X":
        return normalize(rot_x(n, a))
    if axis == "Y":
        return normalize(rot_y(n, a))
    if axis == "Z":
        return normalize(rot_z(n, a))
    raise Exception("Unknown theoretical rotation axis: %s" % axis)


def correction(n):
    x, y, z = normalize(n)
    vals = (abs(x), abs(y), abs(z))
    idx = vals.index(max(vals))

    if (x, y, z)[idx] < 0.0:
        x, y, z = -x, -y, -z

    n0 = (x, y, z)

    if idx == 2:
        ax = math.atan2(y, z)
        n1 = rot_x(n0, ax)
        ay = math.atan2(-n1[0], n1[2])
        n2 = rot_y(n1, ay)
        d = deg(math.acos(clamp(z, -1.0, 1.0)))
        return "Z", d, [("X", deg(ax)), ("Y", deg(ay))], normalize(n2)

    elif idx == 0:
        ay = math.atan2(z, x)
        n1 = rot_y(n0, ay)
        az = math.atan2(-n1[1], n1[0])
        n2 = rot_z(n1, az)
        d = deg(math.acos(clamp(x, -1.0, 1.0)))
        return "X", d, [("Y", deg(ay)), ("Z", deg(az))], normalize(n2)

    else:
        az = math.atan2(x, y)
        n1 = rot_z(n0, az)
        ax = math.atan2(-n1[2], n1[1])
        n2 = rot_x(n1, ax)
        d = deg(math.acos(clamp(y, -1.0, 1.0)))
        return "Y", d, [("Z", deg(az)), ("X", deg(ax))], normalize(n2)


def deviation(n):
    x, y, z = normalize(n)
    best = max(abs(x), abs(y), abs(z))
    return deg(math.acos(clamp(best, -1.0, 1.0)))


def plane_normal_difference_deg(a, b):
    a = normalize(a)
    b = normalize(b)
    dot = a[0]*b[0] + a[1]*b[1] + a[2]*b[2]
    dot = abs(clamp(dot, -1.0, 1.0))
    return deg(math.acos(dot))


def get_all_components(root):
    try:
        return list(root.GetAllComponents())
    except:
        pass

    result = []

    def walk_part(part, depth):
        if part is None or depth > 12:
            return
        try:
            comps = list(part.Components)
        except:
            comps = []
        for comp in comps:
            result.append(comp)
            try:
                content = comp.Content
            except:
                content = None
            if content is not None:
                walk_part(content, depth + 1)

    walk_part(root, 0)
    return result


def resolve_move_target(face):
    body = face.Parent
    part = body.Parent
    root = GetRootPart()

    if same_object(part, root):
        return body, "DesignBody in root Part", body, part

    matches = []
    for comp in get_all_components(root):
        try:
            content = comp.Content
        except:
            content = None
        if same_object(content, part):
            matches.append(comp)

    if len(matches) == 1:
        return matches[0], "owning Component", body, part

    if len(matches) > 1:
        raise Exception(
            "The selected Part is used by %d Component occurrences. "
            "The tool will not guess which occurrence to move." % len(matches)
        )

    raise Exception(
        "The selected body is not in the root Part and the tool could not resolve "
        "exactly one owning Component.Content."
    )


def get_world_anchor(face, body, face_to_master):
    errors = []

    try:
        box = body.Shape.GetBoundingBox(face_to_master)
        center = box.Center
        xyz(center)
        return center, "body.Shape.GetBoundingBox(faceToMaster).Center", errors
    except Exception as ex:
        errors.append("World body bounding-box center failed: %s" % str(ex))

    try:
        surface = face.Shape.Geometry
        local_origin = surface.Frame.Origin
        world_origin = face_to_master * local_origin
        xyz(world_origin)
        return world_origin, "face plane Frame.Origin transformed to master", errors
    except Exception as ex:
        errors.append("Plane-origin fallback failed: %s" % str(ex))

    return None, None, errors


def direction_for_axis(axis):
    if axis == "X":
        return Direction.DirX
    if axis == "Y":
        return Direction.DirY
    if axis == "Z":
        return Direction.DirZ
    raise Exception("Unknown Move axis: %s" % axis)


def build_world_axis_line(anchor_point, axis):
    return Line.Create(anchor_point, direction_for_axis(axis))


def apply_move_rotation(target_selection, anchor_point, axis, angle_deg):
    global _moves_issued

    axis_line = build_world_axis_line(anchor_point, axis)
    options = MoveOptions()
    api_angle = DEG(angle_deg)

    result = Move.Rotate(
        target_selection,
        axis_line,
        api_angle,
        options
    )

    _moves_issued += 1
    return result


def desktop():
    try:
        import System
        return System.Environment.GetFolderPath(
            System.Environment.SpecialFolder.Desktop
        )
    except:
        return os.path.expanduser("~")


def write_file(path, lines):
    f = open(path, "w")
    try:
        f.write("\n".join(lines))
        f.write("\n")
    finally:
        f.close()


def finish_outputs():
    out("")
    out("================================================================")
    out(" ACTION REQUIRED - LAST SECTION")
    out("================================================================")

    for line in _action:
        out(line)

    out("================================================================")

    desk = desktop()
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(
        desk,
        "SpaceClaim_WorldAxis_Alignment_Fix_v1_0_%s.txt" % stamp
    )
    action_path = os.path.join(
        desk,
        "SpaceClaim_WorldAxis_Alignment_Action.txt"
    )

    try:
        write_file(log_path, _lines)
        print("")
        print("Full diagnostic log:")
        print(log_path)
    except Exception as ex:
        log_path = None
        print("")
        print("Full log write failed: %s" % str(ex))

    compact = [
        "SPACECLAIM WORLD-AXIS ALIGNMENT FIX v1.0",
        "============================================",
        ""
    ]
    compact.extend(_action)
    compact.extend([
        "",
        "============================================",
        "SAFETY",
        "============================================",
        "",
        "THIS TOOL CAN MODIFY THE SELECTED BODY/COMPONENT.",
        "",
        "THE TOOL NEVER SAVES THE DOCUMENT AUTOMATICALLY.",
        "",
        "If AUTO-FIX VERIFIED - ALIGNED:",
        "  1) Save the SpaceClaim document.",
        "  2) Test/create the drawing.",
        "",
        "If AUTO-FIX CHECK FAILED:",
        "  DO NOT save yet.",
        "  Do not rerun the tool repeatedly after a failed verification.",
        "  Review the full log first.",
        "",
        "Move.Rotate operations issued this run: %d" % _moves_issued
    ])

    if log_path:
        compact.extend([
            "",
            "Full diagnostic log:",
            log_path
        ])

    try:
        write_file(action_path, compact)
        print("")
        print("Action instructions:")
        print(action_path)

        if OPEN_ACTION_IN_NOTEPAD:
            try:
                import System
                p = System.Diagnostics.Process()
                p.StartInfo.FileName = "notepad.exe"
                p.StartInfo.Arguments = '"%s"' % action_path
                p.StartInfo.UseShellExecute = True
                p.Start()
            except Exception as ex:
                print("")
                print("Could not launch Notepad: %s" % str(ex))

    except Exception as ex:
        print("")
        print("Action file write failed: %s" % str(ex))


out("")
out("================================================================")
out(" SPACECLAIM WORLD-AXIS ALIGNMENT FIX v1.0 - API V19")
out(" AUTOMATIC CORRECTION + POST-CHANGE VERIFICATION")
out("================================================================")
out("")
out("WARNING: THIS TOOL CAN MODIFY THE SELECTED BODY/COMPONENT.")
out("THE TOOL DOES NOT SAVE THE DOCUMENT.")
out("")

try:
    active = Selection.GetActive()
    face_selection = active.ConvertToFaces()
    faces = selection_items(face_selection)
except Exception as ex:
    faces = []
    out("Selection error:")
    out("  %s" % str(ex))


if len(faces) != 1:
    out("STOP: Select exactly ONE planar datum face.")
    out("Faces detected: %d" % len(faces))

    act("NO CHANGE MADE.")
    act("")
    act("Select exactly ONE planar datum face and rerun the tool.")

else:
    face = faces[0]

    out("Selected face:")
    out("  type = %s" % type_name(face))
    out("")

    surface, surface_attempts = get_face_surface(face)
    normal_obj, normal_attempts = get_surface_normal(surface)

    if normal_obj is None:
        out("RESULT: NO SAFE PLANAR FACE NORMAL")
        for item in surface_attempts:
            out("  %s" % item)
        for item in normal_attempts:
            out("  %s" % item)

        act("NO CHANGE MADE.")
        act("")
        act("The tool requires exactly one planar datum face.")

    else:
        try:
            local_n = normalize(xyz(normal_obj))
            current_n, transform_method, face_to_master = read_current_world_normal(
                face,
                normal_obj
            )
        except Exception as ex:
            out("RESULT: PRE-CHECK FAILED")
            out("  %s" % str(ex))

            act("NO CHANGE MADE.")
            act("")
            act("The tool could not complete the orientation pre-check.")
            act("Send the full diagnostic log before modifying the part.")

        else:
            print_normal("LOCAL ACIS face normal:", local_n)
            out("")
            print_normal("CURRENT FACE-TO-MASTER normal:", current_n)
            out("")
            out("Transform method:")
            out("  %s" % transform_method)

            axis_name, initial_dev, steps, final_predicted = correction(current_n)

            out("")
            out("Nearest World axis:")
            out("  World %s" % axis_name)
            out("")
            out("PRE-CHECK deviation:")
            out("  %.*f deg" % (ANGLE_DP, initial_dev))
            out("")
            out("Calculated automatic correction:")
            for i, step in enumerate(steps):
                out(
                    "  Step %d: World %s %s deg"
                    % (i + 1, step[0], fmt_angle(step[1]))
                )

            if initial_dev <= ALIGN_TOL_DEG:
                out("")
                out("STATUS: ALREADY ALIGNED")

                act("VERIFICATION PASS - ALREADY ALIGNED")
                act("")
                act("Nearest World axis: %s" % axis_name)
                act("Current deviation: %.*f deg" % (ANGLE_DP, initial_dev))
                act("")
                act("NO CHANGE WAS MADE.")
                act("")
                act("You can save/test the drawing.")

            elif initial_dev > MAX_AUTO_FIX_DEG:
                out("")
                out("STATUS: AUTO-FIX REFUSED - ERROR TOO LARGE")
                out(
                    "Maximum automatic-fix deviation: %.6f deg"
                    % MAX_AUTO_FIX_DEG
                )

                act("NO CHANGE MADE.")
                act("")
                act("AUTOMATIC CORRECTION REFUSED.")
                act("Measured deviation: %.*f deg" % (ANGLE_DP, initial_dev))
                act("Automatic correction limit: %.6f deg" % MAX_AUTO_FIX_DEG)
                act("")
                act("Use the documented manual alignment workflow or investigate this part before retrying.")

            else:
                preflight_ok = True

                try:
                    target, target_kind, body, owning_part = resolve_move_target(face)

                    out("")
                    out("Automatic move target:")
                    out("  kind = %s" % target_kind)
                    out("  type = %s" % type_name(target))
                    if LOG_TARGET_NAME:
                        out("  name = %s" % object_name(target))
                    else:
                        out("  name = <not logged; LOG_TARGET_NAME=False>")

                    anchor_point, anchor_source, anchor_errors = get_world_anchor(
                        face,
                        body,
                        face_to_master
                    )

                    if anchor_point is None:
                        raise Exception("; ".join(anchor_errors))

                    ax, ay, az = xyz(anchor_point)

                    out("")
                    out("World rotation anchor:")
                    out("  source = %s" % anchor_source)
                    out("  X = %.12f" % ax)
                    out("  Y = %.12f" % ay)
                    out("  Z = %.12f" % az)

                    target_selection = Selection.Create(target)

                    for step_axis, step_angle in steps:
                        test_line = build_world_axis_line(anchor_point, step_axis)
                        if test_line is None:
                            raise Exception(
                                "Line.Create returned None for World %s"
                                % step_axis
                            )

                    test_options = MoveOptions()
                    test_deg = DEG(steps[0][1])

                except Exception as ex:
                    preflight_ok = False

                    out("")
                    out("STATUS: AUTO-FIX PREFLIGHT FAILED")
                    out("  %s" % str(ex))

                    act("NO CHANGE MADE.")
                    act("")
                    act("PRE-FLIGHT FAILED.")
                    act("No Move.Rotate operation was issued.")
                    act("")
                    act("Send the full diagnostic log for investigation.")

                if preflight_ok:
                    step1_axis = steps[0][0]
                    step1_angle = steps[0][1]
                    predicted_after_1 = rotate_theoretical(
                        current_n,
                        step1_axis,
                        step1_angle
                    )

                    out("")
                    out("------------------------------------------------------------")
                    out("AUTO-FIX STEP 1")
                    out("------------------------------------------------------------")
                    out(
                        "World %s rotation = %s deg"
                        % (step1_axis, fmt_angle(step1_angle))
                    )

                    step1_command_ok = True

                    try:
                        result1 = apply_move_rotation(
                            target_selection,
                            anchor_point,
                            step1_axis,
                            step1_angle
                        )
                        out("Move.Rotate result type:")
                        out("  %s" % type_name(result1))
                    except Exception as ex:
                        step1_command_ok = False
                        out("STEP 1 Move.Rotate EXCEPTION:")
                        out("  %s" % str(ex))

                    if not step1_command_ok:
                        act("AUTO-FIX CHECK FAILED.")
                        act("")
                        act("Step 1 could not be completed safely.")
                        act(
                            "Move.Rotate operations issued: %d"
                            % _moves_issued
                        )
                        act("")
                        act("DO NOT SAVE until the model is reviewed.")
                        act("Send the full diagnostic log.")

                    else:
                        step1_verify_ok = True

                        try:
                            after1_surface, after1_normal_obj, after1_local_n, \
                                measured_after_1, method_after_1, matrix_after_1 = \
                                reacquire_face_state(face, "POST-STEP-1")

                            step1_difference = plane_normal_difference_deg(
                                predicted_after_1,
                                measured_after_1
                            )

                            out("")
                            out("POST-STEP-1: FRESH GEOMETRY REACQUIRED")
                            print_normal(
                                "Refreshed LOCAL normal after Step 1:",
                                after1_local_n
                            )
                            out("")
                            print_normal(
                                "Predicted normal after Step 1:",
                                predicted_after_1
                            )
                            out("")
                            print_normal(
                                "Refreshed measured normal after Step 1:",
                                measured_after_1
                            )
                            out("")
                            out("Step 1 predicted-vs-measured difference:")
                            out(
                                "  %.*f deg"
                                % (ANGLE_DP, step1_difference)
                            )
                            out("Step 1 measured deviation:")
                            out(
                                "  %.*f deg"
                                % (
                                    ANGLE_DP,
                                    deviation(measured_after_1)
                                )
                            )

                            if step1_difference > STEP_VERIFY_TOL_DEG:
                                step1_verify_ok = False

                        except Exception as ex:
                            step1_verify_ok = False
                            out("")
                            out("STEP 1 FRESH POST-CHECK FAILED:")
                            out("  %s" % str(ex))

                        if not step1_verify_ok:
                            out("")
                            out("STATUS: AUTO-FIX ABORTED AFTER STEP 1")
                            out("Step 2 was NOT applied.")

                            act("AUTO-FIX CHECK FAILED.")
                            act("")
                            act("The tool applied Step 1 and reacquired fresh geometry,")
                            act("but the post-change check did not match prediction.")
                            act("")
                            act("STEP 2 WAS NOT APPLIED.")
                            act(
                                "Move.Rotate operations issued: %d"
                                % _moves_issued
                            )
                            act("")
                            act("DO NOT SAVE yet.")
                            act("Use Undo for the issued move if required,")
                            act("then send the full diagnostic log.")

                        else:
                            step2_axis = steps[1][0]
                            step2_angle = steps[1][1]

                            predicted_after_2 = rotate_theoretical(
                                measured_after_1,
                                step2_axis,
                                step2_angle
                            )

                            out("")
                            out("STEP 1 CHECK: PASS")
                            out("")
                            out("------------------------------------------------------------")
                            out("AUTO-FIX STEP 2")
                            out("------------------------------------------------------------")
                            out(
                                "World %s rotation = %s deg"
                                % (step2_axis, fmt_angle(step2_angle))
                            )

                            step2_command_ok = True

                            try:
                                result2 = apply_move_rotation(
                                    target_selection,
                                    anchor_point,
                                    step2_axis,
                                    step2_angle
                                )
                                out("Move.Rotate result type:")
                                out("  %s" % type_name(result2))
                            except Exception as ex:
                                step2_command_ok = False
                                out("STEP 2 Move.Rotate EXCEPTION:")
                                out("  %s" % str(ex))

                            if not step2_command_ok:
                                act("AUTO-FIX CHECK FAILED.")
                                act("")
                                act("Step 1 passed verification but Step 2")
                                act("could not be completed.")
                                act(
                                    "Move.Rotate operations issued: %d"
                                    % _moves_issued
                                )
                                act("")
                                act("DO NOT SAVE yet.")
                                act("Review/Undo the issued move(s) and")
                                act("send the full diagnostic log.")

                            else:
                                final_check_ok = True

                                try:
                                    final_surface, final_normal_obj, final_local_n, \
                                        final_n, final_method, final_matrix = \
                                        reacquire_face_state(
                                            face,
                                            "FINAL POST-CHECK"
                                        )

                                    final_axis, final_dev, residual_steps, residual_pred = \
                                        correction(final_n)

                                    final_prediction_difference = \
                                        plane_normal_difference_deg(
                                            predicted_after_2,
                                            final_n
                                        )

                                    out("")
                                    out("------------------------------------------------------------")
                                    out("FINAL FRESH POST-CHANGE CHECK")
                                    out("------------------------------------------------------------")
                                    print_normal(
                                        "Final refreshed LOCAL face normal:",
                                        final_local_n
                                    )
                                    out("")
                                    print_normal(
                                        "Final refreshed measured face normal:",
                                        final_n
                                    )
                                    out("")
                                    out("Final nearest World axis:")
                                    out("  World %s" % final_axis)
                                    out("Final deviation:")
                                    out(
                                        "  %.*f deg"
                                        % (ANGLE_DP, final_dev)
                                    )
                                    out("Final predicted-vs-measured difference:")
                                    out(
                                        "  %.*f deg"
                                        % (
                                            ANGLE_DP,
                                            final_prediction_difference
                                        )
                                    )

                                    if (
                                        final_axis != axis_name or
                                        final_dev > ALIGN_TOL_DEG or
                                        final_prediction_difference > STEP_VERIFY_TOL_DEG
                                    ):
                                        final_check_ok = False

                                except Exception as ex:
                                    final_check_ok = False
                                    out("")
                                    out("FINAL FRESH POST-CHECK EXCEPTION:")
                                    out("  %s" % str(ex))

                                if final_check_ok:
                                    out("")
                                    out("STATUS: AUTO-FIX VERIFIED - ALIGNED")

                                    act("AUTO-FIX VERIFIED - ALIGNED")
                                    act("")
                                    act(
                                        "The tool applied %d Move.Rotate operations."
                                        % _moves_issued
                                    )
                                    act("Final World axis: %s" % final_axis)
                                    act(
                                        "Final deviation: %.*f deg"
                                        % (ANGLE_DP, final_dev)
                                    )
                                    act("")
                                    act("FRESH POST-CHANGE CHECK: PASS")
                                    act("")
                                    act("NEXT:")
                                    act("1) Save the SpaceClaim document.")
                                    act("2) Test/create the drawing.")
                                    act("")
                                    act("No manual rotation is required.")

                                else:
                                    out("")
                                    out("STATUS: AUTO-FIX CHECK FAILED")

                                    act("AUTO-FIX CHECK FAILED.")
                                    act("")
                                    act(
                                        "The tool issued %d Move.Rotate operations,"
                                        % _moves_issued
                                    )
                                    act("but the FINAL fresh post-change check")
                                    act("did not reach the verified aligned state.")
                                    act("")
                                    act("THE TOOL WILL NOT APPLY ANOTHER CORRECTION.")
                                    act("")
                                    act("DO NOT SAVE yet.")
                                    act("Do not rerun the tool repeatedly.")
                                    act("Review/Undo the issued move(s) and")
                                    act("send the full diagnostic log.")


finish_outputs()
