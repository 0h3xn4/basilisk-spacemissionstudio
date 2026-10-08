# Space weather data

`SW-All.txt` is CelesTrak's space-weather file (CSSI format, version 1.2),
unmodified except for line endings (stored with LF):

* source: <https://celestrak.org/SpaceData/SW-All.txt>
  (format: <https://celestrak.org/SpaceData/SpaceWx-format.php>);
* updated 2025-07-21 10:37 UTC;
* observed daily Kp/Ap and F10.7 from 1957-10-01 to 2025-07-20, CelesTrak's
  45-day daily forecast to 2025-08-28, and NOAA's monthly F10.7 forecast to
  2041-10;
* this copy was taken from the `spaceweather` Python package (version
  0.4.2), which redistributes it with CelesTrak's permission.

CelesTrak asks only that the URL above is given so others can find the
data and its documentation; there are no other licensing requirements
(Dr. T.S. Kelso, CelesTrak).

A newer copy downloaded by the app's startup prompt (with your consent)
replaces this one automatically; see `engine/spaceweather.py`.

`oct2026f10-prd.txt` is NASA Marshall Space Flight Center's solar-cycle
prediction of October 2026 ("Table 3: estimates of 13-month smoothed solar
activity for the balance of cycle 25, with a mean cycle for cycle 26"),
unmodified: monthly F10.7 and Ap at the 95th, 50th and 5th percentiles
from 2026-04 to 2041-10.

* source: <https://www.nasa.gov/solar-cycle-progression-and-forecast/>
  (this issue: `wp-content/uploads/2026/10/oct2026f10-prd.txt`);
* a NASA work, so not subject to copyright in the US.

ESA's guideline EOP-FM/2024-07-177 (AD10) Sec. 5.9 prescribes MSFC's
prediction for future solar activity: the 95th percentile for operations
budgets, the 50th for end of life, NRLMSISE-00, and the last 132 months
repeated past the file's end. A study's own MSFC file can be set in
Propagation setup instead.
