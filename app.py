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
# CUSTOM CSS - DARK THEME WITH HIGH CONTRAST
# ============================================================================

st.markdown("""
<style>
    /* Dark theme with high contrast */
    .stApp {
        background-color: #0f172a;
        color: #ffffff;
    }
    
    /* Make all text white */
    .stMarkdown, .stText, p, h1, h2, h3, h4, h5, h6, span, div, label {
        color: #ffffff !important;
    }
    
    /* Sidebar - slightly lighter dark */
    section[data-testid="stSidebar"] {
        background-color: #1e293b;
    }
    
    /* Headers with accent color */
    .main-title {
        font-size: 2.5rem;
        color: #60a5fa !important;
        font-weight: 700;
        margin-bottom: 1rem;
        text-align: center;
    }
    
    .section-title {
        font-size: 1.8rem;
        color: #93c5fd !important;
        font-weight: 600;
        margin-top: 2rem;
        margin-bottom: 1rem;
        padding-bottom: 0.5rem;
        border-bottom: 2px solid #60a5fa;
    }
    
    /* Cards with dark backgrounds */
    .info-card {
        background-color: #1e293b;
        padding: 1.5rem;
        border-radius: 10px;
        margin: 1rem 0;
        border-left: 5px solid #3b82f6;
        border: 1px solid #334155;
    }
    
    .warning-card {
        background-color: #451a03;
        padding: 1.5rem;
        border-radius: 10px;
        margin: 1rem 0;
        border-left: 5px solid #f59e0b;
        border: 1px solid #7c2d12;
    }
    
    .success-card {
        background-color: #064e3b;
        padding: 1.5rem;
        border-radius: 10px;
        margin: 1rem 0;
        border-left: 5px solid #10b981;
        border: 1px solid #065f46;
    }
    
    .error-card {
        background-color: #7f1d1d;
        padding: 1.5rem;
        border-radius: 10px;
        margin: 1rem 0;
        border-left: 5px solid #ef4444;
        border: 1px solid #991b1b;
    }
    
    /* Buttons */
    .stButton > button {
        background-color: #3b82f6;
        color: white !important;
        font-weight: 600;
        border: none;
        border-radius: 8px;
        padding: 0.75rem 1.5rem;
        font-size: 1rem;
    }
    
    .stButton > button:hover {
        background-color: #2563eb;
    }
    
    /* Input fields */
    .stTextInput > div > div > input {
        background-color: #1e293b !important;
        color: white !important;
        border: 1px solid #475569 !important;
    }
    
    .stNumberInput > div > div > input {
        background-color: #1e293b !important;
        color: white !important;
        border: 1px solid #475569 !important;
    }
    
    /* Sliders */
    .stSlider > div > div > div {
        color: white !important;
    }
    
    /* Dataframes */
    .dataframe {
        background-color: #1e293b !important;
        color: white !important;
        border: 1px solid #475569 !important;
    }
    
    .dataframe th {
        background-color: #334155 !important;
        color: white !important;
    }
    
    .dataframe td {
        background-color: #1e293b !important;
        color: white !important;
    }
    
    /* Code blocks */
    .stCodeBlock {
        background-color: #1e293b !important;
        border: 1px solid #475569 !important;
        color: #e2e8f0 !important;
    }
    
    /* Metrics */
    .stMetric {
        background-color: #1e293b;
        padding: 1rem;
        border-radius: 8px;
        border: 1px solid #475569;
    }
    
    .stMetric label {
        color: #93c5fd !important;
    }
    
    .stMetric div {
        color: white !important;
    }
    
    /* Expander */
    .streamlit-expanderHeader {
        background-color: #1e293b !important;
        color: white !important;
        border: 1px solid #475569 !important;
    }
    
    /* Selectbox */
    .stSelectbox > div > div {
        background-color: #1e293b !important;
        color: white !important;
        border: 1px solid #475569 !important;
    }
    
    /* Links */
    a {
        color: #60a5fa !important;
    }
    
    /* Footer */
    .footer {
        text-align: center;
        color: #94a3b8 !important;
        padding: 2rem 0;
        border-top: 1px solid #334155;
        margin-top: 2rem;
    }
</style>
""", unsafe_allow_html=True)

# ============================================================================
# APP TITLE
# ============================================================================

st.markdown('<h1 class="main-title">🏢 Postpass Building Overlap Detector</h1>', unsafe_allow_html=True)
st.markdown("### Find overlapping buildings in OpenStreetMap data")

# ============================================================================
# SESSION STATE
# ============================================================================

if 'current_results' not in st.session_state:
    st.session_state.current_results = None

if 'bbox_input' not in st.session_state:
    st.session_state.bbox_input = "8.40,48.98,8.42,49.00"  # Smaller default area

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def build_fast_overlap_query(west, south, east, north, min_overlap=1.0, limit=20):
    """Build optimized query that won't timeout"""
    return f"""
WITH buildings_in_bbox AS (
    SELECT osm_id, osm_type, geom, tags
    FROM postpass_polygon 
    WHERE tags ? 'building'
    AND geom && ST_MakeEnvelope({west}, {south}, {east}, {north}, 4326)
    LIMIT 500  -- Limit buildings to prevent massive joins
),
building_pairs AS (
    SELECT 
        a.osm_id as building_a_id,
        b.osm_id as building_b_id,
        a.geom as geom_a,
        b.geom as geom_b
    FROM buildings_in_bbox a
    JOIN buildings_in_bbox b 
    ON a.osm_id < b.osm_id 
    AND a.geom && b.geom  -- Fast bounding box check first
)
SELECT 
    building_a_id,
    building_b_id,
    ROUND(ST_Area(ST_Intersection(geom_a, geom_b)::geography)::numeric, 2) as overlap_area_m2,
    ST_AsText(ST_Centroid(ST_Intersection(geom_a, geom_b))) as centroid_wkt
FROM building_pairs
WHERE ST_Area(ST_Intersection(geom_a, geom_b)::geography) > {min_overlap}
ORDER BY overlap_area_m2 DESC
LIMIT {limit}
"""

def build_simple_count_query(west, south, east, north):
    """First check how many buildings are in the area"""
    return f"""
SELECT COUNT(*) as building_count
FROM postpass_polygon 
WHERE tags ? 'building'
AND geom && ST_MakeEnvelope({west}, {south}, {east}, {north}, 4326)
"""

def build_fast_simple_query(west, south, east, north, limit=20):
    """Simplest possible query - just find buildings that overlap"""
    return f"""
SELECT 
    a.osm_id as building_a_id,
    b.osm_id as building_b_id
FROM postpass_polygon a
JOIN postpass_polygon b 
ON a.osm_id < b.osm_id 
AND a.geom && b.geom
WHERE 
    a.tags ? 'building' 
    AND b.tags ? 'building'
    AND a.geom && ST_MakeEnvelope({west}, {south}, {east}, {north}, 4326)
    AND b.geom && ST_MakeEnvelope({west}, {south}, {east}, {north}, 4326)
LIMIT {limit}
"""

def execute_query_with_retry(query, timeout=30, max_retries=2):
    """Execute query with retry logic"""
    for attempt in range(max_retries):
        try:
            post_data = {
                "data": query,
                "options[geojson]": "false"
            }
            
            response = requests.post(
                "https://postpass.geofabrik.de/api/0.2/interpreter",
                data=post_data,
                timeout=timeout
            )
            return response
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                st.warning(f"Attempt {attempt + 1} timed out, retrying...")
                time.sleep(2)
            else:
                raise Exception(f"Query timed out after {max_retries} attempts")
    return None

# ============================================================================
# SIDEBAR
# ============================================================================

with st.sidebar:
    st.markdown("## ⚙️ Settings")
    st.markdown("---")
    
    # BBOX Input
    st.markdown("### 📍 Search Area")
    
    bbox_input = st.text_input(
        "Enter BBOX (west,south,east,north):",
        value=st.session_state.bbox_input,
        help="Start with a small area like: 8.40,48.98,8.42,49.00"
    )
    st.session_state.bbox_input = bbox_input
    
    # Quick buttons for different area sizes
    st.caption("Quick area selection:")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Tiny", use_container_width=True):
            st.session_state.bbox_input = "8.405,48.985,8.415,48.995"
            st.rerun()
    with col2:
        if st.button("Small", use_container_width=True):
            st.session_state.bbox_input = "8.40,48.98,8.42,49.00"
            st.rerun()
    with col3:
        if st.button("Medium", use_container_width=True):
            st.session_state.bbox_input = "8.38,48.96,8.44,49.02"
            st.rerun()
    
    st.markdown("---")
    
    # Analysis Settings
    st.markdown("### 🔧 Analysis Parameters")
    
    # Use VERY conservative defaults
    min_overlap = st.number_input(
        "Minimum overlap (m²):",
        min_value=0.1,
        max_value=100.0,
        value=0.5,
        step=0.1,
        help="Start with 0.5 m²"
    )
    
    max_results = st.number_input(
        "Maximum results:",
        min_value=5,
        max_value=50,
        value=15,
        step=5,
        help="Keep this low (15-20)"
    )
    
    timeout = st.slider(
        "Timeout (seconds):",
        min_value=15,
        max_value=90,
        value=30,
        step=15,
        help="Shorter timeouts are better"
    )
    
    st.markdown("---")
    
    # Query Strategy
    st.markdown("### 🚀 Query Strategy")
    query_strategy = st.radio(
        "Choose query type:",
        ["Fast & Simple", "Detailed Overlap"],
        index=0,
        help="'Fast & Simple' is recommended to avoid timeouts"
    )
    
    st.markdown("---")
    
    # Action Buttons
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔍 Find Overlaps", type="primary", use_container_width=True):
            st.session_state.run_query = True
    with col2:
        if st.button("🧹 Clear", use_container_width=True):
            st.session_state.current_results = None
            st.rerun()

# ============================================================================
# MAIN CONTENT
# ============================================================================

# Welcome message
st.markdown('<div class="info-card">', unsafe_allow_html=True)
st.markdown("""
### Welcome to the Building Overlap Detector

This tool identifies overlapping buildings in OpenStreetMap data. Overlaps often indicate mapping errors that need correction.

**For best results:**
1. **Start with a TINY area** (use the "Tiny" button)
2. **Use 'Fast & Simple' query strategy**
3. **Keep max results low** (15-20)
4. **Use short timeout** (30 seconds)

**Example tiny area:** `8.405,48.985,8.415,48.995`
""")
st.markdown('</div>', unsafe_allow_html=True)

# Run query if requested
if 'run_query' in st.session_state and st.session_state.run_query and bbox_input:
    # Parse BBOX
    try:
        bbox_clean = bbox_input.strip("[](){} ")
        bbox_parts = bbox_clean.split(",")
        
        if len(bbox_parts) != 4:
            st.error("❌ Please enter exactly 4 coordinates: west, south, east, north")
            st.stop()
            
        west, south, east, north = [float(coord.strip()) for coord in bbox_parts]
        
        # Validate
        if west >= east or south >= north:
            st.error("❌ West must be < East and South must be < North")
            st.stop()
            
    except ValueError:
        st.error("❌ Please enter valid numeric coordinates")
        st.stop()
    
    # Display area info
    st.markdown('<div class="info-card">', unsafe_allow_html=True)
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
    
    # Calculate approximate area
    area_km2 = abs(east - west) * abs(north - south) * 111 * 111  # rough approximation
    st.info(f"Approximate area: {area_km2:.2f} km²")
    st.markdown('</div>', unsafe_allow_html=True)
    
    # First, check how many buildings are in the area
    with st.spinner("🔍 Checking building count in area..."):
        try:
            count_query = build_simple_count_query(west, south, east, north)
            count_response = execute_query_with_retry(count_query, timeout=15)
            
            if count_response and count_response.status_code == 200:
                csv_data = list(csv.reader(StringIO(count_response.text)))
                if csv_data and len(csv_data) > 1:
                    building_count = int(csv_data[1][0]) if len(csv_data[1]) > 0 else 0
                    st.info(f"Found {building_count} buildings in the area")
                    
                    if building_count > 1000:
                        st.warning(f"⚠️ Large area detected ({building_count} buildings). Using simple query strategy.")
                        query_strategy = "Fast & Simple"
            
        except Exception as e:
            st.warning(f"Could not get building count: {str(e)[:100]}")
    
    # Build appropriate query
    if query_strategy == "Fast & Simple":
        query = build_fast_simple_query(west, south, east, north, max_results)
        query_type = "simple"
    else:
        query = build_fast_overlap_query(west, south, east, north, min_overlap, max_results)
        query_type = "detailed"
    
    # Show query
    with st.expander("📝 View SQL Query", expanded=False):
        st.code(query, language="sql")
    
    # Execute main query
    with st.spinner("🔍 Running query... This may take a moment"):
        start_time = time.time()
        
        try:
            response = execute_query_with_retry(query, timeout=timeout)
            query_time = time.time() - start_time
            
            if response is None:
                st.error("❌ No response received from API")
                st.stop()
            
            if response.status_code != 200:
                st.markdown('<div class="error-card">', unsafe_allow_html=True)
                st.error(f"❌ API Error {response.status_code}")
                if response.text:
                    st.code(response.text[:300], language="text")
                st.markdown('</div>', unsafe_allow_html=True)
                st.stop()
            
            # Parse response
            content = response.text.strip()
            if not content:
                st.warning("⚠️ No data returned from query")
                st.stop()
            
            csv_reader = csv.reader(StringIO(content))
            rows = list(csv_reader)
            
            if not rows or len(rows) <= 1:
                st.info("ℹ️ No overlapping buildings found in this area")
                st.stop()
            
            headers = rows[0]
            data_rows = rows[1:] if len(rows) > 1 else []
            
            # Create DataFrame
            df = pd.DataFrame(data_rows, columns=headers)
            
            # Store results
            st.session_state.current_results = {
                'dataframe': df,
                'bbox': (west, south, east, north),
                'query_time': query_time,
                'query_type': query_type,
                'query': query
            }
            
            # Display success
            st.markdown('<div class="success-card">', unsafe_allow_html=True)
            st.success(f"✅ Found {len(df)} results in {query_time:.1f} seconds")
            st.markdown('</div>', unsafe_allow_html=True)
            
        except Exception as e:
            st.markdown('<div class="error-card">', unsafe_allow_html=True)
            error_msg = str(e)
            st.error(f"❌ Error: {error_msg}")
            
            # Helpful suggestions
            st.markdown("""
            **Troubleshooting tips:**
            
            1. **Use a smaller area** - click "Tiny" button in sidebar
            2. **Switch to 'Fast & Simple'** query strategy
            3. **Reduce max results** to 10-15
            4. **Try a different location** 
            5. **Check if Postpass API is online:**
            """)
            
            # Quick API check
            try:
                test_response = requests.get("https://postpass.geofabrik.de/", timeout=5)
                if test_response.status_code == 200:
                    st.info("✅ Postpass website is accessible")
                else:
                    st.warning("⚠️ Postpass website may be having issues")
            except:
                st.warning("⚠️ Cannot reach Postpass server")
            
            st.markdown('</div>', unsafe_allow_html=True)
    
    # Clear the flag
    st.session_state.run_query = False

# Display results if available
if st.session_state.current_results:
    results = st.session_state.current_results
    df = results['dataframe']
    
    # Summary
    st.markdown("### 📊 Results Summary")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Pairs Found", len(df))
    with col2:
        st.metric("Query Time", f"{results['query_time']:.1f}s")
    with col3:
        st.metric("Query Type", results['query_type'])
    
    # Data Table
    st.markdown("### 📋 Overlapping Building Pairs")
    
    if len(df) > 0:
        # Clean up column names for display
        display_df = df.copy()
        
        # Rename columns for better readability
        column_renames = {
            'building_a_id': 'Building A ID',
            'building_b_id': 'Building B ID',
            'overlap_area_m2': 'Overlap Area (m²)',
            'centroid_wkt': 'Centroid Location'
        }
        
        display_df = display_df.rename(columns={k: v for k, v in column_renames.items() if k in display_df.columns})
        
        st.dataframe(display_df, use_container_width=True, height=300)
        
        # Export options
        st.markdown("### 💾 Export Data")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # CSV Export
            csv_data = df.to_csv(index=False)
            st.download_button(
                label="📥 Download CSV",
                data=csv_data,
                file_name=f"overlaps_{time.strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True
            )
        
        with col2:
            # Summary text
            summary = f"""Building Overlap Analysis
Date: {time.strftime('%Y-%m-%d %H:%M:%S')}
Area: {results['bbox']}
Query Type: {results['query_type']}
Pairs Found: {len(df)}
Query Time: {results['query_time']:.1f}s

Building Pairs:
"""
            for idx, row in df.iterrows():
                summary += f"{row.get('building_a_id', 'N/A')} - {row.get('building_b_id', 'N/A')}"
                if 'overlap_area_m2' in row:
                    summary += f" (Overlap: {row['overlap_area_m2']} m²)"
                summary += "\n"
            
            st.download_button(
                label="📄 Download Summary",
                data=summary,
                file_name=f"summary_{time.strftime('%Y%m%d_%H%M%S')}.txt",
                mime="text/plain",
                use_container_width=True
            )
        
        # Simple map if we have coordinates
        st.markdown("### 🗺️ Map View")
        
        try:
            west, south, east, north = results['bbox']
            center_lat = (south + north) / 2
            center_lon = (west + east) / 2
            
            m = folium.Map(
                location=[center_lat, center_lon],
                zoom_start=15,
                tiles="OpenStreetMap",
                width="100%",
                height=400
            )
            
            # Add bounding box
            folium.Rectangle(
                bounds=[[south, west], [north, east]],
                color='blue',
                fill=False,
                weight=2,
                opacity=0.5,
                tooltip="Search Area"
            ).add_to(m)
            
            # Add markers for building pairs if we have centroids
            if 'centroid_wkt' in df.columns:
                for idx, row in df.iterrows():
                    try:
                        centroid = row['centroid_wkt']
                        if pd.notna(centroid) and centroid:
                            # Parse WKT POINT(x y)
                            centroid = centroid.replace('POINT(', '').replace(')', '')
                            lon, lat = map(float, centroid.split())
                            
                            folium.CircleMarker(
                                location=[lat, lon],
                                radius=5,
                                color='red',
                                fill=True,
                                popup=f"Buildings: {row.get('building_a_id', '?')} & {row.get('building_b_id', '?')}"
                            ).add_to(m)
                    except:
                        continue
            
            st_folium(m, width=800, height=400)
            
        except Exception as e:
            st.info("Map could not be displayed. Showing results in table only.")
    else:
        st.info("No data to display.")

# ============================================================================
# FOOTER
# ============================================================================

st.markdown("""
<div class="footer">
    <p><b>Postpass Building Overlap Detector</b></p>
    <p>Data source: OpenStreetMap • API: Postpass</p>
    <p>Tip: For reliable results, use very small areas (under 0.5 km²)</p>
</div>
""", unsafe_allow_html=True)
