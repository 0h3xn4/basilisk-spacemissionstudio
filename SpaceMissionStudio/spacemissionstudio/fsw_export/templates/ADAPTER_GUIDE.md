# Running your own flight software in the loop

The adapter puts flight software of your own, written in C or callable
from C, behind the same ports as this export. SpaceMissionStudio can then
fly it against the Basilisk dynamics and compare it, step by step, with
the Basilisk modules the export came from. The protocol is in
`SIL_CONTRACT.md`. You do not need to read it to use the adapter.

## What you get

| File | |
|---|---|
| `adapter/fsw_adapter.c` | **The file you edit**: `fsw_init`, `fsw_reset`, `fsw_step`, your name and step |
| `adapter/fsw_adapter.h` | Generated: the input, output and telemetry payload structs and their written flags, and the configuration constants the exported modules use (`fsw_adapter_constant_*`) |
| `adapter/fsw_adapter_ports.c` | Generated: the port tables (names, types, sizes, layout hashes) and the glue between the structs and the SIL harness |
| `host/fsw_host.c`, `generated/fsw_sil.c` | The same harness the export uses, built as `fsw_adapter_host` |

The payload types are Basilisk's own (`basilisk/architecture/msgPayloadDefC/`).
The layout check that the simulation runs before the first step makes
sure their binary layout is the one the simulation uses.

## Steps

1. **Call your code** from `adapter/fsw_adapter.c`:
   - `fsw_init()` once, when the run starts: initialise.
   - `fsw_reset(t)` once, after the simulation's own reset:
     `fsw_adapter_inputs` then holds the inputs written at reset (see
     `fsw_adapter_inputs_written`).
   - `fsw_step(t)` once per step: read `fsw_adapter_inputs`, run one step,
     then set every command in `fsw_adapter_outputs` and its flag in
     `fsw_adapter_outputs_written` to 1. Telemetry is optional; what you
     set there is compared too.

   Keep `fsw_rate_ns` at the step your software runs at. The simulation
   refuses a different one.
2. **Add your sources** to the `fsw_adapter` library in `CMakeLists.txt`
   (`add_library(fsw_adapter STATIC ...)`), or link your own library into
   it with `target_link_libraries(fsw_adapter PUBLIC <yours>)`.
3. **Build**:

   ```sh
   cmake -S . -B build
   cmake --build build
   ctest --test-dir build           # includes adapter_ports: the adapter starts and lists its ports
   ```

4. **Check it offline** against the recorded Basilisk run:

   ```sh
   ./build/fsw_adapter_host replay tests/data/replay_inputs.trace /tmp/out.trace \
       --expect tests/data/replay_expected.trace --rtol 1e-6 --atol 1e-9
   ```

   It prints the largest difference per output and telemetry port.
5. **Run it in the loop**: in SpaceMissionStudio, Flight Software tab,
   choose **Run SIL...** on the spacecraft and pick
   `build/fsw_adapter_host` (`build\Release\fsw_adapter_host.exe` on
   Windows). From the command line:

   ```sh
   spacemissionstudio sil scenario.json --spacecraft <name> --binary build/fsw_adapter_host
   ```

   The comparison panel then shows each signal's residual against the
   Basilisk modules, the round-trip and execution times, and any dropped
   steps.

## As generated

The template builds and runs, but sets no command. In the loop the
actuators then stay at zero, and the comparison lists the outputs as not
provided. That shows the link works before any of your code is in.

## Another language or another link

Any program that follows `SIL_CONTRACT.md` can be run in the loop: it
does not have to be built from this folder. To use a serial line or a UDP
link instead of the socket, replace `generated/fsw_transport_socket.c`
with your own implementation of `generated/fsw_transport.h`. The protocol
code does not change.
