import streamlit as st
import pandas as pd
import gspread
import json
import streamlit as st
from google.oauth2 import service_account
import time
import base64
import re

# ── Rate Limiting for Google Sheets API ─────────────────────────────────────
class RateLimiter:
    def __init__(self, max_calls=50, time_window=60):  # 50 calls per minute max
        self.max_calls = max_calls
        self.time_window = time_window
        self.calls = []
    
    def can_make_call(self):
        now = time.time()
        # Remove calls older than time_window
        self.calls = [call_time for call_time in self.calls if now - call_time < self.time_window]
        # Check if we're under the limit
        if len(self.calls) < self.max_calls:
            self.calls.append(now)
            return True
        return False

# Global rate limiter instance
sheets_rate_limiter = RateLimiter()

# ── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Working Camp 2025",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ── Global CSS / Hide default chrome & prevent refresh dimming ──────────────
hide_streamlit_style = """
<style>
#MainMenu, footer, header, .stDeployButton, .stToolbar {visibility: hidden; display:none;}

.main {
    padding-top:0;
    background: #000; /* solid black background */
    height:100vh;
    overflow:hidden;
}

.block-container {padding:1rem 2rem 60px 2rem; height:calc(100vh - 60px); overflow:hidden; max-width:none;}

.dashboard-header {
    background: rgba(255,255,255,0.1);
    backdrop-filter:blur(20px);
    border-radius:20px;
    padding:20px 30px;
    margin-bottom:20px;
    border:1px solid rgba(255,255,255,0.2);
    display:flex;
    justify-content:space-between;
    align-items:center;
}

.header-left {display:flex;align-items:center;gap:25px;}
.logo-img {width:60px;height:60px;border-radius:15px;object-fit:cover;border:2px solid rgba(255,255,255,0.3);}
.title-section h1 {color:#fff;font-size:32px;font-weight:800;margin:0;text-shadow:0 2px 4px rgba(0,0,0,0.3);}
.live-status {background:rgba(255,255,255,0.15);padding:10px 20px;border-radius:25px;color:#fff;font-weight:600;border:1px solid rgba(255,255,255,0.2);font-size:14px;}
.status-dot {width:8px;height:8px;background:#00ff88;border-radius:50%;display:inline-block;margin-right:8px;animation:pulse 2s infinite;}
@keyframes pulse {0%,100%{opacity:1;}50%{opacity:0.7;}}

div[data-testid="stVerticalBlock"] > div {gap:0.5rem;}

/* Prevent screen dimming during refresh */
.stSpinner > div {display: none !important;}
div[data-testid="stStatusWidget"] {display: none !important;}
.stAlert > div[kind="info"] {display: none !important;}
section[data-testid="stSidebar"] {display: none !important;}
.stProgress {display: none !important;}
.streamlit-container .element-container .stMarkdown .stAlert {display: none !important;}
div[class*="stConnectionStatus"] {display: none !important;}
div[data-testid="stConnectionStatus"] {display: none !important;}

/* Hide any loading overlays */
div[data-testid="stApp"] > div[class*="main"] > div[class*="appview-container"] > section > div[class*="block-container"] > div > div > div[class*="stMarkdown"] div[class*="stAlert"] {display: none !important;}
.stApp > .main .block-container .element-container .stAlert {display: none !important;}

/* Smooth transitions instead of jarring refreshes */
.main .block-container {
    transition: opacity 0.1s ease-in-out;
}
</style>"""

st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# DATA FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════
@st.cache_resource
def get_google_client():
    """Create a gspread client using service account info stored in st.secrets.

    The secrets should include GOOGLE_SERVICE_ACCOUNT_JSON (the full JSON blob)
    and GOOGLE_SHEET_ID. This avoids keeping service_account.json on disk.
    """
    try:
        sa_json = st.secrets.get("GOOGLE_SERVICE_ACCOUNT_JSON")
        if not sa_json:
            raise RuntimeError("Missing GOOGLE_SERVICE_ACCOUNT_JSON in st.secrets")

        service_account_info = json.loads(sa_json)
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = service_account.Credentials.from_service_account_info(service_account_info, scopes=scopes)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Failed to connect to Google Sheets: {str(e)}")
        return None

@st.cache_data(ttl=8)  # Cache for 8 seconds to reduce API calls
def get_data(nonce: int | None = None):  # nonce param forces refetch when desired
    try:
        # Check rate limiting first
        if not sheets_rate_limiter.can_make_call():
            st.warning("⏱️ Rate limit reached. Using cached data...")
            # Return cached data if available
            if 'last_good_data' in st.session_state:
                return st.session_state.last_good_data
            return pd.DataFrame()
        
        gc = get_google_client()
        if not gc:
            return pd.DataFrame()
            
        # Read sheet id and worksheet name from secrets so we don't store credentials on disk
        sheet_id = st.secrets.get("GOOGLE_SHEET_ID")
        sheet_name = st.secrets.get("SHEET_NAME", "Counts")
        if not sheet_id:
            raise RuntimeError("Missing GOOGLE_SHEET_ID in st.secrets")

        spreadsheet = gc.open_by_key(sheet_id)
        sheet = spreadsheet.worksheet(sheet_name)
        
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        
        if df.empty:
            return df
            
        # Clean and validate data
        required_columns = ['Code', 'Item', 'Count', 'Target']
        for col in required_columns:
            if col not in df.columns:
                df[col] = 0 if col in ['Count', 'Target'] else ''
        
        # Convert to proper types
        df['Count'] = pd.to_numeric(df['Count'], errors='coerce').fillna(0).astype(int)
        df['Target'] = pd.to_numeric(df['Target'], errors='coerce').fillna(1).astype(int)
        
        # Remove empty rows
        df = df[df['Item'].astype(str).str.strip() != '']
        
        # Cache successful data
        st.session_state.last_good_data = df
        
        return df
        
    except Exception as e:
        error_msg = str(e)
        if "429" in error_msg or "Quota exceeded" in error_msg:
            st.error("🚫 Google Sheets API quota exceeded. Please wait a moment...")
            # Return cached data if available
            if 'last_good_data' in st.session_state:
                st.info("📊 Showing cached data...")
                return st.session_state.last_good_data
        else:
            st.error(f"Error loading data: {error_msg}")
        return pd.DataFrame()

def get_base64_image(image_path):
    try:
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode()
    except:
        return None

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════

## NOTE: Partial front-end only updates without rerunning the Streamlit script
## require a separate backend endpoint or a custom component. For now we use
## Streamlit's native rerun (st.autorefresh) which re-executes Python but does
## NOT hard-reload the browser, giving a stable layout with updated numbers.

## Streamlit's native rerun (st.autorefresh) which re-executes Python but does
## NOT hard-reload the browser, giving a stable layout with updated numbers.

# Force fresh data (no cache) with timestamp nonce
nonce = int(time.time())
df = get_data(nonce)

if df.empty:
    st.markdown("""
    <div style='text-align: center; padding: 100px; color: white;'>
        <h2>Loading Working Camp 2025 Data...</h2>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# Get logo
logo_b64 = get_base64_image("Logo.jpg")

# Generate logo HTML
logo_html = f'<img src="data:image/jpeg;base64,{logo_b64}" class="logo-img">' if logo_b64 else '<div style="width:50px;height:50px;background:#ddd;border-radius:12px;"></div>'

# Header Section
logo_html = f'<img src="data:image/jpeg;base64,{logo_b64}" class="logo-img">' if logo_b64 else '<div style="width:60px;height:60px;background:#ddd;border-radius:12px;"></div>'

st.markdown(f"""
<div class="dashboard-header">
    <div class="header-left">
        {logo_html}
        <div class="title-section">
            <h1>Working Camp 2025</h1>
        </div>
    </div>
    <div class="live-status">
        <span class="status-dot"></span>
        LIVE • {time.strftime('%H:%M:%S')}
    </div>
</div>
""", unsafe_allow_html=True)

# (Layout distribution logic – internal comment removed from UI)
items = df.to_dict(orient="records")
num_items = len(items)

# Mapping for up to 18 items (extendable) focusing on visually pleasing symmetry.
distribution_map = {
    1:[1],2:[2],3:[3],4:[4],5:[3,2],6:[3,3],7:[3,4],8:[4,4],9:[5,4],
    10:[3,3,4],11:[3,4,4],12:[4,4,4],13:[4,5,4],14:[5,5,4],15:[5,5,5],
    16:[4,4,4,4],17:[4,4,5,4],18:[4,5,5,4]
}

if num_items in distribution_map:
    row_distribution = distribution_map[num_items]
else:
    # Generic fallback: pack rows of 5
    full_rows, remainder = divmod(num_items, 5)
    row_distribution = [5]*full_rows + ([remainder] if remainder else [])

num_rows = len(row_distribution)

HEADER_PX = 120  # Increased header space for bigger elements
ROW_GAP_PX = 20   # Increased spacing between rows
CARD_GAP_PX = 18  # Increased spacing between cards
FUDGE_PX = 50     # general bottom fudge used previously
BOTTOM_SPACE_PX = 60  # extra visible spacing from bottom of viewport
# Reserve BOTTOM_SPACE_PX in the height calculation so rows don't stretch to very bottom
row_height_css = f"calc((100vh - {HEADER_PX + FUDGE_PX + BOTTOM_SPACE_PX}px - {(num_rows - 1) * ROW_GAP_PX}px) / {num_rows})"

# Build HTML grid manually for precise control with bigger, centered design
cards_html_parts = [
    "<style>\n"
    " .wc-rows {display:flex;flex-direction:column;gap:%dpx;height:calc(100vh - %dpx);padding-bottom:20px;}" % (ROW_GAP_PX, HEADER_PX + FUDGE_PX + BOTTOM_SPACE_PX),
    " .wc-row {display:flex;justify-content:center;gap:%dpx;height:%s;padding:0 6px;}" % (CARD_GAP_PX, row_height_css),
    " .wc-card {"
    "   background: rgba(255,255,255,0.94);"
    "   border: 2px solid rgba(255,255,255,0.32);"
    "   border-radius: 25px;"
    "   padding: 25px 30px 20px 30px;"
    "   display: flex;"
    "   flex-direction: column;"
    "   justify-content: space-between;"
    "   box-shadow: 0 8px 32px -8px rgba(0,0,0,0.3);"
    "   transition: transform .3s ease, box-shadow .3s ease;"
    " }"
    " .wc-card:hover {"
    "   transform: translateY(-8px);"
    "   box-shadow: 0 15px 45px -5px rgba(0,0,0,0.4);"
    " }"
    " .wc-top {"
    "   display: flex;"
    "   justify-content: flex-end;"
    "   align-items: center;"
    "   margin-bottom: 8px;"
    " }"
    " .wc-name {"
    "   font-size: 22px;"
    "   font-weight: 800;"
    "   color: #0d1114;"
    "   line-height: 1.2;"
    "   margin: 8px 0 20px;"
    "   min-height: 45px;"
    "   text-align: center;"
    "   display: flex;"
    "   align-items: center;"
    "   justify-content: center;"
    " }"
    " .wc-count {"
    "   text-align: center;"
    "   margin-bottom: 20px;"
    " }"
    " .wc-count-main {"
    "   font-size: 48px;"
    "   font-weight: 900;"
    "   color: #0d1114;"
    "   line-height: 1;"
    " }"
    " .wc-sub {"
    "   font-size: 16px;"
    "   color: #68727a;"
    "   font-weight: 600;"
    "   margin-top: 8px;"
    " }"
    " .wc-bar-wrap {"
    "   background: #e2e8f0;"
    "   border-radius: 12px;"
    "   height: 14px;"
    "   overflow: hidden;"
    "   margin: 4px 0 15px;"
    " }"
    " .wc-status {"
    "   text-align: center;"
    "   font-weight: 700;"
    "   font-size: 16px;"
    " }"
    " .wc-stage {"
    "   text-align: center;"
    "   margin-top: 8px;"
    "   font-size: 12px;"
    "   color: #68727a;"
    "   text-transform: uppercase;"
    "   letter-spacing: 0.8px;"
    "   font-weight: 600;"
    " }"
    " </style>"
]

index = 0
for row_size in row_distribution:
    # Width per card minus gaps: (100% - totalGap)/row_size
    card_width_css = f"calc((100% - {(row_size - 1) * CARD_GAP_PX}px) / {row_size})"
    cards_html_parts.append(f"<div class='wc-row'>")
    for i in range(row_size):
        if index >= num_items:
            break
        item_data = items[index]
        index += 1
        # code intentionally hidden
        name = str(item_data.get('Item', 'Unnamed Item')).strip()
        count = int(item_data.get('Count', 0))
        target = int(item_data.get('Target', 1)) or 1
        pct = min((count / target) * 100, 100)
        slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-') or 'item'
        # Logical green color progression based on completion percentage
        if pct >= 100:
            status_color = "#296815"; stage = "Completed"  # Bright green - success
        elif pct >= 80:
            status_color = "#4B8C30"; stage = "Nearly Done"  # Lime green - almost there
        elif pct >= 50:
            status_color = "#6EAA4D"; stage = "Good Progress"  # Light green - good progress
        elif pct >= 25:
            status_color = "#A4CC8B"; stage = "Getting Started"  # Gray - minimal progress
        else:
            status_color = "#93AD8B"; stage = "Not Started"  # Dark gray - no progress
        bar_html = (
            f"<div class='wc-bar-wrap'><div id='bar-{slug}' style=\"height:100%;width:{pct:.2f}%;background:{status_color};border-radius:10px;transition:width .8s ease\"></div></div>"
        )
        cards_html_parts.append(
            f"<div class='wc-card' style='width:{card_width_css}'>"
                f"<div class='wc-top'><div style='width:16px;height:16px;border-radius:50%;background:#16a34a;box-shadow:0 0 0 4px rgba(0,0,0,0.05)'></div></div>"
                f"<div class='wc-name'>{name}</div>"
                f"<div class='wc-count'><div id='count-{slug}' class='wc-count-main'>{count:,}</div><div class='wc-sub'>of <span id='target-{slug}'>{target:,}</span></div></div>"
                f"{bar_html}"
                f"<div id='pct-{slug}' class='wc-status' style='color:{status_color}'>{pct:.1f}% Complete</div>"
                f"<div id='stage-{slug}' class='wc-stage'>{stage}</div>"
                f"</div>"
        )
    cards_html_parts.append("</div>")

full_grid_html = "".join(cards_html_parts)
st.markdown(f"<div class='wc-rows' id='wc-root'>{full_grid_html}</div>", unsafe_allow_html=True)

REFRESH_INTERVAL_SEC = 10  # 10 seconds to avoid API quota limits

# Use Streamlit's built-in auto-refresh mechanism
from streamlit_autorefresh import st_autorefresh

# Auto-refresh every 10 seconds to respect Google API quotas
refresh_count = st_autorefresh(interval=REFRESH_INTERVAL_SEC * 1000, key="data_refresh")

# JavaScript to prevent any loading overlays or dimming effects
st.markdown("""
<script>
// Remove any loading states or overlays that might appear
function hideLoadingElements() {
    const elementsToHide = [
        'div[data-testid="stSpinner"]',
        'div[data-testid="stStatusWidget"]', 
        'div[class*="stConnectionStatus"]',
        'div[data-testid="stConnectionStatus"]',
        '.stProgress',
        '.stAlert[kind="info"]'
    ];
    
    elementsToHide.forEach(selector => {
        const elements = document.querySelectorAll(selector);
        elements.forEach(el => {
            if (el) el.style.display = 'none';
        });
    });
}

// Run immediately and set up observer for dynamic content
hideLoadingElements();

// Watch for new elements being added to the DOM
const observer = new MutationObserver(() => {
    hideLoadingElements();
});

observer.observe(document.body, {
    childList: true,
    subtree: true
});

// Also hide on page load and refresh
document.addEventListener('DOMContentLoaded', hideLoadingElements);
window.addEventListener('load', hideLoadingElements);
</script>
""", unsafe_allow_html=True)