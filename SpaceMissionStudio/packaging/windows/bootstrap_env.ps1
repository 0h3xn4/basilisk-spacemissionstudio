<#
.SYNOPSIS
    Runs during Inno Setup's [Run] step (see spacemissionstudio.iss) to create
    SpaceMissionStudio's own Python environment and install into it: creates a
    venv under the install directory, installs Basilisk ("bsk[all]" from
    PyPI -- the one thing that needs internet access during setup, and
    can take a few minutes), then installs SpaceMissionStudio itself from the
    wheel the installer already bundled (no network needed for that part
    -- see spacemissionstudio.iss's own header for how that wheel gets there).

    Same logic as packaging/install.ps1, trimmed to what a non-interactive
    installer step needs (a fixed, already-known install directory and a
    bundled wheel, no CLI flags) -- see that script for the same design
    already used for the plain (non-installer) Windows install path.

.PARAMETER InstallDir
    The installer's target directory (Inno Setup's {app}).
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$InstallDir
)

$ErrorActionPreference = "Stop"

function Fail($Message) {
    Write-Host "SPACEMISSIONSTUDIO_SETUP_ERROR: $Message"
    exit 1
}

$VenvDir = Join-Path $InstallDir "venv"
if (Test-Path $VenvDir) {
    Remove-Item -Recurse -Force $VenvDir
}

Write-Host "SpaceMissionStudio: creating its Python environment at $VenvDir ..."
python -m venv $VenvDir
if ($LASTEXITCODE -ne 0) {
    Fail "python -m venv failed (exit code $LASTEXITCODE)"
}

$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
& $VenvPython -m pip install --quiet --upgrade pip
if ($LASTEXITCODE -ne 0) {
    Fail "pip upgrade failed (exit code $LASTEXITCODE)"
}

Write-Host "SpaceMissionStudio: installing Basilisk 2.12.0 (bsk[all]==2.12.0, the version SpaceMissionStudio is qualified with) from PyPI -- this needs internet access and can take a few minutes ..."
& $VenvPython -m pip install --quiet "bsk[all]==2.12.0"
if ($LASTEXITCODE -ne 0) {
    Fail "Basilisk install failed (exit code $LASTEXITCODE)"
}

$Wheel = Get-ChildItem (Join-Path $InstallDir "dist\spacemissionstudio-*.whl") -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1 -ExpandProperty FullName
if (-not $Wheel) {
    Fail "no bundled spacemissionstudio-*.whl found under $InstallDir\dist -- this installer build is broken"
}

Write-Host "SpaceMissionStudio: installing SpaceMissionStudio itself from the bundled wheel ..."
& $VenvPython -m pip install --quiet "$Wheel[gui]"
if ($LASTEXITCODE -ne 0) {
    Fail "spacemissionstudio install failed (exit code $LASTEXITCODE)"
}

# SpaceMissionStudio never accesses the network at runtime (real user
# requirement: "the app must be completely closed off and offline, only
# exception is the installation process") -- this is that one exception.
# engine.kernels.require_kernels()'s own default (ALL_SUPPORT_DATA_FILES)
# covers every SPICE/gravity-harmonics/magnetic-field support-data file
# any of this app's code paths read, fetching each one once into
# Basilisk's own local pooch cache; every later get_path() call for the
# rest of this install's lifetime resolves from that cache with no
# network touched at all. Fatal here (same as the Basilisk/
# spacemissionstudio install steps above): this script always installs a
# real Basilisk, so a scenario that can never actually run without its
# own kernels is exactly the kind of "configured but broken" state this
# installer step should refuse, not silently ship. Run only now (not
# right after Basilisk, above): it imports spacemissionstudio itself,
# which isn't installed into this venv until the pip install just above
# completes.
Write-Host "SpaceMissionStudio: pre-fetching SPICE kernels and other support data -- this needs internet access ..."
& $VenvPython -c "
from spacemissionstudio.engine import kernels
kernels.require_kernels()
"
if ($LASTEXITCODE -ne 0) {
    Fail "support-data pre-fetch failed (exit code $LASTEXITCODE) -- check internet access and try again"
}

# IERS-based Earth orientation (NAIF ITRF93 Earth PCKs, ~36 MB) into the
# install-wide directory every user reads. Non-fatal: without them runs
# use IAU_EARTH and say so.
Write-Host "SpaceMissionStudio: fetching Earth orientation files (NAIF ITRF93 Earth PCKs, ~36 MB) ..."
& $VenvPython -c "
from spacemissionstudio.engine import earth_orientation
earth_orientation.fetch(earth_orientation.SYSTEM_DIR)
"
if ($LASTEXITCODE -ne 0) {
    Write-Host "SpaceMissionStudio: could not fetch the Earth orientation files -- runs use IAU_EARTH until they are fetched."
}

# No custom Start Menu icon is rendered here: gui/icons.py's
# ensure_icon_file() always writes PNG data regardless of the path's own
# extension (see that function's own docstring) -- a Windows .lnk's
# IconLocation needs a real .ico/.exe/.dll, not a bare .png, so a
# mislabeled "icon.ico" containing PNG bytes would not actually resolve.
# Same reasoning, same decision, as packaging/install.ps1's own Start
# Menu shortcut -- see that script's comment for the full explanation.
# The shortcut (spacemissionstudio.iss's [Icons] section) uses
# spacemissionstudio.exe's own embedded icon instead.

Write-Host "SpaceMissionStudio: environment setup complete."
exit 0
