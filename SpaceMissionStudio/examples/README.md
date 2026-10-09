# Python examples

Short scripts that use SpaceMissionStudio from Python, without the GUI.
Each shows one part of the tool and prints what it found. Every script
is run by `tests/test_examples.py`, so they keep working.

Run them from the `SpaceMissionStudio` folder, with the environment you
installed SpaceMissionStudio into active (see
[`GETTING_STARTED.md`](../GETTING_STARTED.md)). Each one takes `--help`.

| Script | Shows | Needs Basilisk | Takes about |
|---|---|---|---|
| [`build_a_scenario.py`](build_a_scenario.py) | Building a scenario from the schema's dataclasses: an orbit, a spacecraft, a ground station. It validates the scenario, saves it as JSON for the GUI or CLI, and prints the Explain tab's summary. | no | 1 s |
| [`run_a_template.py`](run_a_template.py) | Running any bundled template (or your own file) and reading its results: time series, events (passes, eclipses), CSV export. | yes | 5 s |
| [`hohmann_transfer.py`](hohmann_transfer.py) | A Mission Sequence in code: burn, coast until apoapsis, burn again. The result is checked against the textbook Hohmann transfer. | yes | 5 s |
| [`altitude_lifetime_sweep.py`](altitude_lifetime_sweep.py) | A parameter sweep: orbital lifetime at several altitudes, with real solar activity, checked against the 5-year disposal rule. | yes | 35 s |
| [`monte_carlo_spread.py`](monte_carlo_spread.py) | Running template 25's Monte Carlo batch and reading the archive back, which the GUI does not plot. | yes | 1 min |

```bash
python3 examples/build_a_scenario.py my_first_mission.json
spacemissionstudio run my_first_mission.json --out-dir out    # or open it in the GUI
python3 examples/run_a_template.py 23
python3 examples/hohmann_transfer.py --from-km 550 --to-km 700
python3 examples/altitude_lifetime_sweep.py --altitudes 400,450,500,550
python3 examples/monte_carlo_spread.py --runs 20 --archive mc_out
```

## Where things live

All five use the same few entry points:

| You want to | Use |
|---|---|
| Describe a mission | `spacemissionstudio.schema.scenario`: `Scenario`, `SpacecraftConfig`, `OrbitIC`, `GroundStationConfig` and friends. |
| Read or write a scenario file | `spacemissionstudio.schema.load_scenario(path)`, `Scenario.save(path)`, `Scenario.validate()` |
| Plan an orbit | `spacemissionstudio.engine.orbit_design`: Sun-synchronous inclination, RAAN for a local time, GEO elements |
| Run it | `spacemissionstudio.engine.service.SimulationService(scenario).run()`. With a Mission Sequence: `engine.mission_engine.MissionEngine(scenario, service=...).run()` |
| Read results | `ResultSet.series[name]`, a `TimeSeries` with `time_s`, `data`, `columns`, `units`; `ResultSet.export_csv(folder)` |
| List events | `spacemissionstudio.engine.events.extract_events(result)` |
| Summarize a scenario | `spacemissionstudio.engine.scenario_explainer.explain(scenario)` (the Explain tab) |
| Estimate lifetime | `spacemissionstudio.engine.lifetime.spacecraft_lifetime(scenario, name)` (the End of Life tab) |
| Monte Carlo | `spacemissionstudio.engine.monte_carlo.run_monte_carlo(scenario, scenario.monte_carlo, folder)` |

Series names follow `<spacecraft>.<quantity>` (`my-sat.position_N`) or
`<station>.access_to_<spacecraft>.<quantity>`; the Results tab's
**Series** list shows the same names. Positions are in metres, in the
inertial frame (`_N`), and times are seconds since the scenario's epoch.
