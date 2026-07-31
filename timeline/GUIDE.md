# Program Timeline Generator — User Guide

## What It Does

Reads a CSV file of projects and milestones, then generates a visual HTML Gantt chart you can open in any browser. Run it once a week to produce a dated snapshot of your program timeline.

---

## Features

- **Color-coded projects** — each project gets its own color (up to 3 distinct colors; additional projects cycle through the same palette)
- **Milestone diamonds** — rows where `start_date` equals `end_date` render as a diamond marker instead of a bar
- **Week / Month view toggle** — switch the time axis granularity without regenerating the file
- **Zoom controls** — zoom in or out (25 % – 300 %) with `+` / `−` buttons; percentage is shown between them
- **Fit to screen** — the **Fit** button calculates the zoom level that fills the visible container width
- **Date labels** — end dates (or the single date for milestones) are drawn next to each bar; toggle them on/off with the **Show dates** checkbox
- **Date format toggle** — switch between compact `MM-DD` and full `YYYY-MM-DD` format for those labels
- **Click-to-inspect** — click any bar or diamond to see a popup with the milestone name and date range
- **Horizontal scroll** — scroll the chart to navigate through time; today's date is marked with a vertical line
- **Export PNG** — the **Export PNG** button renders the chart (including the title, legend, and all custom overlays) to a hi-DPI PNG file that downloads automatically
- **Dated output files** — each run writes a new file named by ISO week (e.g. `timeline_2026-W29.html`), so all previous snapshots are preserved

---

## Prerequisites

- Python 3.9 or later
- Internet connection (the chart loads Frappe Gantt from a CDN)

No extra Python packages are required — the script uses only the standard library.

---

## Step 1: Set Up Your Project Data

Open `data/projects.csv` in Excel, Google Sheets, or any text editor.

The file has four columns:

| Column | Description | Example |
|--------|-------------|---------|
| `project_name` | Name of the project (group) | `Website Redesign` |
| `milestone_name` | Name of the individual milestone | `Design Mockups` |
| `start_date` | Milestone start date (`YYYY-MM-DD`) | `2026-07-15` |
| `end_date` | Milestone end date (`YYYY-MM-DD`) | `2026-08-04` |

**Rules:**
- Dates must be in `YYYY-MM-DD` format (e.g. `2026-07-15`, not `07/15/2026`)
- Keep the header row exactly as-is
- Add as many milestone rows as you need per project
- Projects are identified by whatever unique values appear in `project_name`
- To mark a point-in-time milestone (diamond), set `start_date` and `end_date` to the same date

**Example:**
```
project_name,milestone_name,start_date,end_date
Website Redesign,Discovery & Requirements,2026-07-01,2026-07-14
Website Redesign,Design Mockups,2026-07-15,2026-08-04
Website Redesign,Development,2026-08-05,2026-09-15
Website Redesign,Launch,2026-09-15,2026-09-15
Mobile App Launch,Architecture & Setup,2026-07-01,2026-07-21
...
```

---

## Step 2: Open a Terminal

Navigate to the `timeline` directory:

```bash
cd /Users/amakar/Documents/GitHub/pmtools/timeline
```

---

## Step 3: Generate the Timeline

Run the script with no arguments to generate this week's chart:

```bash
python3 generate_timeline.py
```

You will see:

```
Generated: /Users/amakar/Documents/GitHub/pmtools/timeline/output/timeline_2026-W29.html
```

---

## Step 4: Open the Chart in Your Browser

Open the generated HTML file:

```bash
open output/timeline_2026-W29.html
```

Or navigate to it in Finder and double-click it. The Gantt chart will load in your default browser showing all projects color-coded with their milestones on a weekly axis.

**In the chart you can:**
- Click any bar or diamond to see a popup with the milestone name and dates
- Scroll horizontally to move through time
- See today's date marked with a vertical line
- Switch between **Week** and **Month** view using the toggle in the toolbar
- Zoom in/out with the **+** and **−** buttons, or click **Fit** to auto-fit all tasks to the screen width
- Show or hide date labels with the **Show dates** checkbox; switch between `MM-DD` and `YYYY-MM-DD` format with the adjacent toggle
- Click **Export PNG** to download a high-resolution PNG of the chart

---

## Step 5: Update Data Each Week

Each week before running the script:

1. Open `data/projects.csv`
2. Update dates or add new milestones as the program progresses
3. Save the file
4. Run `python3 generate_timeline.py` again

Each run creates a new file named with the current ISO week (e.g. `timeline_2026-W30.html`), so previous weeks are preserved in the `output/` folder.

---

## Optional: Generate for a Specific Week

To generate a chart for a specific week (useful for back-filling or previewing):

```bash
python3 generate_timeline.py --week 2026-07-14
```

Replace `2026-07-14` with the Monday of the target week. The output filename will reflect that week's ISO number.

---

## Optional: Use a Different CSV File

To point the script at a different input file:

```bash
python3 generate_timeline.py --csv /path/to/other/projects.csv
```

---

## File Layout Reference

```
timeline/
├── data/
│   └── projects.csv          ← edit this to update your timeline data
├── generate_timeline.py      ← the script (do not edit unless customizing)
├── GUIDE.md                  ← this guide
└── output/
    ├── timeline_2026-W29.html  ← generated charts (one per week)
    └── timeline_2026-W30.html
```

---

## Troubleshooting

**"Error: CSV not found"**
Make sure you are running the script from the `timeline/` directory, and that `data/projects.csv` exists.

**Chart is blank / Frappe Gantt doesn't load**
You need an internet connection — the chart library loads from a CDN. Check your network connection and reload the page.

**Dates look wrong on the chart**
Verify your CSV dates are in `YYYY-MM-DD` format (not `MM/DD/YYYY` or other formats). Check that `end_date` is on or after `start_date` for every row.

**Export PNG shows a blank or partial chart**
The export captures the chart exactly as rendered. If bars are not visible, try scrolling back to the start of the timeline first, then export. If the issue persists, try Chrome or Edge — some browsers restrict canvas-based image export.

**Old output file was overwritten**
It wasn't — each file is named by ISO week. If you run the script twice in the same week, it overwrites that week's file only.
