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
