# Getting started with SpaceMissionStudio

From nothing to your first simulated orbit: install, check, run. No
programming needed for the installers. The from-source path (C) needs
only a terminal and copy-and-paste.

**Contents**

1. [What you need](#1-what-you-need)
2. [Pick an install path](#2-pick-an-install-path)
3. [Path A: the installer](#3-path-a-the-installer)
4. [Path B: the install script](#4-path-b-the-install-script)
5. [Path C: from source, step by step](#5-path-c-from-source-step-by-step)
6. [Check that it works](#6-check-that-it-works)
7. [Your first run](#7-your-first-run)
8. [Where things are kept](#8-where-things-are-kept)
9. [If something goes wrong](#9-if-something-goes-wrong)
10. [Where to go next](#10-where-to-go-next)

## 1. What you need

| | |
|---|---|
| Operating system | Linux (x86_64 or aarch64, glibc 2.24 or newer, e.g. Ubuntu 18.04+) or Windows 10/11 (x86_64). macOS is not supported by the installers; path C may work there, unverified. |
| Python | 3.9 or newer (paths B and C; the installers set up their own). |
| Disk | About 1 GB: the simulation engine (Basilisk), the GUI toolkit and about 116 MB of reference data. |
| Internet | Once, during installation. After that the app runs offline and never downloads anything without asking. |

Two pieces make up the app:

* **SpaceMissionStudio** -- the windows, forms, plots and scenario files.
* **Basilisk** -- the simulation engine from the University of Colorado's
  AVS Lab that computes every number. The app opens without it (you can
  build and save scenarios), but **Run** needs it.

## 2. Pick an install path

| Path | For | You type |
|---|---|---|
| **A. Installer** (`.deb` on Linux, `-setup.exe` on Windows) | Using the app | Nothing: double-click |
| **B. Install script** (`packaging/install.sh` or `install.ps1`) | Using the app from a checkout of this repository | One command |
| **C. From source** with `pip` | Developing, scripting from Python, running the tests | About six commands |

All three install the same Basilisk version, 2.12.0, the one this app is
verified against (path C asks you to pin it yourself).

## 3. Path A: the installer

You need the installer file. Build it yourself with
`packaging/build_deb.sh` (Linux) or `packaging/windows/spacemissionstudio.iss`
with [Inno Setup](https://jrsoftware.org/isinfo.php) (Windows), or get
it from whoever distributes the app to you.

**Linux:** double-click `spacemissionstudio_2.0.0_all.deb`, or in a terminal:

```bash
sudo apt install ./spacemissionstudio_2.0.0_all.deb
```

**Windows:** double-click `spacemissionstudio-2.0.0-setup.exe` and follow
the wizard.

The installer downloads Basilisk and the reference data (SPICE kernels
with planet positions and leap seconds, the gravity field, the magnetic
field model) once. Then open **SpaceMissionStudio** from your
application menu or Start Menu and go to [section 6](#6-check-that-it-works).

The Linux package was built and installed in this project's own Linux
environment. The Windows installer has not yet been run on a real
Windows machine; please report anything that goes wrong. Details:
[`packaging/README.md`](packaging/README.md).

## 4. Path B: the install script

From the `SpaceMissionStudio` folder of this repository:

Linux:

```bash
packaging/install.sh --basilisk-wheel "bsk[all]==2.12.0"
```

Windows (PowerShell):

```powershell
packaging\install.ps1 -BasiliskWheel "bsk[all]==2.12.0"
```

Either creates a private Python environment, installs both pieces and
the reference data into it, and adds a launcher (a desktop entry on
Linux, a Start Menu shortcut on Windows). The Linux script has been run
end to end; the Windows script has not yet been run on a real Windows
machine.

## 5. Path C: from source, step by step

**1. Get the code.** Clone this repository (or download it as a ZIP and
unpack it), then open a terminal in its `SpaceMissionStudio` folder:

```bash
git clone https://github.com/0h3xn4/basilisk-spacemissionstudio.git
cd basilisk-spacemissionstudio/SpaceMissionStudio
```

**2. Create a private Python environment**, so nothing touches your
system Python:

Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows (PowerShell):

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

Your prompt now starts with `(.venv)`. Run the activate line again in
every new terminal before using the app. (Windows refusing to run
`Activate.ps1`? See [section 9](#9-if-something-goes-wrong).)

**3. Install Basilisk**, the verified version, as a prebuilt wheel (no
compiler needed):

```bash
pip install "bsk[all]==2.12.0"
```

**4. Install SpaceMissionStudio** with its GUI:

```bash
pip install -e ".[gui]"
```

Add `dev` (`".[dev,gui]"`) if you also want to run the tests.

**5. Fetch the reference data** (once, about 116 MB):

```bash
spacemissionstudio kernels-status
spacemissionstudio earth-orientation --fetch
```

The first downloads the SPICE kernels, gravity field and magnetic model
into Basilisk's cache and lists each file as `OK`. The second fetches
the measured Earth orientation files (without them, runs use a simpler
Earth rotation model and say so).

## 6. Check that it works

```bash
spacemissionstudio validate spacemissionstudio/scenarios/templates/22_starter_first_leo_satellite.json
spacemissionstudio kernels-status
```

The first prints `OK: '22 - Starter: your first LEO satellite' -- 1
spacecraft, ...` (no Basilisk needed). The second lists every reference
file as `OK`.

In the GUI (installed apps: from the menu; from source: `spacemissionstudio gui`):

* The status bar at the bottom shows the Basilisk version. "Basilisk
  version not qualified" means a version other than 2.12.0 is installed:
  runs still work, but results are outside what the app was verified
  against.
* **Run > Check Reference Data** opens the **Data** tab, which lists every
  reference file and offers to download anything missing (it asks first).
* **Help > About SpaceMissionStudio** shows the app's version.

## 7. Your first run

**In the GUI** -- about a minute:

1. The app opens on **Load Scenario**. Click **22 - Starter: your first
   LEO satellite**; its description appears below the list.
2. Click **Open Template**. The **Scenario Editor** shows the mission.
   The **Explain** tab on the right summarizes what it switches on.
3. **Run > Run Simulation** (`Ctrl+R`). A one-day run takes a few seconds.
4. The **Results** tab opens. Pick `my-sat.position_N` from **Series** to
   see the orbit; the **Events** tab lists the Berlin passes and eclipses.
5. **File > Save As...** to keep your own copy before you change anything.

**From the command line:**

```bash
spacemissionstudio run spacemissionstudio/scenarios/templates/22_starter_first_leo_satellite.json --out-dir out
```

`out/` then holds one CSV per result series, `events.csv` and
`provenance.json` (which Basilisk version, reference files and scenario
produced the numbers).

**From Python:** see [`examples/`](examples/README.md), starting with
`python3 examples/build_a_scenario.py` (no Basilisk needed) and
`python3 examples/run_a_template.py 22`.

## 8. Where things are kept

| What | Where |
|---|---|
| Your scenarios | Wherever you save them: plain `.json` files you can copy, mail or keep in version control. |
| Bundled templates | `spacemissionstudio/scenarios/templates/` (read-only starting points; the app never overwrites them). |
| Log files | `~/.spacemissionstudio/logs/` (Windows: `%USERPROFILE%\.spacemissionstudio\logs\`); error dialogs name the current one. |
| Reference data | Basilisk's own download cache, as listed by `spacemissionstudio kernels-status`. |
| Space-weather downloads | `~/.cache/SpaceMissionStudio/spaceweather/` (only if you ask for newer data than the bundled copy). |

## 9. If something goes wrong

**"Basilisk is not installed/built" when you click Run.** The GUI works
without Basilisk, but runs need it. Path C: activate the environment
(`source .venv/bin/activate`) and run `pip install "bsk[all]==2.12.0"`.
Installed app: reinstall while connected to the internet.

**A reference file is missing (`FAIL` in `kernels-status`, or Run says a
support-data file is not installed).** Connect to the internet once and
run `spacemissionstudio kernels-status` again, or use the **Data** tab's
**Download... > Support data**.

**Linux: `ImportError: libEGL.so.1` (or another `.so`) when the GUI
starts.** A minimal system is missing Qt's libraries. On Debian/Ubuntu:

```bash
sudo apt-get install libegl1 libopengl0 libxcb-cursor0 libgl1 libxkbcommon0
```

**Windows: "running scripts is disabled on this system" for
`Activate.ps1`.** Allow scripts you start yourself, for your account
only, then activate again:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

**`pip` cannot find `bsk`.** Your Python is too old (3.9 or newer is
needed) or your platform has no prebuilt wheel (see
[section 1](#1-what-you-need)). `python3 --version` shows which Python the
environment uses. Building Basilisk from source is possible
(`../docs/source/Build.rst`) but rarely needed.

**Behind a company proxy.** `pip` and the reference-data download honour
the usual `HTTPS_PROXY` environment variable; set it before installing.

**The Results plot stays blank.** The plots draw in an embedded web view
(Qt WebEngine, a built-in Chromium), which on minimal Linux systems needs
a few more libraries than the rest of the GUI. On Debian/Ubuntu:

```bash
sudo apt-get install libnss3 libatk-bridge2.0-0 libgbm1
```

Still stuck? The log file named in the error dialog (section 8) has the
details; include it, and **Help > About**'s version, when you report a
problem. [`USER_MANUAL.md`](USER_MANUAL.md) section 11 covers problems
once the app is running.

## 10. Where to go next

* [`USER_MANUAL.md`](USER_MANUAL.md) -- using the app, from your first
  template to building your own mission (section 6). Also in the app
  under **Help > User Manual** (`F1`).
* [`spacemissionstudio/scenarios/templates/README.md`](spacemissionstudio/scenarios/templates/README.md)
  -- the 25 template missions and a suggested order to learn from them.
* [`examples/`](examples/README.md) -- using SpaceMissionStudio from Python.
* [`README.md`](README.md) -- the technical reference: capabilities,
  verification status, architecture, tests.
