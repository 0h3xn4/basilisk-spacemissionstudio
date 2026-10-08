#
#  ISC License
#
#  Copyright (c) 2026, Autonomous Vehicle Systems Lab, University of Colorado at Boulder
#
#  Permission to use, copy, modify, and/or distribute this software for any
#  purpose with or without fee is hereby granted, provided that the above
#  copyright notice and this permission notice appear in all copies.
#
#  THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
#  WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
#  MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
#  ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
#  WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
#  ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
#  OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
#
"""Mid-step planet orientation for the gravity model (ECSS-Q-ST-80C
7.1.7a numerical accuracy; Phase 3 finding V-04, see
``compliance/validation/README.md``).

**Problem.** Basilisk 2.12's ``GravBodyData::computeGravityInertial``
(``gravityEffector.cpp``) takes the planet orientation from the SPICE
message written at the end of each dynamics task step and extrapolates it
linearly inside the step, ``dcm_PfixN + dcm_PfixN_dot * dt``. A linear
extrapolation of a rotation matrix is not a rotation: it stretches
equatorial vectors by about ``(omega dt)^2 / 2``, and every gravity
evaluation passes through it, point mass included. At the 10 s default
step this acts like a relative GM error of about 1e-7: 148 m along-track
after one day in a 400 km two-body orbit, against Kepler's solution.

**Workaround** (no change to Basilisk; public messaging API only). The
gravity body reads its own copy of the SPICE planet message, in which the
orientation is the one at the middle of the step being integrated
(Basilisk integrates from ``t - h`` to ``t`` with the message written at
``t``, so the middle is ``t - h/2``), re-orthonormalised, and the rate is
zero, so Basilisk uses that one rotation for the whole step. The
remaining error is the orientation's deviation from the mid-step value,
of order ``omega h / 2`` for the tesseral terms only. One-day results: two-body at
10 s within 1 mm of Kepler; degree 10 at 10 s within 2 cm of a 0.25 s
reference (66 m without the workaround).

Ground stations, the atmosphere and attitude guidance keep reading the
unmodified SPICE message.
"""

from __future__ import annotations

import numpy as np
from Basilisk.architecture import messaging, sysModel

#: Task priority: after the SPICE interface (500), before the spacecraft.
PRIORITY = 450


def _nearest_rotation(matrix: np.ndarray) -> np.ndarray:
    """Orthonormalise a nearly orthonormal matrix (one Newton step of the
    polar decomposition, exact to the square of its deviation)."""
    return 1.5 * matrix - 0.5 * matrix @ matrix.T @ matrix


class MidStepPlanetOrientation(sysModel.SysModel):
    """Copies a ``SpicePlanetStateMsg`` with ``J20002Pfix`` moved to the
    middle of the integration step and ``J20002Pfix_dot`` set to zero."""

    def __init__(self, name: str, step_s: float):
        super().__init__()
        self.ModelTag = name
        self.planetInMsg = messaging.SpicePlanetStateMsgReader()
        self.planetOutMsg = messaging.SpicePlanetStateMsg()
        self.shift_s = -0.5 * step_s  # [s] middle of the step that ends at the message time

    def Reset(self, CurrentSimNanos):
        if self.planetInMsg.isWritten():
            self.UpdateState(CurrentSimNanos)

    def UpdateState(self, CurrentSimNanos):
        # The reader returns a view of the SPICE message: copy, never modify it.
        source = self.planetInMsg()
        payload = messaging.SpicePlanetStateMsgPayload()
        for name in ("J2000Current", "PlanetName", "PositionVector", "VelocityVector", "computeOrient"):
            setattr(payload, name, getattr(source, name))
        dcm = np.array(source.J20002Pfix)
        dcm_dot = np.array(source.J20002Pfix_dot)
        if dcm_dot.any():
            dcm = _nearest_rotation(dcm + dcm_dot * self.shift_s)
        payload.J20002Pfix = dcm.tolist()
        payload.J20002Pfix_dot = np.zeros((3, 3)).tolist()
        self.planetOutMsg.write(payload, CurrentSimNanos, self.moduleID)


def attach(sim, task_name: str, spice_object, grav_bodies: dict, body_names, step_s: float) -> list:
    """Insert one :class:`MidStepPlanetOrientation` per gravity body and
    subscribe the body to it. Returns the modules (kept alive by the caller)."""
    modules = []
    for index, name in enumerate(body_names):
        if name not in grav_bodies:
            continue
        module = MidStepPlanetOrientation(f"midStepOrientation_{name}", step_s)
        module.planetInMsg.subscribeTo(spice_object.planetStateOutMsgs[index])
        sim.AddModelToTask(task_name, module, PRIORITY)
        grav_bodies[name].planetBodyInMsg.subscribeTo(module.planetOutMsg)
        modules.append(module)
    return modules
