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
import math

# ============================================================================
# PAGE CONFIGURATION
# ============================================================================

st.set_page_config(
    page_title="Postpass Explorer - OSM Spatial Analysis",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================================
# CUSTOM CSS FOR BETTER READABILITY
# ============================================================================

st.markdown("""
<style>
    /* Light theme with better contrast */
    .stApp {
        background-color: #f8f9fa;
    }
    
    /* Main headers */
    .main-title {
        font-size: 2.5rem;
        color: #1a3c6e;
        font-weight: 700;
        margin-bottom: 1rem;
        text-align: center;
    }
    
    .section-title {
        font-size: 1.8rem;
        color: #2c5282;
        font-weight: 600;
        margin-top: 2rem;
        margin-bottom: 1rem;
        padding-bottom: 0.5rem;
        border-bottom: 2px solid #4299e1;
    }
    
    /* Cards and containers */
    .info-card {
        background-color: white;
        padding: 1.5rem;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        margin: 1rem 0;
        border-left: 4px solid #4299e1;
    }
    
    .warning-card {
        background-color: #fffaf0;
        padding: 1.5rem;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        margin: 1rem 0;
        border-left: 4px solid #ed8936;
    }
    
    .success-card {
        background-color: #f0fff4;
        padding: 1.5rem;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        margin: 1rem 0;
        border-left: 4px solid #48bb78;
    }
    
    /* Metric cards */
    .metric-container {
        display: flex;
        justify-content: space-between;
        gap: 1rem;
        margin: 1rem 0;
    }
    
    .metric-box {
        background: linear-gradient(135deg, #4c51bf 0%, #667eea 100%);
        padding: 1.2rem;
        border-radius: 10px;
        color: white;
        flex: 1;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    
    .metric-title {
        font-size: 0.9rem;
        opacity: 0.9;
        margin-bottom: 0.5rem;
    }
    
    .metric-value {
        font-size: 1.8rem;
        font-weight: 700;
        margin: 0.5rem 0;
    }
    
    .metric-unit {
        font-size: 0.8rem;
        opacity: 0.8;
    }
    
    /* Buttons */
    .stButton > button {
        background-color: #4299e1;
        color: white;
        font-weight: 600;
        border: none;
        border-radius: 8px;
        padding: 0.75rem 1.5rem;
        font-size: 1rem;
        transition: all 0.3s ease;
    }
    
    .stButton > button:hover {
        background-color: #3182ce;
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(66, 153, 225, 0.3);
    }
    
    .primary-button {
        background-color: #2b6cb0 !important;
    }
    
    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 1rem;
        background-color: white;
        padding: 0.5rem;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    }
    
    .stTabs [data-baseweb="tab"] {
        height: 45px;
        background-color: #e2e8f0;
        border-radius: 8px;
        padding: 0.5rem 1.5rem;
        font-weight: 600;
        color: #4a5568;
        transition: all 0.3s ease;
    }
    
    .stTabs [data-baseweb="tab"]:hover {
        background-color: #cbd5e0;
    }
    
    .stTabs [aria-selected="true"] {
        background-color: #4299e1 !important;
        color: white !important;
    }
    
    /* Text areas and inputs */
    .stTextArea textarea {
        font-family: 'Monaco', 'Courier New', monospace;
        font-size: 14px;
        background-color: #f7fafc;
    }
    
    /* Dataframes */
    .dataframe {
        background-color: white;
        border-radius: 10px;
        overflow: hidden;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    }
    
    /* Code blocks */
    .stCodeBlock {
        background-color: #f7fafc;
        border-radius: 8px;
        border: 1px solid #e2e8f0;
        padding: 1rem;
    }
    
    /* Sidebar */
    .css-1d391kg {
        background-color: #2d3748;
    }
    
    /* Links */
    a {
        color: #4299e1;
        text-decoration: none;
    }
    
    a:hover {
        color: #3182ce;
        text-decoration: underline;
    }
    
    /* Tables */
    table {
        background-color: white;
        border-radius: 8px;
        overflow: hidden;
    }
    
    th {
        background-color: #edf2f7 !important;
        color: #2d3748 !important;
        font-weight: 600 !important;
    }
    
    /* Custom alerts */
    .custom-alert {
        padding: 1rem;
        border-radius: 8px;
        margin: 1rem 0;
        border-left: 4px solid;
    }
    
    .alert-info {
        background-color: #ebf8ff;
        border-color: #4299e1;
    }
    
    .alert-warning {
        background-color: #fffaf0;
        border-color: #ed8936;
    }
    
    .alert-success {
        background-color: #f0fff4;
        border-color: #48bb78;
    }
    
    .alert-error {
        background-color: #fff5f5;
        border-color: #f56565;
    }
</style>
""", unsafe_allow_html=True)

# ============================================================================
# APP TITLE
# ============================================================================

st.markdown('<h1 class="main-title">🏢 Postpass Building Overlap Detector</h1>', unsafe_allow_html=True)
st.markdown("### Find overlapping buildings in OpenStreetMap data using the Postpass API")

# ============================================================================
# SESSION STATE INITIALIZATION
# ============================================================================

if 'query_history' not in st.session_state:
    st.session_state.query_history = []

if 'api_status' not in st.session_state:
    st.session_state.api_status = None

if 'current_results' not in st.session_state:
    st.session_state.current_results = None

if 'bbox_input' not in st.session_state:
    st.session_state.bbox_input = "8.34,48.97,8.46,49.03"

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def check_api_status():
    """Check if Postpass API is online"""
    try:
        query = "SELECT value as timestamp FROM osm2pgsql_properties WHERE property = 'import_timestamp'"
        response = requests.post(
            "https://postpass.geofabrik.de/api/0.2/interpreter",
            data={"data": query, "options[geojson]": "false"},
            timeout=10
        )
        if response.status_code == 200:
            csv_data = list(csv.reader(StringIO(response.text)))
            if csv_data and len(csv_data) > 1:
                return {
                    "status": "online",
                    "timestamp": csv_data[1][0] if len(csv_data[1]) > 0 else csv_data[0][0],
                    "message": "✅ API is online"
                }
            return {"status": "online", "message": "✅ API is online"}
    except Exception as e:
        return {"status": "offline", "message": f"❌ API Error: {str(e)[:100]}"}
    return {"status": "unknown", "message": "⚠️ Could not determine API status"}

def parse_bbox(bbox_input):
    """Parse and validate BBOX input"""
    try:
        bbox_input = bbox_input.strip("[](){} ")
        bbox_parts = bbox_input.split(",")
        
        if len(bbox_parts) != 4:
            return None, "Please enter exactly 4 coordinates: west, south, east, north"
            
        west, south, east, north = [float(coord.strip()) for coord in bbox_parts]
        
        # Validate coordinates
        if not (-180 <= west <= 180 and -180 <= east <= 180):
            return None, "Longitude must be between -180 and 180"
        if not (-90 <= south <= 90 and -90 <= north <= 90):
            return None, "Latitude must be between -90 and 90"
        if west >= east:
            return None, "West must be less than East"
        if south >= north:
            return None, "South must be less than North"
            
        return (west, south, east, north), None
        
    except ValueError:
        return None, "Please enter valid numeric coordinates"

def build_overlap_query(west, south, east, north, min_overlap=1.0, limit=100):
    """Build optimized overlap detection query"""
    return f"""
SELECT 
    a.osm_type || '/' || a.osm_id as building_a_id,
    b.osm_type || '/' || b.osm_id as building_b_id,
    ROUND(ST_Area(ST_Intersection(a.geom, b.geom)::geography)::numeric, 2) as overlap_area_m2,
    ST_AsText(ST_Intersection(a.geom, b.geom)) as wkt_geom,
    ROUND(ST_Area(a.geom::geography)::numeric, 2) as area_a_m2,
    ROUND(ST_Area(b.geom::geography)::numeric, 2) as area_b_m2,
    a.tags->>'building' as a_building_type,
    b.tags->>'building' as b_building_type
FROM postpass_polygon a
JOIN postpass_polygon b 
ON (
    (a.osm_type, a.osm_id) < (b.osm_type, b.osm_id)
    AND a.geom && b.geom
)
WHERE 
    a.tags ? 'building' 
    AND b.tags ? 'building'
    AND a.geom && ST_MakeEnvelope({west}, {south}, {east}, {north}, 4326)
    AND b.geom && ST_MakeEnvelope({west}, {south}, {east}, {north}, 4326)
    AND ST_Overlaps(a.geom, b.geom)
    AND ST_Area(ST_Intersection(a.geom, b.geom)::geography) > {min_overlap}
ORDER BY overlap_area_m2 DESC
LIMIT {limit}
"""

def execute_postpass_query(query, timeout=120, geojson=False):
    """Execute query on Postpass API with proper error handling"""
    post_data = {"data": query}
    if not geojson:
        post_data["options[geojson]"] = "false"
    
    try:
        response = requests.post(
            "https://postpass.geofabrik.de/api/0.2/interpreter",
            data=post_data,
            timeout=timeout
        )
        return response
    except requests.exceptions.Timeout:
        raise Exception(f"Query timed out after {timeout} seconds")
    except requests.exceptions.RequestException as e:
        raise Exception(f"Network error: {str(e)}")

def parse_csv_response(response_text):
    """Parse CSV response from Postpass"""
    if not response_text.strip():
        return None, []
    
    csv_reader = csv.reader(StringIO(response_text))
    rows = list(csv_reader)
    
    if not rows:
        return None, []
    
    headers = rows[0]
    data_rows = rows[1:] if len(rows) > 1 else []
    
    return headers, data_rows

# ============================================================================
# SIDEBAR
# ============================================================================

with st.sidebar:
    st.markdown("## ⚙️ Settings")
    st.markdown("---")
    
    # API Status Check
    if st.button("🔄 Check API Status", use_container_width=True):
        with st.spinner("Checking..."):
            st.session_state.api_status = check_api_status()
    
    if st.session_state.api_status:
        status = st.session_state.api_status
        if status["status"] == "online":
            st.success(status["message"])
            if "timestamp" in status:
                st.caption(f"Last update: {status['timestamp']}")
        else:
            st.error(status["message"])
    
    st.markdown("---")
    
    # BBOX Input
    st.markdown("### 📍 Search Area")
    
    bbox_option = st.radio(
        "Input method:",
        ["Use Example", "Enter Coordinates"],
        horizontal=True,
        label_visibility="collapsed"
    )
    
    if bbox_option == "Use Example":
        example = st.selectbox(
            "Choose example area:",
            [
                "Karlsruhe, Germany",
                "Colombo, Sri Lanka", 
                "Berlin, Germany",
                "San Francisco, USA"
            ],
            index=0
        )
        
        examples = {
            "Karlsruhe, Germany": "8.34,48.97,8.46,49.03",
            "Colombo, Sri Lanka": "79.85,6.92,79.92,6.96",
            "Berlin, Germany": "13.08,52.33,13.76,52.67",
            "San Francisco, USA": "-122.52,37.70,-122.36,37.82"
        }
        
        bbox_input = examples[example]
        st.code(bbox_input, language="text")
        
    else:
        bbox_input = st.text_input(
            "Enter BBOX (west,south,east,north):",
            value=st.session_state.bbox_input,
            help="Format: 8.34,48.97,8.46,49.03"
        )
        st.session_state.bbox_input = bbox_input
    
    st.markdown("---")
    
    # Analysis Settings
    st.markdown("### 🔧 Analysis Parameters")
    
    min_overlap = st.slider(
        "Minimum overlap area (m²):",
        min_value=0.1,
        max_value=50.0,
        value=1.0,
        step=0.1,
        help="Filter out small overlaps"
    )
    
    max_results = st.slider(
        "Maximum results:",
        min_value=10,
        max_value=200,
        value=50,
        step=10,
        help="Limit number of results"
    )
    
    timeout = st.slider(
        "Timeout (seconds):",
        min_value=30,
        max_value=180,
        value=90,
        step=30
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

# Initialize session state
if 'run_query' not in st.session_state:
    st.session_state.run_query = False

# Main content area
st.markdown('<div class="info-card">', unsafe_allow_html=True)
st.markdown("""
### Welcome to the Postpass Building Overlap Detector

This tool helps you identify overlapping buildings in OpenStreetMap data using the **Postpass API**. 
Overlapping buildings often indicate data quality issues that can be fixed to improve map accuracy.

**How to use:**
1. Select or enter a bounding box (BBOX) in the sidebar
2. Adjust analysis parameters as needed
3. Click **"Find Overlaps"** to run the analysis
4. View results in the table and on the interactive map
""")
st.markdown('</div>', unsafe_allow_html=True)

# Run query if requested
if st.session_state.run_query and bbox_input:
    # Parse BBOX
    bbox_result, error = parse_bbox(bbox_input)
    
    if error:
        st.error(f"❌ {error}")
        st.stop()
    
    west, south, east, north = bbox_result
    
    # Display BBOX info
    st.markdown('<div class="info-card">', unsafe_allow_html=True)
    st.markdown("### 📍 Search Area Information")
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("West", f"{west:.6f}")
    with col2:
        st.metric("South", f"{south:.6f}")
    with col3:
        st.metric("East", f"{east:.6f}")
    with col4:
        st.metric("North", f"{north:.6f}")
    
    st.markdown(f"""
    **Analysis Parameters:**
    - Minimum overlap: {min_overlap} m²
    - Maximum results: {max_results}
    - Timeout: {timeout} seconds
    """)
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Build query
    query = build_overlap_query(west, south, east, north, min_overlap, max_results)
    
    # Show query
    with st.expander("📝 View SQL Query", expanded=False):
        st.code(query, language="sql")
    
    # Execute query
    with st.spinner("🔍 Querying Postpass API..."):
        start_time = time.time()
        
        try:
            # FIX: Always use geojson=false since we're returning CSV format
            response = execute_postpass_query(query, timeout, geojson=False)
            query_time = time.time() - start_time
            
            if response.status_code != 200:
                st.error(f"❌ API Error {response.status_code}")
                st.markdown('<div class="alert-error custom-alert">', unsafe_allow_html=True)
                st.code(response.text[:500], language="text")
                st.markdown('</div>', unsafe_allow_html=True)
                st.stop()
            
            # Parse response
            headers, data_rows = parse_csv_response(response.text)
            
            if not data_rows:
                st.warning("⚠️ No overlapping buildings found in this area.")
                st.stop()
            
            # Create DataFrame
            df = pd.DataFrame(data_rows, columns=headers)
            
            # Convert numeric columns
            numeric_cols = ['overlap_area_m2', 'area_a_m2', 'area_b_m2']
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # Store results
            st.session_state.current_results = {
                'dataframe': df,
                'bbox': (west, south, east, north),
                'query_time': query_time,
                'query': query
            }
            
            # Display success
            st.markdown('<div class="success-card">', unsafe_allow_html=True)
            st.success(f"✅ Found **{len(df)}** overlapping building pairs in **{query_time:.1f} seconds**")
            st.markdown('</div>', unsafe_allow_html=True)
            
        except requests.exceptions.Timeout:
            st.error(f"⏰ Query timed out after {timeout} seconds.")
            st.info("Try using a smaller area or increasing the timeout.")
        except Exception as e:
            st.error(f"❌ Error: {str(e)}")
    
    # Clear the flag
    st.session_state.run_query = False

# Display results if available
if st.session_state.current_results:
    results = st.session_state.current_results
    df = results['dataframe']
    
    # Summary Statistics
    st.markdown('<div class="section-title">📊 Results Summary</div>', unsafe_allow_html=True)
    
    if 'overlap_area_m2' in df.columns:
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            avg_area = df['overlap_area_m2'].mean()
            st.metric("Average Overlap", f"{avg_area:.1f} m²")
        
        with col2:
            max_area = df['overlap_area_m2'].max()
            st.metric("Maximum Overlap", f"{max_area:.1f} m²")
        
        with col3:
            total_area = df['overlap_area_m2'].sum()
            st.metric("Total Overlap", f"{total_area:.1f} m²")
        
        with col4:
            unique_buildings = len(set(df['building_a_id'].tolist() + df['building_b_id'].tolist()))
            st.metric("Unique Buildings", unique_buildings)
    
    # Data Table
    st.markdown('<div class="section-title">📋 Overlapping Building Pairs</div>', unsafe_allow_html=True)
    
    # Select columns to display
    display_cols = ['building_a_id', 'building_b_id', 'overlap_area_m2']
    if 'a_building_type' in df.columns:
        display_cols.append('a_building_type')
    if 'b_building_type' in df.columns:
        display_cols.append('b_building_type')
    
    display_df = df[display_cols].copy()
    
    # Format numbers
    if 'overlap_area_m2' in display_df.columns:
        display_df['overlap_area_m2'] = display_df['overlap_area_m2'].apply(
            lambda x: f"{float(x):.1f} m²" if pd.notna(x) else ""
        )
    
    st.dataframe(display_df, use_container_width=True, height=400)
    
    # Export Options
    st.markdown('<div class="section-title">💾 Export Data</div>', unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    
    with col1:
        # CSV Export
        csv_data = df.to_csv(index=False)
        st.download_button(
            label="📥 Download CSV",
            data=csv_data,
            file_name=f"building_overlaps_{time.strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            use_container_width=True
        )
    
    with col2:
        # GeoJSON Export (if geometries available)
        if 'wkt_geom' in df.columns:
            try:
                # Parse geometries
                geometries = []
                valid_data = []
                
                for idx, row in df.iterrows():
                    try:
                        geom_wkt = row['wkt_geom']
                        if pd.notna(geom_wkt) and str(geom_wkt).strip().lower() not in ['null', 'none', '']:
                            geom = wkt.loads(str(geom_wkt))
                            if not geom.is_empty:
                                geometries.append(geom)
                                
                                row_dict = {col: row[col] for col in df.columns if col != 'wkt_geom'}
                                valid_data.append(row_dict)
                    except:
                        continue
                
                if geometries:
                    gdf = gpd.GeoDataFrame(valid_data, geometry=geometries, crs="EPSG:4326")
                    geojson_str = gdf.to_json()
                    
                    st.download_button(
                        label="🗺️ Download GeoJSON",
                        data=geojson_str,
                        file_name=f"building_overlaps_{time.strftime('%Y%m%d_%H%M%S')}.geojson",
                        mime="application/geo+json",
                        use_container_width=True
                    )
            except Exception as e:
                st.warning(f"Could not create GeoJSON: {str(e)[:100]}")
    
    # Map Viewer
    st.markdown('<div class="section-title">🗺️ Interactive Map</div>', unsafe_allow_html=True)
    
    if 'wkt_geom' in df.columns:
        try:
            # Parse geometries for map
            geometries = []
            valid_data = []
            
            for idx, row in df.iterrows():
                try:
                    geom_wkt = row['wkt_geom']
                    if pd.notna(geom_wkt) and str(geom_wkt).strip().lower() not in ['null', 'none', '']:
                        geom = wkt.loads(str(geom_wkt))
                        if not geom.is_empty:
                            geometries.append(geom)
                            
                            row_dict = {col: row[col] for col in df.columns if col != 'wkt_geom'}
                            valid_data.append(row_dict)
                except:
                    continue
            
            if geometries:
                gdf = gpd.GeoDataFrame(valid_data, geometry=geometries, crs="EPSG:4326")
                
                # Create map
                west, south, east, north = results['bbox']
                center_lat = (south + north) / 2
                center_lon = (west + east) / 2
                
                m = folium.Map(
                    location=[center_lat, center_lon],
                    zoom_start=13,
                    tiles="OpenStreetMap",
                    width="100%",
                    height=500
                )
                
                # Add search bounding box
                folium.Rectangle(
                    bounds=[[south, west], [north, east]],
                    color='#3182ce',
                    fill=False,
                    weight=2,
                    opacity=0.7,
                    tooltip="Search Area"
                ).add_to(m)
                
                # Add overlapping areas
                folium.GeoJson(
                    gdf,
                    name="Overlapping Areas",
                    tooltip=folium.GeoJsonTooltip(
                        fields=['building_a_id', 'building_b_id', 'overlap_area_m2'],
                        aliases=['Building A:', 'Building B:', 'Overlap Area:'],
                        localize=True
                    ),
                    style_function=lambda x: {
                        'fillColor': '#e53e3e',
                        'color': '#c53030',
                        'weight': 1,
                        'fillOpacity': 0.6
                    }
                ).add_to(m)
                
                # Display map
                st_folium(m, width=800, height=500)
                
            else:
                st.info("No valid geometries available for mapping.")
                
        except Exception as e:
            st.warning(f"Could not create map: {str(e)[:100]}")
    else:
        st.info("No geometry data available for mapping.")

# ============================================================================
# FOOTER
# ============================================================================

st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #718096; padding: 2rem 0; font-size: 0.9rem;">
    <p><b>Postpass Building Overlap Detector</b> • Built with Streamlit</p>
    <p>Data source: <a href="https://www.openstreetmap.org" target="_blank">OpenStreetMap</a> • 
    API: <a href="https://postpass.geofabrik.de" target="_blank">Postpass</a> • 
    <a href="https://github.com/woodpeck/postpass-ops" target="_blank">Documentation</a></p>
</div>
""", unsafe_allow_html=True)
