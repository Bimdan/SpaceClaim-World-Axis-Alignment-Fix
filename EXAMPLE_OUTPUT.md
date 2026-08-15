# Sanitized example output

The following is a shortened, sanitized example from a successful two-axis correction.

```text
SPACECLAIM WORLD-AXIS ALIGNMENT FIX v1.0

PRE-CHECK LOCAL ACIS face normal:
  X = -0.000015194000
  Y =  0.000025243000
  Z =  0.999999999566

PRE-CHECK FACE-TO-MASTER normal:
  X = -0.000015194000
  Y =  0.000025243000
  Z =  0.999999999566

Nearest World axis:
  World Z

PRE-CHECK deviation:
  0.001688104 deg

Calculated automatic correction:
  Step 1: World X +0.001446317 deg
  Step 2: World Y +0.000870552 deg

AUTO-FIX STEP 1
World X rotation = +0.001446317 deg

Refreshed LOCAL normal after Step 1:
  X = -0.000015194000
  Y =  0.000000000000
  Z =  0.999999999885

Step 1 predicted-vs-measured difference:
  0.000000000 deg

STEP 1 CHECK: PASS

AUTO-FIX STEP 2
World Y rotation = +0.000870552 deg

FINAL FRESH POST-CHANGE CHECK
Final refreshed LOCAL face normal:
  X = 0.000000000000
  Y = 0.000000000000
  Z = 1.000000000000

Final nearest World axis:
  World Z

Final deviation:
  0.000000000 deg

STATUS: AUTO-FIX VERIFIED - ALIGNED
```

The correction values are only an example. The script calculates the actual values from the selected face each time.
