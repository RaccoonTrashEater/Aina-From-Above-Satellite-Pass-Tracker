# Aina-From-Above-Satellite-Pass-Tracker

Ephemeris tracker for the Aina From Above project that tracks specific satellite passes using the user's general coordinates and NORAD Catalog Number, otherwise known as NORAD ID or SATCAT number.

Pass-prediction tool built for **Aina From Above**, a portable satellite ground station (cyberdeck) project for receiving Meteor-M weather satellite imagery over Maui, Hawaiʻi.

The ground station ran on a Raspberry Pi with an RTL-SDR Blog V4, a SAWbird+ NOAA filter/LNA (137 MHz), and an Elk log-periodic antenna, using [SatDump](https://github.com/SatDump/SatDump) to decode and reconstruct the images. This script handled the planning side: it pulls fresh TLEs from Celestrak and computes Maui-specific pass times so we knew exactly when to be out with the antenna, more precisely than general-purpose sites like Heavens Above.

## What it does

- Downloads the latest TLE orbital elements from [Celestrak](https://celestrak.org) for:
  - **METEOR M2-3** (NORAD 57166)
  - **METEOR M2-4** (NORAD 59051)
  - **ISS** (NORAD 25544)
- Uses [Skyfield](https://rhodesmill.org/skyfield/) to find every pass above 10° elevation over the next 3 days from Maui (20.8893° N, 156.4729° W)
- Logs each pass's **Rise / Culminate (Max) / Set** time in Hawaiʻi Standard Time, with altitude and azimuth
- Saves results as dated CSV logs (`passlog_<name>_<date>.csv`, auto-versioned so nothing gets overwritten)
- Prints a formatted pass table in the terminal and lets you reload any of your recent logs

```
┌─────────────── ISS ───────────────┐

  DATE: 2026-11-17
  ────────────────────────────────────────────────────
  │ Time (HST) │      Event       │   Alt   │   Az    │
  ────────────────────────────────────────────────────
  │  10:33:07  │ Rise             │   10.0° │  214.4° │
  │  10:36:26  │ Culminate (Max)  │   76.5° │  128.3° │
  │  10:39:45  │ Set              │   10.0° │   42.6° │
  ────────────────────────────────────────────────────
```
*(example layout — times shown are illustrative)*

## Usage

```bash
pip install -r requirements.txt
python pass_tracker.py
```

Menu options:

1. **Scrape Fresh Data** — fetch new TLEs, compute passes, save a new log, and display it
2. **Load CSV File** — list your 5 most recent logs and open one (Tab-completion works on Linux/macOS)
3. **Exit**

Logs are saved to a `pass_logs/` folder next to the script. Change `TARGET_DIR` at the top of the file to save them somewhere else.

## Data source: CelesTrak (please don't over-request)

All orbital data comes from [CelesTrak](https://celestrak.org), a free public source of satellite orbital elements maintained by Dr. T.S. Kelso. Every time you pick **Scrape Fresh Data**, the script makes one request to CelesTrak per satellite, spaced 3 seconds apart.

Please be considerate with it:

- **Don't scrape more often than you need to.** CelesTrak only updates its orbital data about every 2 hours, so re-scraping inside that window gets you the same numbers. One scrape gives you 3 days of predictions. For planning passes, once or twice a day is plenty.
- **Don't put this in a tight loop or a frequent cron job.** If you automate it, keep it to once every few hours at most.
- **Don't track huge lists of satellites with this script.** It makes one request per satellite. If you want a whole constellation, download CelesTrak's group files instead.
- **If you start getting errors (403, 404, 500, 503), stop and look into it. Don't keep retrying.** CelesTrak sends 403s to clients it considers abusive, and ignoring them can get your IP blocked.

Full rules are in [CelesTrak's usage policy](https://celestrak.org/usage-policy.php).

> **Note on the TLE format:** In July 2026 the satellite catalog ran past 5-digit numbers. Newly catalogued objects (NORAD 100000+) can't be represented in TLE format, so this script can't fetch them as written. CelesTrak recommends moving to its CSV/OMM formats.

## Customizing it for your own setup

Everything below lives in `pass_tracker.py`. Most of it is inside `scrape_data()`.

### 1. Your location

Find this line and replace it with your own latitude and longitude:

```python
maui = Topos('20.8893 N', '156.4729 W')
```

For example, Denver would be `Topos('39.7392 N', '104.9903 W')`. You can find your coordinates by right-clicking your spot in Google Maps. The variable is still called `maui`, but that's only a name, so you can rename it if you want (rename it in both places it's used).

### 2. Your time zone

Times get converted from UTC to Hawaiʻi time on this line:

```python
hst_time = ti.utc_datetime().replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=-10)))
```

Change `hours=-10` to your own UTC offset, for example `-7` for Mountain Standard Time or `+1` for Central European Time. This is a fixed offset, so it won't follow daylight saving time. Bump it by an hour when your clocks change.

The column label `"Time (HST)"` shows up in three places: the `headers` list in `scrape_data()`, and two spots in `read_from_csv()`. If you rename it (to `"Time (MST)"`, say), change all three to the same string, or the CSV reader won't find the column.

### 3. Which satellites to track

Satellites are listed by their **NORAD Catalog Number** (also called the NORAD ID or SATCAT number) in the `satellites` dictionary:

```python
satellites = {
    "ISS": "25544",
    "METEOR M2-3": "57166",
    "METEOR M2-4": "59051"
}
```

Add, remove, or swap entries as `"Display Name": "NORAD number"`. To look up a satellite's number, search for it on [Celestrak's SATCAT search](https://celestrak.org/satcat/search.php) or [N2YO](https://www.n2yo.com). The display name is only for your logs. Celestrak fetches by the number.

### 4. Minimum elevation

Passes only count once the satellite climbs above 10°:

```python
t, events = satellite.find_events(maui, t0, t1, altitude_degrees=10.0)
```

Raise it if you have trees, buildings, or mountains on your horizon. Lower it if you have a clear view and want to catch the edges of passes. For APT/LRPT weather imagery, low passes usually give noisy or partial images anyway.

### 5. How far ahead to predict

The prediction window is 3 days:

```python
t1 = ts.from_datetime(now_utc + timedelta(days=3))
```

Change `days=3` to whatever you need. TLEs lose accuracy the further out you go, so a week is about the useful limit. Re-scrape often for best timing.

### 6. Where logs get saved

At the top of the file, `TARGET_DIR` defaults to a `pass_logs/` folder next to the script. Set it to any folder path you like.

## Credits

- **Zachary Montondo** ([@RaccoonTrashEater](https://github.com/RaccoonTrashEater)) — pass tracker software
- **Vivian Breman** — Aina From Above co-builder
- Advised by **Dr. Buddhi Rai**, University of Hawaiʻi Maui College

Aina From Above was supported by NSF Grant #2030979.

## License

[MIT](LICENSE)
