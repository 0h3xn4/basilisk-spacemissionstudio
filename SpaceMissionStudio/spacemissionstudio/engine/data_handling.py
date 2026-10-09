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

r"""
Onboard data generation, storage and downlink for one spacecraft
(``schema.scenario.DataHandlingConfig``).

The chain is Basilisk's own, wired as ``examples/scenarioGroundDownlink.py``
wires it:

* one ``simpleInstrument`` per instrument, at its constant data rate;
* one ``partitionedStorageUnit``, a partition per instrument, holding at
  most ``storage_capacity_gbit``; a step of an instrument's data that
  would not fit is refused whole, so a full memory loses data;
* one ``spaceToGroundTransmitter`` at ``rf_link.data_rate_bps``, which
  empties the fullest partition while any of its access messages says
  there is access, in 1 Mbit packets (the example's size).

Two Python modules of this tool sit around it:

* :class:`_DownlinkGate` re-publishes each ground station's real
  ``groundLocation`` access message to the transmitter, with ``hasAccess``
  cleared unless the link closes: the Eb/N0 margin
  (``engine.link_budget``) for the real slant range and the antenna's gain
  toward the station must be at least 0 dB. That gain comes from the
  simulated attitude: the angle between ``rf_link.antenna_boresight_b``
  and the line of sight to the station, through ``rf_link.antenna_pattern``
  (a patch antenna's cos^n, or a datasheet table). Basilisk's own antenna
  model (``simpleAntenna``) is not used: it refuses directivities below
  9 dB, so it cannot represent the patch antennas most small satellites
  fly.
* :class:`_DataLedger` follows the storage unit step by step and counts
  what was generated, refused (lost) and downlinked, repeating the storage
  unit's own rule: instrument data is added in the order the instruments
  were attached, each step's amount ``round(rate * dt)`` only if it fits,
  then the transmitter removes data, never below zero. It also switches
  the transmitter's power draw.

All of them run at the task's default priority, so in the order they are
added -- after the spacecraft and ground stations, which are added first:
gate, instruments, transmitter, storage, ledger. The gate thus sees this
step's access, and the transmitter reads the storage status of the
previous step, as in the Basilisk example. The power sinks run before the
battery (engine.service), so the transmitter's draw the ledger sets takes
effect one step later.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
from Basilisk.architecture import messaging, sysModel
from Basilisk.simulation import partitionedStorageUnit, simpleInstrument, simplePowerSink, spaceToGroundTransmitter
from Basilisk.utilities import RigidBodyKinematics as rbk
from Basilisk.utilities import macros

from ..schema.scenario import DataHandlingConfig, GroundStationConfig, RFLinkConfig
from . import link_budget
from .orbit_maintenance import LogThinner

BITS_PER_GBIT = 1.0e9  # [bit/Gbit]
PACKET_SIZE_BITS = 1.0e6  # [bit] scenarioGroundDownlink.py's packet size

# Higher runs first within a task (Basilisk): engine.service's power sinks
# run at 50, before the battery at 40.
_PRIORITY_SINKS = 50


def antenna_boresight_b(sc_config) -> Optional[np.ndarray]:
    """The downlink antenna's body-frame boresight (unit vector), from
    ``rf_link`` or else ``comms_pointing``; None if neither gives one."""
    vector = None
    if sc_config.rf_link is not None and sc_config.rf_link.antenna_boresight_b is not None:
        vector = sc_config.rf_link.antenna_boresight_b
    elif sc_config.comms_pointing is not None:
        vector = sc_config.comms_pointing.antenna_boresight_b
    if vector is None:
        return None
    vector = np.asarray(vector, dtype=float)
    return vector / np.linalg.norm(vector)


class _DownlinkGate(sysModel.SysModel):
    """One spacecraft's link to every ground station; see the module docstring."""

    def __init__(self, rf_link: RFLinkConfig, stations: List[GroundStationConfig],
                 boresight_b: Optional[np.ndarray], record_interval_s: float):
        super().__init__()
        self.rfLink = rf_link
        self.stations = stations
        self.boresightB = boresight_b  # None: perfect pointing assumed, as engine.link_budget always did
        self.scStateInMsg = messaging.SCStatesMsgReader()
        self.accessInMsgs = [messaging.AccessMsgReader() for _ in stations]
        self.groundStateInMsgs = [messaging.GroundStateMsgReader() for _ in stations]
        self.accessOutMsgs = [messaging.AccessMsg() for _ in stations]
        self.marginAtOneMetreDb = [link_budget.margin_at_one_metre_db(rf_link, station)
                                   for station in stations]  # [dB]
        self.logThinner = LogThinner(record_interval_s)
        self.tLog: list = []
        self.marginDbLog: List[list] = [[] for _ in stations]  # [dB] NaN outside access
        self.offBoresightDegLog: List[list] = [[] for _ in stations]  # [deg] NaN outside access
        self.linkClosedLog: List[list] = [[] for _ in stations]  # 1 while the link closes

    def off_boresight_deg(self, sc_state, ground_state) -> float:
        if self.boresightB is None:
            return 0.0
        line_of_sight_n = np.asarray(ground_state.r_LN_N) - np.asarray(sc_state.r_BN_N)  # [m]
        dcm_bn = np.asarray(rbk.MRP2C(np.asarray(sc_state.sigma_BN)))
        line_of_sight_b = dcm_bn @ line_of_sight_n
        cos_angle = float(self.boresightB @ line_of_sight_b) / float(np.linalg.norm(line_of_sight_b))
        return float(np.degrees(np.arccos(np.clip(cos_angle, -1.0, 1.0))))

    def UpdateState(self, CurrentSimNanos):
        # Runs every step: the attitude and the link budget are only
        # evaluated in access (both are logged as NaN outside it).
        t = CurrentSimNanos * macros.NANO2SEC  # [s]
        due = self.logThinner.due(t)
        if due:
            self.tLog.append(t)
        sc_state = None
        for index in range(len(self.stations)):
            access = self.accessInMsgs[index]()
            angle_deg = float("nan")
            margin_db = float("nan")
            closed = False
            if access.hasAccess:
                if sc_state is None:
                    sc_state = self.scStateInMsg()
                angle_deg = self.off_boresight_deg(sc_state, self.groundStateInMsgs[index]())
                margin_db = (self.marginAtOneMetreDb[index] - 20.0 * math.log10(float(access.slantRange))
                             - link_budget.pointing_loss_db(self.rfLink, angle_deg))  # [dB]
                closed = margin_db >= 0.0
            out = messaging.AccessMsgPayload()
            out.hasAccess = 1 if closed else 0
            out.slantRange = access.slantRange
            out.elevation = access.elevation
            out.azimuth = access.azimuth
            self.accessOutMsgs[index].write(out, CurrentSimNanos, self.moduleID)
            if due:
                self.marginDbLog[index].append(margin_db)
                self.offBoresightDegLog[index].append(angle_deg)
                self.linkClosedLog[index].append(1.0 if closed else 0.0)


class _DataLedger(sysModel.SysModel):
    """Generated, lost and downlinked bits of one storage unit; see the module docstring."""

    def __init__(self, config: DataHandlingConfig, capacity_bits: int, initial_bits: int,
                 transmitter_sink, transmitter_power_w: float, record_interval_s: float):
        super().__init__()
        self.rates = [instrument.data_rate_bps for instrument in config.instruments]  # [bit/s]
        self.capacityBits = capacity_bits  # [bit]
        self.storageInMsg = messaging.DataStorageStatusMsgReader()
        self.transmitterInMsg = messaging.DataNodeUsageMsgReader()
        self.transmitterSink = transmitter_sink
        self.transmitterPowerW = transmitter_power_w  # [W]
        self.previousT: Optional[float] = None  # [s]
        self.previousLevel = float(initial_bits)  # [bit]
        self.generated = 0.0  # [bit] everything the instruments produced
        self.lost = 0.0  # [bit] refused by a full memory
        self.downlinked = 0.0  # [bit]
        self.logThinner = LogThinner(record_interval_s)
        self.tLog: list = []
        self.downlinkRateLog: list = []  # [bit/s] over the last step
        self.downlinkedLog: list = []  # [bit] cumulative
        self.lostLog: list = []  # [bit] cumulative
        self.generatedLog: list = []  # [bit] cumulative

    def Reset(self, CurrentSimNanos):
        if self.transmitterSink is not None:
            self.transmitterSink.nodePowerOut = 0.0

    def UpdateState(self, CurrentSimNanos):
        t = CurrentSimNanos * macros.NANO2SEC  # [s]
        level = float(self.storageInMsg().storageLevel)  # [bit]
        downlink_rate = 0.0  # [bit/s]
        if self.previousT is not None and t > self.previousT:
            dt = t - self.previousT  # [s]
            total = self.previousLevel  # [bit]
            for rate in self.rates:
                delta = float(np.round(rate * dt))  # [bit] DataStorageUnitBase::computeDataDelta
                self.generated += delta
                if total + delta <= self.capacityBits:
                    total += delta
                else:
                    self.lost += delta
            removed = max(0.0, total - level)  # [bit]
            self.downlinked += removed
            downlink_rate = removed / dt
        self.previousT = t
        self.previousLevel = level
        if self.transmitterSink is not None:  # only built together with a transmitter
            transmitting = float(self.transmitterInMsg().baudRate) < 0.0
            self.transmitterSink.nodePowerOut = -self.transmitterPowerW if transmitting else 0.0
        if self.logThinner.due(t):
            self.tLog.append(t)
            self.downlinkRateLog.append(downlink_rate)
            self.downlinkedLog.append(self.downlinked)
            self.lostLog.append(self.lost)
            self.generatedLog.append(self.generated)


@dataclass
class DataHandlingHandle:
    """What :func:`build_data_handling` built, for recording and for
    carrying the memory's contents into the next segment of a long run."""

    storage: Optional[object] = None
    storage_recorder: Optional[object] = None
    instrument_names: List[str] = field(default_factory=list)
    ledger: Optional[_DataLedger] = None
    gate: Optional[_DownlinkGate] = None
    station_names: List[str] = field(default_factory=list)
    keep_alive: list = field(default_factory=list)  # Basilisk objects Python must not free


def build_link_gate(scSim, task_name: str, tag: str, sc_config, sc_object, stations: List[GroundStationConfig],
                    access_out_msgs: Dict[str, object], ground_state_msgs: Dict[str, object],
                    record_interval_s: float) -> _DownlinkGate:
    """The live link gate of one spacecraft (see ``engine.link_budget.needs_link_gate``)."""
    gate = _DownlinkGate(sc_config.rf_link, stations, antenna_boresight_b(sc_config), record_interval_s)
    gate.ModelTag = f"{tag}DownlinkGate"
    gate.scStateInMsg.subscribeTo(sc_object.scStateOutMsg)
    for index, station in enumerate(stations):
        gate.accessInMsgs[index].subscribeTo(access_out_msgs[station.name])
        gate.groundStateInMsgs[index].subscribeTo(ground_state_msgs[station.name])
    scSim.AddModelToTask(task_name, gate)
    return gate


def build_data_handling(scSim, task_name: str, tag: str, config: DataHandlingConfig,
                        gate: Optional[_DownlinkGate], downlink_rate_bps: float, battery,
                        record, record_interval_s: float) -> DataHandlingHandle:
    """Builds one spacecraft's instruments, storage and (with ``gate``)
    transmitter. ``battery`` (or None) receives the instruments' and the
    transmitter's power sinks; ``record(msg)`` makes a recorder."""
    handle = DataHandlingHandle(instrument_names=[i.name for i in config.instruments])
    capacity_bits = int(round(config.storage_capacity_gbit * BITS_PER_GBIT))  # [bit]

    storage = partitionedStorageUnit.PartitionedStorageUnit()
    storage.ModelTag = f"{tag}DataStorage"
    storage.storageCapacity = capacity_bits
    for instrument in config.instruments:
        node = simpleInstrument.SimpleInstrument()
        node.ModelTag = f"{tag}Instrument_{instrument.name}"
        node.nodeBaudRate = instrument.data_rate_bps  # [bit/s]
        node.nodeDataName = instrument.name
        scSim.AddModelToTask(task_name, node)
        storage.addDataNodeToModel(node.nodeDataOutMsg)
        handle.keep_alive.append(node)

    transmitter = None
    if gate is not None:
        transmitter = spaceToGroundTransmitter.SpaceToGroundTransmitter()
        transmitter.ModelTag = f"{tag}Transmitter"
        transmitter.nodeBaudRate = -downlink_rate_bps  # [bit/s] negative: removes data
        transmitter.packetSize = -PACKET_SIZE_BITS  # [bit]
        transmitter.numBuffers = len(config.instruments)
        for access_msg in gate.accessOutMsgs:
            transmitter.addAccessMsgToTransmitter(access_msg)
        scSim.AddModelToTask(task_name, transmitter)
        storage.addDataNodeToModel(transmitter.nodeDataOutMsg)  # last: removal follows the instruments' additions
        handle.keep_alive.append(transmitter)

    for instrument in config.instruments:
        storage.addPartition(instrument.name)
    initial = [int(round(i.initial_data_gbit * BITS_PER_GBIT)) for i in config.instruments]  # [bit]
    if any(initial):
        storage.setDataBuffer([i.name for i in config.instruments], initial)
    scSim.AddModelToTask(task_name, storage)
    if transmitter is not None:
        transmitter.addStorageUnitToTransmitter(storage.storageUnitDataOutMsg)

    transmitter_sink = None
    if battery is not None:
        instruments_w = sum(i.power_w for i in config.instruments)  # [W]
        if instruments_w > 0:
            sink = simplePowerSink.SimplePowerSink()
            sink.ModelTag = f"{tag}InstrumentsPowerSink"
            sink.nodePowerOut = -instruments_w  # [W] constant
            scSim.AddModelToTask(task_name, sink, _PRIORITY_SINKS)
            battery.addPowerNodeToModel(sink.nodePowerOutMsg)
            handle.keep_alive.append(sink)
        if transmitter is not None and config.transmitter_power_w > 0:
            transmitter_sink = simplePowerSink.SimplePowerSink()
            transmitter_sink.ModelTag = f"{tag}TransmitterPowerSink"
            transmitter_sink.nodePowerOut = 0.0  # [W] the ledger switches it while transmitting
            scSim.AddModelToTask(task_name, transmitter_sink, _PRIORITY_SINKS)
            battery.addPowerNodeToModel(transmitter_sink.nodePowerOutMsg)
            handle.keep_alive.append(transmitter_sink)

    ledger = _DataLedger(config, capacity_bits, sum(initial), transmitter_sink, config.transmitter_power_w,
                         record_interval_s)
    ledger.ModelTag = f"{tag}DataLedger"
    ledger.storageInMsg.subscribeTo(storage.storageUnitDataOutMsg)
    if transmitter is not None:
        ledger.transmitterInMsg.subscribeTo(transmitter.nodeDataOutMsg)
    scSim.AddModelToTask(task_name, ledger)

    handle.storage = storage
    handle.ledger = ledger
    handle.gate = gate
    handle.storage_recorder = record(storage.storageUnitDataOutMsg)
    scSim.AddModelToTask(task_name, handle.storage_recorder)
    return handle


def stored_bits_by_instrument(storage, names: List[str]) -> Dict[str, int]:
    """What each instrument's partition holds now [bit], for carrying a
    long run's memory into its next segment."""
    status = storage.storageUnitDataOutMsg.read()
    stored = dict(zip(list(status.storedDataName), list(status.storedData)))
    return {name: int(stored.get(name, 0)) for name in names}
