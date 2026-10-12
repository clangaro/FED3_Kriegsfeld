"""
FED3 Actogram Dashboard (Streamlit)

Launch:
    cd /Users/carolinalangaro/Desktop/FED3_Kriegsfeld
    streamlit run FED3_RT_Actogram.py

Reads a multi-tab Google Sheet of FED3 data, plots per-mouse actograms,
compares today's pellet intake to yesterday's (feeding-day boundary
configurable), warns when consumption drops below a threshold, and lets
you log daily body weights.
"""

import io
import os
import re
import urllib.request
from datetime import date, datetime

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
from matplotlib.backends.backend_pdf import PdfPages

# --- Paths & constants ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "data")
OUTPUT_DIR = os.path.join(DATA_DIR, "outputs")
WEIGHTS_FILE = os.path.join(DATA_DIR, "mouse_weights.csv")
TIME_COL = "MM/DD/YYYY hh:mm:ss.SSS"

# Pink palette (mirrors .streamlit/config.toml)
PINK_PRIMARY = "#d6336c"
PINK_BG = "#fff5f8"
PINK_SOFT = "#ffe0ec"
PINK_DEEP = "#3d0a1e"


# --- Page setup & CSS ---
st.set_page_config(page_title="FED3 Actogram Dashboard", layout="wide")

st.markdown(
    f"""
<style>
  .block-container {{ padding-top: 2rem; }}
  .metric-card {{
    background: {PINK_SOFT};
    border-radius: 14px;
    padding: 18px 20px;
    box-shadow: 0 2px 10px rgba(214, 51, 108, 0.12);
    border: 1px solid rgba(214, 51, 108, 0.15);
  }}
  .metric-label {{
    color: {PINK_DEEP};
    font-size: 0.85rem;
    font-weight: 600;
    opacity: 0.75;
    letter-spacing: 0.03em;
    text-transform: uppercase;
  }}
  .metric-value {{
    color: {PINK_PRIMARY};
    font-size: 1.7rem;
    font-weight: 700;
    line-height: 1.2;
    margin-top: 4px;
  }}
  .warning-banner {{
    background: {PINK_PRIMARY};
    color: white;
    padding: 16px 20px;
    border-radius: 14px;
    font-weight: 600;
    margin: 14px 0;
    box-shadow: 0 3px 12px rgba(214, 51, 108, 0.35);
  }}
  .ok-banner {{
    background: {PINK_SOFT};
    color: {PINK_DEEP};
    padding: 14px 20px;
    border-radius: 14px;
    font-weight: 600;
    margin: 14px 0;
    border: 1px solid rgba(214, 51, 108, 0.25);
  }}
  h1, h2, h3 {{ color: {PINK_PRIMARY}; }}
  .stTabs [data-baseweb="tab-list"] {{ gap: 4px; }}
  .stTabs [data-baseweb="tab"] {{
    background: {PINK_SOFT};
    border-radius: 10px 10px 0 0;
    padding: 8px 16px;
  }}
  .stTabs [aria-selected="true"] {{
    background: {PINK_PRIMARY} !important;
    color: white !important;
  }}
</style>
""",
    unsafe_allow_html=True,
)


# --- Data helpers ---
def download_google_sheet(sheet_url: str):
    """Download the sheet as .xlsx to data/outputs/. Returns (path, error_msg)."""
    match = re.search(r"/d/([a-zA-Z0-9-_]+)", sheet_url)
    if not match:
        return None, "Could not extract Spreadsheet ID from URL."
    sheet_id = match.group(1)
    export_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    xlsx_path = os.path.join(OUTPUT_DIR, f"fed3_multifeeder_{sheet_id[:8]}.xlsx")
    try:
        urllib.request.urlretrieve(export_url, xlsx_path)
        return xlsx_path, None
    except Exception as e:
        return None, f"Download failed: {e}. Ensure the sheet is shared as 'Anyone with the link'."


def _feeding_day_series(ts: pd.Series, boundary_hour: int) -> pd.Series:
    """Map each timestamp to its feeding-day date.

    A feeding day runs from `boundary_hour` on day D-1 to `boundary_hour` on
    day D — so any event with hour >= boundary_hour belongs to the *next*
    calendar day's feeding window. We implement that by shifting timestamps
    forward and taking the date.
    """
    shifted = ts + pd.Timedelta(hours=(24 - boundary_hour))
    return shifted.dt.date


@st.cache_data(show_spinner=False)
def load_workbook_pellets(xlsx_path: str, boundary_hour: int):
    """Read every tab, keep only PelletInWell events, tag each with its feeding-day."""
    all_tabs = pd.read_excel(xlsx_path, sheet_name=None)
    result = {}
    for tab_name, df in all_tabs.items():
        if TIME_COL not in df.columns or "Event" not in df.columns:
            continue
        df = df.copy()
        df[TIME_COL] = pd.to_datetime(df[TIME_COL], errors="coerce")
        df = df.dropna(subset=[TIME_COL])
        pellets = df[df["Event"].astype(str).str.contains("PelletInWell", case=False, na=False)].copy()
        if pellets.empty:
            continue
        pellets["FeedingDay"] = _feeding_day_series(pellets[TIME_COL], boundary_hour)
        result[tab_name] = pellets
    return result


def make_actogram(
    pellets: pd.DataFrame,
    tab_name: str,
    selected_days,
    bin_minutes: int = 10,
    light_start: float = 7.0,
    dark_start: float = 19.0,
):
    """Render an actogram figure for one mouse over the selected feeding days."""
    pellets = pellets[pellets["FeedingDay"].isin(selected_days)].copy()
    if pellets.empty:
        return None
    pellets["Event_Count"] = 1
    binned = (
        pellets.set_index(TIME_COL)["Event_Count"]
        .resample(f"{bin_minutes}min")
        .sum()
        .reset_index()
    )
    binned["Date"] = binned[TIME_COL].dt.date
    binned["Time_of_Day"] = binned[TIME_COL].dt.hour + binned[TIME_COL].dt.minute / 60.0

    unique_dates = sorted(binned["Date"].unique())
    n = len(unique_dates)
    if n == 0:
        return None
    max_events = binned["Event_Count"].max()
    y_max = (max_events * 1.1) if pd.notna(max_events) and max_events > 0 else 5

    fig, axes = plt.subplots(nrows=n, ncols=1, figsize=(10, 1.3 * n), sharex=True, sharey=True)
    if n == 1:
        axes = [axes]
    fig.suptitle(f"FED3 Actogram — {tab_name}", fontsize=13, fontweight="bold", color=PINK_PRIMARY, y=1.02)
    bar_w = bin_minutes / 60.0

    for i, (ax, d) in enumerate(zip(axes, unique_dates)):
        day_data = binned[binned["Date"] == d]
        ax.axvspan(0, light_start, color="lightgray", alpha=0.35, lw=0)
        ax.axvspan(light_start, dark_start, color="lemonchiffon", alpha=0.45, lw=0)
        ax.axvspan(dark_start, 24, color="lightgray", alpha=0.35, lw=0)
        ax.bar(
            day_data["Time_of_Day"],
            day_data["Event_Count"],
            width=bar_w,
            color=PINK_DEEP,
            align="edge",
            edgecolor="none",
        )
        ax.set_xlim(0, 24)
        ax.set_ylim(0, y_max)
        ax.locator_params(axis="y", nbins=3)
        ax.tick_params(axis="y", labelsize=8, colors=PINK_DEEP)
        ax.set_ylabel(
            d.strftime("%Y-%m-%d"),
            rotation=0,
            labelpad=45,
            ha="right",
            va="center",
            fontsize=9,
            color=PINK_DEEP,
        )
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            ax.spines[s].set_color(PINK_PRIMARY)
            ax.spines[s].set_linewidth(1.0)
        if ax is not axes[-1]:
            ax.tick_params(bottom=False)

    axes[-1].set_xlabel("Time of Day (h)", fontsize=11, labelpad=10, color=PINK_DEEP)
    axes[-1].set_xticks(range(0, 25, 2))
    axes[-1].tick_params(axis="x", colors=PINK_DEEP)
    plt.subplots_adjust(hspace=0.0)
    return fig


def load_weights() -> pd.DataFrame:
    if os.path.exists(WEIGHTS_FILE):
        df = pd.read_csv(WEIGHTS_FILE)
        df["date"] = pd.to_datetime(df["date"]).dt.date
        return df
    return pd.DataFrame(columns=["date", "mouse_id", "weight_g"])


def save_weight(mouse_id: str, weight_g: float, on_date):
    df = load_weights()
    mask = (df["mouse_id"] == mouse_id) & (df["date"] == on_date)
    df = df[~mask]
    new_row = pd.DataFrame([{"date": on_date, "mouse_id": mouse_id, "weight_g": weight_g}])
    df = pd.concat([df, new_row], ignore_index=True).sort_values(["mouse_id", "date"])
    os.makedirs(DATA_DIR, exist_ok=True)
    df.to_csv(WEIGHTS_FILE, index=False)


def metric_card(label: str, value: str) -> str:
    return (
        f"<div class='metric-card'>"
        f"<div class='metric-label'>{label}</div>"
        f"<div class='metric-value'>{value}</div>"
        f"</div>"
    )


# --- Sidebar ---
st.sidebar.header("Settings")

sheet_url = st.sidebar.text_input(
    "Google Sheet URL",
    value=st.session_state.get("sheet_url", ""),
    placeholder="https://docs.google.com/spreadsheets/d/...",
)

if st.sidebar.button("Refresh from sheet", use_container_width=True):
    if not sheet_url.strip():
        st.sidebar.error("Enter a sheet URL first.")
    else:
        st.session_state["sheet_url"] = sheet_url
        with st.spinner("Downloading workbook…"):
            path, err = download_google_sheet(sheet_url)
        if err:
            st.sidebar.error(err)
        else:
            st.session_state["xlsx_path"] = path
            load_workbook_pellets.clear()
            st.sidebar.success("Downloaded.")

st.sidebar.divider()
boundary_hour = st.sidebar.number_input(
    "Feeding-day boundary hour (0–23)",
    min_value=0,
    max_value=23,
    value=23,
    help="A feeding day starts at this hour. Default 23 = 11pm (end of feeding).",
)
pellet_mg = st.sidebar.number_input(
    "Pellet weight (mg)", min_value=1.0, max_value=100.0, value=20.0, step=0.5
)
threshold = st.sidebar.slider(
    "Warning threshold (today ÷ yesterday)", min_value=0.5, max_value=1.0, value=0.80, step=0.05
)
bin_minutes = st.sidebar.number_input(
    "Actogram bin size (min)", min_value=1, max_value=60, value=10
)

# --- Main ---
st.title("FED3 Actogram Dashboard")

xlsx_path = st.session_state.get("xlsx_path")
if not xlsx_path or not os.path.exists(xlsx_path):
    st.info("Enter a Google Sheet URL in the sidebar and click **Refresh from sheet**.")
    st.stop()

pellets_by_mouse = load_workbook_pellets(xlsx_path, int(boundary_hour))
if not pellets_by_mouse:
    st.warning("No mice with `PelletInWell` events found in the workbook.")
    st.stop()

# Global feeding-day range
all_days = sorted({d for p in pellets_by_mouse.values() for d in p["FeedingDay"].unique()})
min_d, max_d = all_days[0], all_days[-1]

top_l, top_r = st.columns([2, 1])
with top_l:
    date_range = st.date_input(
        "Feeding-day range",
        value=(min_d, max_d),
        min_value=min_d,
        max_value=max_d,
    )
if isinstance(date_range, tuple) and len(date_range) == 2:
    start_d, end_d = date_range
else:
    d0 = date_range if not isinstance(date_range, tuple) else date_range[0]
    start_d = end_d = d0
selected_days = [d for d in all_days if start_d <= d <= end_d]

# PDF export
with top_r:
    st.write("")
    st.write("")
    pdf_buf = io.BytesIO()
    with PdfPages(pdf_buf) as pdf:
        for tab_name, pellets in pellets_by_mouse.items():
            fig = make_actogram(pellets, tab_name, selected_days, bin_minutes=int(bin_minutes))
            if fig is not None:
                pdf.savefig(fig, bbox_inches="tight", facecolor="white")
                plt.close(fig)
    pdf_buf.seek(0)
    st.download_button(
        "Download PDF of current view",
        data=pdf_buf,
        file_name=f"FED3_Actograms_{datetime.now():%Y%m%d_%H%M%S}.pdf",
        mime="application/pdf",
        use_container_width=True,
    )

st.divider()

# Per-mouse tabs
mouse_ids = list(pellets_by_mouse.keys())
tabs = st.tabs(mouse_ids)

for tab, mouse_id in zip(tabs, mouse_ids):
    with tab:
        pellets = pellets_by_mouse[mouse_id]
        st.markdown(f"### {mouse_id}")

        # Counts per feeding-day, restricted to selected range
        counts = pellets.groupby("FeedingDay").size().reindex(selected_days, fill_value=0)
        today_d = selected_days[-1] if selected_days else None
        yesterday_d = selected_days[-2] if len(selected_days) >= 2 else None
        today_n = int(counts.loc[today_d]) if today_d is not None else 0
        yesterday_n = int(counts.loc[yesterday_d]) if yesterday_d is not None else 0
        today_g = today_n * pellet_mg / 1000.0
        yesterday_g = yesterday_n * pellet_mg / 1000.0
        ratio = (today_n / yesterday_n) if yesterday_n > 0 else None

        c1, c2, c3 = st.columns(3)
        with c1:
            label = f"Today ({today_d})" if today_d else "Today"
            st.markdown(metric_card(label, f"{today_n} pellets · {today_g:.2f} g"), unsafe_allow_html=True)
        with c2:
            label = f"Yesterday ({yesterday_d})" if yesterday_d else "Yesterday"
            st.markdown(metric_card(label, f"{yesterday_n} pellets · {yesterday_g:.2f} g"), unsafe_allow_html=True)
        with c3:
            ratio_txt = f"{ratio:.0%}" if ratio is not None else "—"
            st.markdown(metric_card("Today ÷ yesterday", ratio_txt), unsafe_allow_html=True)

        if ratio is not None and ratio < threshold:
            st.markdown(
                f"<div class='warning-banner'>Warning — {mouse_id} ate "
                f"{ratio:.0%} of yesterday's amount (threshold {threshold:.0%}).</div>",
                unsafe_allow_html=True,
            )
        elif ratio is not None:
            st.markdown(
                f"<div class='ok-banner'>Consumption OK — {ratio:.0%} of yesterday's amount.</div>",
                unsafe_allow_html=True,
            )

        # Actogram
        fig = make_actogram(pellets, mouse_id, selected_days, bin_minutes=int(bin_minutes))
        if fig is not None:
            st.pyplot(fig, clear_figure=True)
        else:
            st.info("No events in the selected date range.")

        # Weights
        st.divider()
        st.markdown("#### Daily body weight")
        wc1, wc2 = st.columns([1, 1])
        with wc1:
            weigh_date = st.date_input(
                "Weigh date", value=date.today(), key=f"wd_{mouse_id}"
            )
            weight = st.number_input(
                "Weight (g)",
                min_value=0.0,
                max_value=200.0,
                value=25.0,
                step=0.1,
                key=f"wt_{mouse_id}",
            )
            if st.button("Save weight", key=f"sv_{mouse_id}", use_container_width=True):
                save_weight(mouse_id, float(weight), weigh_date)
                st.success(f"Saved: {mouse_id} · {weigh_date} · {weight:.1f} g")
        with wc2:
            weights_df = load_weights()
            mine = (
                weights_df[weights_df["mouse_id"] == mouse_id]
                .sort_values("date", ascending=False)
                .head(10)
            )
            if not mine.empty:
                st.dataframe(
                    mine[["date", "weight_g"]].reset_index(drop=True),
                    hide_index=True,
                    use_container_width=True,
                )
            else:
                st.caption("No weights logged yet for this mouse.")
