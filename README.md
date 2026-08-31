# FED3 Kriegsfeld

Tools for logging and visualising FED3 (Feeding Experimentation Device 3) data
for the Kriegsfeld lab.

## Contents

```
FED3_Kriegsfeld/
├── FED3_RT_Actogram.py       # Streamlit dashboard (main app)
├── fed3_monitor.py           # USB serial logger + jam/disconnect email alerts
├── FED3_CSV_to_Actogram.py   # Stitches many CSVs into a ClockLab AWD + double-plotted actogram
├── .streamlit/config.toml    # Pink theme for the dashboard
└── data/
    ├── raw/                  # Recorded FED3 CSVs (checked in)
    ├── outputs/              # Generated PNGs, AWD files, downloaded workbooks, PDFs
    └── mouse_weights.csv     # Auto-created when you save a weight in the dashboard
```

## Setup

Install once (into whichever Python environment you use for this project):

```
pip install streamlit pandas openpyxl matplotlib pyserial
```

## Dashboard — `FED3_RT_Actogram.py`

Pulls a multi-tab Google Sheet of FED3 data, shows per-mouse actograms,
compares today's pellet intake to yesterday's, warns if consumption drops
below a threshold, and lets you log daily body weights.

Launch:

```
cd /Users/carolinalangaro/Desktop/FED3_Kriegsfeld
streamlit run FED3_RT_Actogram.py
```

Then paste the Google Sheet URL into the sidebar and click **Refresh from
sheet**. The sheet must be shared as "Anyone with the link — Viewer".

### Sidebar controls
- **Google Sheet URL** — source workbook (one tab per mouse)
- **Feeding-day boundary hour** — default 23 (11pm). A "day" for the
  intake comparison runs from this hour to this hour the next day. Change
  if your restricted-feeding schedule shifts.
- **Pellet weight (mg)** — default 20; used to convert counts to grams.
- **Warning threshold** — default 0.80 (warns if today ÷ yesterday < 80%).
- **Actogram bin size** — default 10 minutes.

### Main view
- **Feeding-day range picker** — filters actograms, the today/yesterday
  cards, the warning banner, and the PDF export.
- **Download PDF** — exports the currently-filtered actograms (one page
  per mouse).
- **Per-mouse tabs** — each tab shows:
  - Today / yesterday pellet counts (with grams) and their ratio
  - Warning banner if the ratio is below the threshold
  - The actogram itself
  - A weight-entry form and a running table of the last 10 weights

Weights are appended to `data/mouse_weights.csv` (columns: `date`,
`mouse_id`, `weight_g`). Safe to open in Excel.

## USB logger — `fed3_monitor.py`

Logs live pellet events over USB serial and emails alerts on jams or
disconnects.

```
python3 fed3_monitor.py            # start logging
python3 fed3_monitor.py --plot     # generate an actogram from the newest CSV
```

New CSVs land in the current working directory. Move them into
`data/raw/` when you're done recording if you want them archived with the
rest.

> **Security note.** `fed3_monitor.py` currently contains a hardcoded
> Gmail address and app password (`SENDER_APP_PASSWORD`). That value is
> already in the git history, so it should be **revoked in Google
> Account → Security → App passwords** and replaced by an environment
> variable or a local `.env` file (ignored by git).

## CSV stitcher — `FED3_CSV_to_Actogram.py`

Reads every CSV in the folder set by the `INPUT_FOLDER` constant at the
top of the file, stitches them into a single ClockLab-compatible `.awd`
file, and renders a 48-hour double-plotted actogram PNG.

Edit `INPUT_FOLDER` and `ANIMAL_ID` at the top of the script, then run:

```
python3 FED3_CSV_to_Actogram.py
```
