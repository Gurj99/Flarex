import streamlit as st
import requests
import pandas as pd
import time
import re
import io
from requests.auth import HTTPBasicAuth

# ── Page config ──────────────────────────────────────────────
st.set_page_config(
    page_title="Flarex · FX Screener",
    page_icon="⚡",
    layout="wide",
)

# ── Custom CSS (Flarex brand) ─────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
    background-color: #111111;
    color: #f2f2f2;
}

.stApp { background-color: #111111; }

h1, h2, h3 {
    font-family: 'Bebas Neue', sans-serif;
    letter-spacing: 0.04em;
    color: #f2f2f2;
}

.flarex-header {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 24px 0 8px;
    border-bottom: 1px solid rgba(255,255,255,0.08);
    margin-bottom: 32px;
}

.flarex-logo {
    font-family: 'Bebas Neue', sans-serif;
    font-size: 2rem;
    letter-spacing: 0.12em;
    color: #f2f2f2;
}

.flarex-dot {
    width: 10px; height: 10px;
    background: #e8ff00;
    border-radius: 50%;
    display: inline-block;
    margin-right: 8px;
}

.tag {
    background: rgba(232,255,0,0.08);
    border: 1px solid rgba(232,255,0,0.25);
    color: #e8ff00;
    padding: 3px 10px;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    border-radius: 2px;
}

.match-card {
    background: #181818;
    border: 1px solid rgba(255,255,255,0.08);
    border-left: 3px solid #e8ff00;
    padding: 16px 20px;
    margin-bottom: 10px;
    border-radius: 2px;
}

.match-name {
    font-weight: 700;
    font-size: 1rem;
    margin-bottom: 4px;
}

.match-meta {
    font-size: 0.78rem;
    color: #888;
    margin-bottom: 8px;
}

.match-keywords {
    font-size: 0.76rem;
    color: #e8ff00;
    opacity: 0.8;
}

.stProgress > div > div { background-color: #e8ff00 !important; }

div[data-testid="stFileUploader"] {
    background: #181818;
    border: 1px dashed rgba(255,255,255,0.15);
    border-radius: 4px;
    padding: 8px;
}

.stTextInput input, .stPasswordInput input {
    background: #181818 !important;
    border: 1px solid rgba(255,255,255,0.14) !important;
    color: #f2f2f2 !important;
    border-radius: 2px !important;
}

.stButton button {
    background: #e8ff00;
    color: #111;
    font-weight: 700;
    font-family: 'Inter', sans-serif;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    border: none;
    border-radius: 2px;
    padding: 10px 28px;
    width: 100%;
}

.stButton button:hover { opacity: 0.85; background: #e8ff00; color: #111; }

.stAlert { border-radius: 2px; }
</style>
""", unsafe_allow_html=True)

# ── Constants ─────────────────────────────────────────────────
KEYWORDS = [
    "foreign currency", "foreign exchange", "fx risk", "currency risk",
    "currency exposure", "exchange rate", "hedging", "hedge",
    "forward contract", "currency swap", "functional currency",
    "translation risk", "transaction risk", "denominated in",
    "currency fluctuation", "revaluation", "spot rate",
    "currency gain", "currency loss", "monetary assets",
    "monetary liabilities", "overseas operations",
    "international operations", "cross-border",
    "dollar", "euro", "yen", "usd", "eur", "jpy",
    "foreign currency translation", "currency translation",
    "translation adjustment", "translation difference",
]

BASE = "https://api.company-information.service.gov.uk"

# ── Helpers ───────────────────────────────────────────────────
def pad(n):
    n = str(n).strip()
    if re.match(r'^[A-Za-z]{2}', n):
        return n.upper()
    return n.zfill(8)

def ch_get(path, api_key, retries=3):
    auth = HTTPBasicAuth(api_key, "")
    for attempt in range(retries):
        try:
            r = requests.get(BASE + path, auth=auth, timeout=15)
            if r.status_code == 200:
                return r
            elif r.status_code == 429:
                time.sleep(10 * (attempt + 1))
            elif r.status_code == 404:
                return r
            else:
                time.sleep(2)
        except Exception:
            time.sleep(3)
    return None

def get_text(doc_meta_url, api_key):
    auth = HTTPBasicAuth(api_key, "")
    try:
        meta_r = requests.get(doc_meta_url, auth=auth, timeout=15)
        if meta_r.status_code != 200:
            return ""
        resources = meta_r.json().get("resources", {})
        for mime in ["application/xhtml+xml", "text/html"]:
            if mime in resources:
                r = requests.get(
                    doc_meta_url + "/content", auth=auth,
                    headers={"Accept": mime}, timeout=30
                )
                if r.status_code == 200:
                    text = re.sub(r"<[^>]+>", " ", r.text)
                    return re.sub(r"\s+", " ", text).lower()
        if "application/pdf" in resources:
            r = requests.get(
                doc_meta_url + "/content", auth=auth,
                headers={"Accept": "application/pdf"}, timeout=30
            )
            if r.status_code == 200:
                try:
                    import pdfplumber
                    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
                        text = " ".join(p.extract_text() or "" for p in pdf.pages)
                    return re.sub(r"\s+", " ", text).lower()
                except Exception:
                    pass
    except Exception:
        pass
    return ""

def scan_text(text):
    return [kw for kw in KEYWORDS if kw in text]

def parse_csv(file_bytes):
    lines = file_bytes.decode("utf-8-sig").splitlines()
    if not lines:
        return None, None, None
    header = [h.strip().strip('"') for h in lines[0].split(",")]
    num_col = name_col = None
    for i, h in enumerate(header):
        hl = h.lower().replace(" ", "").replace("_", "")
        if hl in ["companynumber", "number", "regno", "companyno"]:
            num_col = i
        if hl in ["companyname", "name", "company"]:
            name_col = i
    return lines[1:], num_col, name_col

# ── UI ────────────────────────────────────────────────────────
st.markdown("""
<div class="flarex-header">
  <span class="flarex-logo"><span class="flarex-dot"></span>Flarex</span>
  <span class="tag">FX Intelligence</span>
</div>
""", unsafe_allow_html=True)

col_left, col_right = st.columns([1, 1], gap="large")

with col_left:
    st.markdown("### Upload & Configure")
    uploaded_file = st.file_uploader(
        "Companies House CSV",
        type=["csv"],
        help="Export any search from Companies House and upload it here."
    )
    api_key = st.text_input(
        "Companies House API key",
        type="password",
        placeholder="Paste your API key",
        help="Get a free key at developer.company-information.service.gov.uk"
    )
    st.caption("Your API key is used only for this scan and never stored.")

    run = st.button("Run FX Scan", disabled=not (uploaded_file and api_key))

with col_right:
    st.markdown("### How it works")
    st.markdown("""
**1. Upload** a Companies House CSV export — any sector or region filter.

**2. Flarex scans** every company's latest filed accounts (PDF or XHTML) for 31 foreign currency keywords including *hedging*, *forward contracts*, *translation risk* and more.

**3. Download** a ranked prospect list sorted by FX signal strength.
    """)

st.divider()

# ── Scan logic ────────────────────────────────────────────────
if run and uploaded_file and api_key:
    file_bytes = uploaded_file.read()
    lines, num_col, name_col = parse_csv(file_bytes)

    if num_col is None:
        st.error("Could not find a company number column in your CSV. Check the file and try again.")
        st.stop()

    total = len(lines)
    st.markdown(f"**Scanning {total} companies...**")

    progress_bar = st.progress(0)
    status_text = st.empty()
    results_container = st.container()

    results = []
    skipped = 0

    for idx, line in enumerate(lines):
        parts = re.split(r',(?![^\[]*\])', line.strip())
        if len(parts) <= max(num_col, name_col if name_col is not None else 0):
            skipped += 1
            continue

        num = pad(parts[num_col].strip().strip('"'))
        name = parts[name_col].strip().strip('"') if name_col is not None else num

        status_text.markdown(f"`[{idx+1}/{total}]` Scanning **{name}** ({num})...")

        pr = ch_get(f"/company/{num}", api_key)
        if not pr or pr.status_code != 200:
            skipped += 1
            time.sleep(0.4)
            progress_bar.progress((idx + 1) / total)
            continue

        profile = pr.json()
        status = profile.get("company_status", "unknown")
        co_name = profile.get("company_name", name)

        fh = ch_get(f"/company/{num}/filing-history?category=accounts&items_per_page=5", api_key)
        if not fh or fh.status_code != 200 or not fh.json().get("items"):
            skipped += 1
            time.sleep(0.4)
            progress_bar.progress((idx + 1) / total)
            continue

        filing = fh.json()["items"][0]
        desc = filing.get("description", "")
        meta_url = (filing.get("links") or {}).get("document_metadata")

        account_text = get_text(meta_url, api_key) if meta_url else ""
        if not account_text:
            account_text = " ".join([
                co_name, desc, filing.get("type", ""),
                " ".join(profile.get("sic_codes", []))
            ]).lower()

        matched = scan_text(account_text)

        if matched:
            results.append({
                "Company name": co_name,
                "Company number": num,
                "Status": status,
                "Accounts period": desc,
                "Matched keywords": "; ".join(matched),
                "Keyword count": len(matched),
            })
            with results_container:
                kw_preview = ", ".join(matched[:5]) + ("..." if len(matched) > 5 else "")
                st.markdown(f"""
<div class="match-card">
  <div class="match-name">{co_name}</div>
  <div class="match-meta">{num} &nbsp;·&nbsp; {status} &nbsp;·&nbsp; {desc}</div>
  <div class="match-keywords">⚡ {kw_preview}</div>
</div>
""", unsafe_allow_html=True)

        time.sleep(0.4)
        progress_bar.progress((idx + 1) / total)

    # ── Done ──────────────────────────────────────────────────
    status_text.empty()
    progress_bar.progress(1.0)

    st.success(f"Done. Scanned: {total} | Matches: {len(results)} | Skipped: {skipped}")

    if results:
        out_df = pd.DataFrame(results).sort_values("Keyword count", ascending=False)
        csv_out = out_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Download fx_prospects.csv",
            data=csv_out,
            file_name="fx_prospects.csv",
            mime="text/csv",
        )
    else:
        st.warning("No FX matches found in this batch.")
