import streamlit as st
import requests
import geopandas as gpd
import folium
from streamlit_folium import st_folium
import json
import csv
from io import StringIO
import pandas as pd
from shapely import wkt
import time

# ============================================================================
# PAGE CONFIGURATION
# ============================================================================

st.set_page_config(
    page_title="Postpass Building Overlap Detector",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================================
# SIMPLE DARK THEME CSS
# ============================================================================

st.markdown("""
<style>
    /* Simple dark theme */
    .stApp {
        background-color: #0a0a0a;
        color: white;
    }
    
    /* All text white */
    .stMarkdown, p, h1, h2, h3, h4, h5, h6 {
        color: white !important;
    }
    
    /* Sidebar */
    section[data-testid="stSidebar"] {
        background-color: #1a1a1a;
    }
    
    /* Cards */
    .info-box {
        background-color: #1a1a1a;
        padding: 1rem;
        border-radius: 10px;
        border: 1px solid #333;
        margin: 1rem 0;
    }
    
    .warning-box {
        background-color: #332100;
        padding: 1rem;
        border-radius: 10px;
        border: 1px solid #665200;
        margin: 1rem 0;
    }
    
    .success-box {
        background-color: #003300;
        padding: 1rem;
        border-radius: 10px;
        border: 1px solid #006600;
        margin: 1rem 0;
    }
    
    .error-box {
        background-color: #330000;
        padding: 1rem;
        border-radius: 10px;
        border: 1px solid #660000;
        margin: 1rem 0;
    }
    
    /* Buttons */
    .stButton > button {
        background-color: #0066cc;
        color: white;
        border: none;
        border-radius: 5px;
    }
    
    /* Inputs */
    .stTextInput > div > div > input {
        background-color: #1a1a1a;
        color: white;
        border: 1px solid #333;
    }
    
    /* Dataframe */
    .dataframe {
        background-color: #1a1a1a !important;
        color: white !important;
    }
</style>
""", unsafe_allow_html=True)

# ============================================================================
# APP TITLE
# ============================================================================

st.title("🏢 Building Overlap Detector")
st.subheader("Find overlapping buildings in OpenStreetMap data")

# ============================================================================
# SESSION STATE
# ============================================================================

if 'current_results' not in st.session_state:
    st.session_state.current_results = None

if 'bbox_input' not in st.session_state:
    st.session_state.bbox_input = "8.405,48.985,8.415,48.995"

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def parse_bbox(bbox_input):
    """Parse BBOX input"""
    try:
        bbox_clean = bbox_input.strip("[](){} ")
        bbox_parts = bbox_clean.split(",")
        
        if len(bbox_parts) != 4:
            return None, "Need 4 coordinates: west,south,east,north"
            
        west, south, east, north = [float(coord.strip()) for coord in bbox_parts]
        
        if west >= east or south >= north:
            return None, "West < East and South < North required"
            
        return (west, south, east, north), None
        
    except ValueError:
        return None, "Invalid coordinates"

def build_ultra_simple_query(west, south, east, north, limit=10):
    """Ultra simple query that won't timeout"""
    return f"""
SELECT 
    a.osm_id as id1,
    b.osm_id as id2
FROM postpass_polygon a
JOIN postpass_polygon b ON a.osm_id < b.osm_id 
WHERE a.tags ? 'building' 
AND b.tags ? 'building'
AND a.geom && ST_MakeEnvelope({west}, {south}, {east}, {north}, 4326)
AND b.geom && ST_MakeEnvelope({west}, {south}, {east}, {north}, 4326)
AND a.geom && b.geom
LIMIT {limit}
"""

def execute_query_safely(query, timeout=20):
    """Execute query with safe error handling"""
    try:
        response = requests.post(
            "https://postpass.geofabrik.de/api/0.2/interpreter",
            data={"data": query, "options[geojson]": "false"},
            timeout=timeout
        )
        return response
    except requests.exceptions.Timeout:
        return None
    except Exception as e:
        raise Exception(f"Request failed: {str(e)}")

def parse_api_response(response_text):
    """Parse API response - handles both JSON and CSV"""
    if not response_text.strip():
        return None, []
    
    # Try to parse as JSON first
    try:
        data = json.loads(response_text)
        if isinstance(data, dict) and 'result' in data:
            # JSON format with result array
            rows = data['result']
            if rows:
                # Extract headers from first row keys
                headers = list(rows[0].keys())
                data_rows = [[row.get(h, '') for h in headers] for row in rows]
                return headers, data_rows
    except json.JSONDecodeError:
        pass
    
    # Try to parse as CSV
    try:
        csv_reader = csv.reader(StringIO(response_text))
        rows = list(csv_reader)
        if rows:
            headers = rows[0]
            data_rows = rows[1:] if len(rows) > 1 else []
            return headers, data_rows
    except:
        pass
    
    return None, []

# ============================================================================
# SIDEBAR
# ============================================================================

with st.sidebar:
    st.header("⚙️ Settings")
    
    # BBOX Input
    st.subheader("📍 Search Area")
    
    bbox_input = st.text_input(
        "Enter BBOX (west,south,east,north):",
        value=st.session_state.bbox_input
    )
    st.session_state.bbox_input = bbox_input
    
    # Quick area buttons
    st.caption("Quick areas:")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Tiny", use_container_width=True):
            st.session_state.bbox_input = "8.405,48.985,8.410,48.990"
            st.rerun()
    with col2:
        if st.button("Small", use_container_width=True):
            st.session_state.bbox_input = "8.40,48.98,8.42,49.00"
            st.rerun()
    
    st.divider()
    
    # Simple settings
    st.subheader("🔧 Parameters")
    
    max_results = st.slider(
        "Max results:",
        min_value=5,
        max_value=30,
        value=10,
        step=5
    )
    
    timeout = st.slider(
        "Timeout (seconds):",
        min_value=10,
        max_value=60,
        value=20,
        step=10
    )
    
    st.divider()
    
    # Action buttons
    if st.button("🔍 Find Overlaps", type="primary", use_container_width=True):
        st.session_state.run_query = True
    
    if st.button("🧹 Clear", use_container_width=True):
        st.session_state.current_results = None
        st.rerun()

# ============================================================================
# MAIN CONTENT
# ============================================================================

# Welcome message
st.markdown('<div class="info-box">', unsafe_allow_html=True)
st.markdown("""
### How to use:
1. **Enter a small area** in the sidebar (use "Tiny" button)
2. **Click "Find Overlaps"** 
3. **View results** below

**Start with this tiny area:** `8.405,48.985,8.410,48.990`
""")
st.markdown('</div>', unsafe_allow_html=True)

# Run query
if 'run_query' in st.session_state and st.session_state.run_query and bbox_input:
    # Parse BBOX
    bbox_result, error = parse_bbox(bbox_input)
    
    if error:
        st.error(f"❌ {error}")
        st.stop()
    
    west, south, east, north = bbox_result
    
    # Show area info
    st.markdown('<div class="info-box">', unsafe_allow_html=True)
    st.markdown("### 📍 Search Area")
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("West", f"{west:.6f}")
    with col2:
        st.metric("South", f"{south:.6f}")
    with col3:
        st.metric("East", f"{east:.6f}")
    with col4:
        st.metric("North", f"{north:.6f}")
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Build ultra simple query
    query = build_ultra_simple_query(west, south, east, north, max_results)
    
    # Show query
    with st.expander("📝 View SQL Query", expanded=False):
        st.code(query, language="sql")
    
    # Execute query
    with st.spinner("Running query..."):
        start_time = time.time()
        
        try:
            response = execute_query_safely(query, timeout)
            
            if response is None:
                st.error("❌ Query timed out")
                st.info("Try using a smaller area or shorter timeout")
                st.stop()
            
            if response.status_code != 200:
                st.error(f"❌ API Error {response.status_code}")
                st.code(response.text[:300], language="text")
                st.stop()
            
            query_time = time.time() - start_time
            
            # Parse response
            headers, data_rows = parse_api_response(response.text)
            
            if headers is None or not data_rows:
                st.info("ℹ️ No overlapping buildings found")
                st.stop()
            
            # Create DataFrame
            df = pd.DataFrame(data_rows, columns=headers)
            
            # Store results
            st.session_state.current_results = {
                'dataframe': df,
                'bbox': (west, south, east, north),
                'query_time': query_time,
                'query': query
            }
            
            # Success message
            st.markdown('<div class="success-box">', unsafe_allow_html=True)
            st.success(f"✅ Found {len(df)} overlapping building pairs in {query_time:.1f}s")
            st.markdown('</div>', unsafe_allow_html=True)
            
        except Exception as e:
            st.markdown('<div class="error-box">', unsafe_allow_html=True)
            st.error(f"❌ Error: {str(e)}")
            
            # Debug info
            with st.expander("Debug info"):
                if 'response' in locals():
                    st.write("Response status:", response.status_code)
                    st.write("Response text (first 500 chars):")
                    st.code(response.text[:500], language="text")
            
            st.markdown('</div>', unsafe_allow_html=True)
    
    st.session_state.run_query = False

# Display results
if st.session_state.current_results:
    results = st.session_state.current_results
    df = results['dataframe']
    
    # Summary
    st.markdown("### 📊 Results")
    st.metric("Overlapping pairs found", len(df))
    
    # Display table
    if len(df) > 0:
        # Rename columns for better display
        df_display = df.copy()
        if 'id1' in df_display.columns:
            df_display = df_display.rename(columns={'id1': 'Building 1 ID', 'id2': 'Building 2 ID'})
        
        st.dataframe(df_display, use_container_width=True)
        
        # Export
        st.markdown("### 💾 Export")
        
        col1, col2 = st.columns(2)
        
        with col1:
            csv_data = df.to_csv(index=False)
            st.download_button(
                label="Download CSV",
                data=csv_data,
                file_name="overlaps.csv",
                mime="text/csv",
                use_container_width=True
            )
        
        with col2:
            summary = f"""Building Overlaps
Date: {time.strftime('%Y-%m-%d %H:%M')}
Area: {results['bbox']}
Pairs found: {len(df)}

Pairs:
"""
            for _, row in df.iterrows():
                summary += f"{row.get('id1', row.get('building_a_id', '?'))} - {row.get('id2', row.get('building_b_id', '?'))}\n"
            
            st.download_button(
                label="Download Summary",
                data=summary,
                file_name="summary.txt",
                mime="text/plain",
                use_container_width=True
            )
        
        # Simple map
        st.markdown("### 🗺️ Area Map")
        
        try:
            west, south, east, north = results['bbox']
            center_lat = (south + north) / 2
            center_lon = (west + east) / 2
            
            m = folium.Map(
                location=[center_lat, center_lon],
                zoom_start=16,
                width="100%",
                height=400
            )
            
            # Add bounding box
            folium.Rectangle(
                bounds=[[south, west], [north, east]],
                color='blue',
                fill=False,
                weight=2,
                tooltip="Search Area"
            ).add_to(m)
            
            st_folium(m, width=800, height=400)
            
        except:
            st.info("Map display skipped")

# ============================================================================
# FOOTER
# ============================================================================

st.divider()
st.markdown("""
<div style="text-align: center; color: #666; font-size: 0.9rem;">
    <p>Building Overlap Detector • Data: OpenStreetMap • API: Postpass</p>
</div>
""", unsafe_allow_html=True)
