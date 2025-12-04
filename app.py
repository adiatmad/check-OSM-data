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
from datetime import datetime
import math

# ============================================================================
# CONFIGURATION
# ============================================================================

st.set_page_config(
    page_title="Postpass Explorer - OSM Spatial Analysis",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# API Configuration
POSTPASS_API = "https://postpass.geofabrik.de/api/0.2/interpreter"
API_VERSION = "0.2"

# Query cost thresholds (from config.go)
QUICK_MEDIUM_THRESHOLD = 150
MEDIUM_SLOW_THRESHOLD = 150000

# ============================================================================
# CUSTOM CSS
# ============================================================================

st.markdown("""
<style>
    /* Main styling */
    .main-header {
        font-size: 2.8rem;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        margin-bottom: 1rem;
        font-weight: 800;
    }
    
    .sub-header {
        font-size: 1.8rem;
        color: #2c7bb6;
        margin-top: 2rem;
        margin-bottom: 1rem;
        border-bottom: 3px solid #2c7bb6;
        padding-bottom: 0.5rem;
    }
    
    /* Info boxes */
    .info-box {
        background-color: #e8f4fd;
        padding: 1.5rem;
        border-radius: 0.75rem;
        border-left: 5px solid #1f77b4;
        margin: 1.5rem 0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    .warning-box {
        background-color: #fff3cd;
        padding: 1.5rem;
        border-radius: 0.75rem;
        border-left: 5px solid #ffc107;
        margin: 1.5rem 0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    .success-box {
        background-color: #d4edda;
        padding: 1.5rem;
        border-radius: 0.75rem;
        border-left: 5px solid #28a745;
        margin: 1.5rem 0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    /* Metric cards */
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 1rem;
        color: white;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        height: 100%;
    }
    
    .metric-card h3 {
        font-size: 1rem;
        margin-bottom: 0.5rem;
        opacity: 0.9;
    }
    
    .metric-card .value {
        font-size: 2rem;
        font-weight: 700;
        margin: 0.5rem 0;
    }
    
    .metric-card .unit {
        font-size: 0.9rem;
        opacity: 0.8;
    }
    
    /* Buttons */
    .stButton > button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        font-weight: 600;
        border: none;
        border-radius: 0.5rem;
        padding: 0.75rem 1.5rem;
        transition: all 0.3s ease;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
    }
    
    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 2rem;
        background-color: transparent;
    }
    
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        background-color: transparent;
        border-radius: 0.5rem 0.5rem 0 0;
        gap: 1rem;
        padding: 1rem 2rem;
        font-weight: 600;
    }
    
    .stTabs [aria-selected="true"] {
        background-color: #1f77b4 !important;
        color: white !important;
    }
    
    /* Code blocks */
    .stCodeBlock {
        border-radius: 0.5rem;
        border: 1px solid #e0e0e0;
    }
    
    /* Dataframe styling */
    .dataframe {
        border-radius: 0.5rem;
        overflow: hidden;
    }
</style>
""", unsafe_allow_html=True)

# ============================================================================
# SESSION STATE INITIALIZATION
# ============================================================================

if 'query_history' not in st.session_state:
    st.session_state.query_history = []

if 'api_status' not in st.session_state:
    st.session_state.api_status = None

if 'current_results' not in st.session_state:
    st.session_state.current_results = None

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def check_api_status():
    """Check if Postpass API is online and get import timestamp"""
    try:
        query = "SELECT value as timestamp FROM osm2pgsql_properties WHERE property = 'import_timestamp'"
        response = requests.post(
            POSTPASS_API,
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
    """Parse BBOX input with validation"""
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

def calculate_bbox_area(west, south, east, north):
    """Calculate approximate area of BBOX in km²"""
    # Simple approximation - more accurate would use geodesic area
    width_km = abs(east - west) * 111.32 * math.cos(math.radians((south + north) / 2))
    height_km = abs(north - south) * 111.32
    return width_km * height_km

def get_query_cost_estimate(query):
    """Get query cost estimate from Postpass EXPLAIN endpoint"""
    try:
        response = requests.post(
            f"{POSTPASS_API}?explain",
            data={"data": query},
            timeout=30
        )
        if response.status_code == 200:
            result = response.json()
            queue = result.get("queue", "unknown")
            plan = result.get("plan", [{}])[0]
            
            # Determine queue based on cost thresholds
            if queue == "quick":
                return "🟢 Quick (< 150 cost units)", "fast"
            elif queue == "medium":
                return "🟡 Medium (150 - 150,000 cost units)", "medium"
            elif queue == "slow":
                return "🔴 Slow (> 150,000 cost units)", "slow"
            else:
                return "⚪ Unknown", "unknown"
    except:
        pass
    return "⚪ Could not estimate", "unknown"

def build_overlap_query(west, south, east, north, min_overlap=1.0, limit=100):
    """Build optimized overlap detection query based on Postpass schema"""
    return f"""
SELECT 
    a.osm_type || '/' || a.osm_id as building_a_id,
    b.osm_type || '/' || b.osm_id as building_b_id,
    ROUND(ST_Area(ST_Intersection(a.geom, b.geom)::geography)::numeric, 2) as overlap_area_m2,
    ST_AsText(ST_Intersection(a.geom, b.geom)) as wkt_geom,
    ROUND(ST_Area(a.geom::geography)::numeric, 2) as area_a_m2,
    ROUND(ST_Area(b.geom::geography)::numeric, 2) as area_b_m2,
    a.tags->>'building' as a_building_type,
    b.tags->>'building' as b_building_type,
    a.tags->>'name' as a_name,
    b.tags->>'name' as b_name
FROM postpass_polygon a
JOIN postpass_polygon b 
ON (
    -- Efficient pair comparison using composite key
    (a.osm_type, a.osm_id) < (b.osm_type, b.osm_id)
    -- Fast bounding box intersection (uses spatial index)
    AND a.geom && b.geom
)
WHERE 
    -- Both must be buildings (uses jsonb existence operator ?)
    a.tags ? 'building' 
    AND b.tags ? 'building'
    -- Bounding box filter (uses spatial index)
    AND a.geom && ST_MakeEnvelope({west}, {south}, {east}, {north}, 4326)
    AND b.geom && ST_MakeEnvelope({west}, {south}, {east}, {north}, 4326)
    -- Precise geometric overlap check
    AND ST_Overlaps(a.geom, b.geom)
    -- Minimum overlap area filter
    AND ST_Area(ST_Intersection(a.geom, b.geom)::geography) > {min_overlap}
ORDER BY overlap_area_m2 DESC
LIMIT {limit}
"""

def execute_postpass_query(query, timeout=120, geojson=False):
    """Execute query on Postpass API"""
    post_data = {"data": query}
    if not geojson:
        post_data["options[geojson]"] = "false"
    
    response = requests.post(
        POSTPASS_API,
        data=post_data,
        timeout=timeout
    )
    
    return response

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
    st.markdown("## 🚀 Postpass Explorer")
    st.markdown("---")
    
    # API Status
    if st.button("🔄 Check API Status", use_container_width=True):
        with st.spinner("Checking..."):
            st.session_state.api_status = check_api_status()
    
    if st.session_state.api_status:
        status = st.session_state.api_status
        if status["status"] == "online":
            st.success(status["message"])
            if "timestamp" in status:
                st.caption(f"Data updated: {status['timestamp']}")
        else:
            st.error(status["message"])
    
    st.markdown("---")
    
    # BBOX Input
    st.markdown("### 📍 Search Area")
    
    bbox_option = st.radio(
        "Input method:",
        ["Quick Examples", "Manual Input"],
        horizontal=True
    )
    
    if bbox_option == "Quick Examples":
        example = st.selectbox(
            "Choose example:",
            [
                "Karlsruhe, Germany (small)",
                "Colombo, Sri Lanka (medium)", 
                "Berlin, Germany (city)",
                "San Francisco, USA",
                "Tokyo, Japan"
            ]
        )
        
        examples = {
            "Karlsruhe, Germany (small)": "8.34,48.97,8.46,49.03",
            "Colombo, Sri Lanka (medium)": "79.85,6.92,79.92,6.96",
            "Berlin, Germany (city)": "13.08,52.33,13.76,52.67",
            "San Francisco, USA": "-122.52,37.70,-122.36,37.82",
            "Tokyo, Japan": "139.69,35.65,139.78,35.70"
        }
        
        bbox_input = examples[example]
        st.code(bbox_input, language="text")
        
    else:
        bbox_input = st.text_input(
            "Enter BBOX (west,south,east,north):",
            value="8.34,48.97,8.46,49.03",
            help="Example: 8.34,48.97,8.46,49.03"
        )
    
    st.markdown("---")
    
    # Analysis Settings
    st.markdown("### ⚙️ Analysis Settings")
    
    min_overlap = st.slider(
        "Minimum overlap (m²):",
        min_value=0.1,
        max_value=100.0,
        value=1.0,
        step=0.1,
        help="Filter out small overlaps"
    )
    
    max_results = st.slider(
        "Maximum results:",
        min_value=10,
        max_value=500,
        value=100,
        step=10
    )
    
    timeout = st.slider(
        "Timeout (seconds):",
        min_value=30,
        max_value=300,
        value=120,
        step=30
    )
    
    st.markdown("---")
    
    # Quick Actions
    st.markdown("### ⚡ Quick Actions")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔍 Find Overlaps", type="primary", use_container_width=True):
            st.session_state.run_overlap_query = True
    with col2:
        if st.button("🧹 Clear Results", use_container_width=True):
            st.session_state.current_results = None
            st.rerun()

# ============================================================================
# MAIN CONTENT - TABS
# ============================================================================

tab1, tab2, tab3, tab4 = st.tabs([
    "🏢 Overlap Detection", 
    "📊 Custom Query",
    "🗺️ Map Viewer",
    "📚 Documentation"
])

# ============================================================================
# TAB 1: OVERLAP DETECTION
# ============================================================================

with tab1:
    st.markdown('<h2 class="sub-header">Building Overlap Detection</h2>', unsafe_allow_html=True)
    
    st.markdown("""
    <div class="info-box">
    <h4>🔍 What this tool does:</h4>
    <p>This tool detects overlapping buildings in OpenStreetMap data by querying the Postpass API. 
    It finds buildings that physically overlap with each other, which can indicate data quality issues 
    or help with urban planning analysis.</p>
    
    <h4>⚡ How it works:</h4>
    <ol>
        <li>Select or enter a bounding box (BBOX) in the sidebar</li>
        <li>Adjust analysis settings as needed</li>
        <li>Click "Find Overlaps" to run the query</li>
        <li>View results in tables and on the interactive map</li>
        <li>Export data for further analysis</li>
    </ol>
    </div>
    """, unsafe_allow_html=True)
    
    if hasattr(st.session_state, 'run_overlap_query') and st.session_state.run_overlap_query:
        # Parse BBOX
        bbox_result, error = parse_bbox(bbox_input)
        
        if error:
            st.error(f"❌ {error}")
            st.stop()
        
        west, south, east, north = bbox_result
        area_km2 = calculate_bbox_area(west, south, east, north)
        
        # Display BBOX info
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            with st.container():
                st.markdown('<div class="metric-card"><h3>West</h3><div class="value">{:.6f}</div><div class="unit">Longitude</div></div>'.format(west), unsafe_allow_html=True)
        with col2:
            with st.container():
                st.markdown('<div class="metric-card"><h3>South</h3><div class="value">{:.6f}</div><div class="unit">Latitude</div></div>'.format(south), unsafe_allow_html=True)
        with col3:
            with st.container():
                st.markdown('<div class="metric-card"><h3>East</h3><div class="value">{:.6f}</div><div class="unit">Longitude</div></div>'.format(east), unsafe_allow_html=True)
        with col4:
            with st.container():
                st.markdown('<div class="metric-card"><h3>North</h3><div class="value">{:.6f}</div><div class="unit">Latitude</div></div>'.format(north), unsafe_allow_html=True)
        
        st.markdown(f"""
        <div class="info-box">
        <h4>📍 Search Area Summary</h4>
        <p><b>Bounding Box:</b> [{west:.6f}, {south:.6f}, {east:.6f}, {north:.6f}]</p>
        <p><b>Approximate Area:</b> {area_km2:.1f} km²</p>
        <p><b>Query Parameters:</b> Min overlap = {min_overlap} m², Max results = {max_results}</p>
        </div>
        """, unsafe_allow_html=True)
        
        # Build and execute query
        query = build_overlap_query(west, south, east, north, min_overlap, max_results)
        
        with st.expander("🔎 View SQL Query", expanded=False):
            st.code(query, language="sql")
            
            # Get cost estimate
            cost_estimate, queue_type = get_query_cost_estimate(query)
            st.info(f"**Estimated query complexity:** {cost_estimate}")
        
        # Execute query
        with st.spinner(f"🚀 Executing query (timeout: {timeout}s)..."):
            start_time = time.time()
            
            try:
                response = execute_postpass_query(query, timeout, geojson=False)
                query_time = time.time() - start_time
                
                if response.status_code != 200:
                    st.error(f"❌ API Error {response.status_code}")
                    st.code(response.text[:500], language="text")
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
                
                # Display success message
                st.success(f"✅ Found {len(df)} overlapping building pairs in {query_time:.1f} seconds!")
                
            except requests.exceptions.Timeout:
                st.error(f"⏰ Query timed out after {timeout} seconds. Try a smaller area or increase timeout.")
                st.stop()
            except Exception as e:
                st.error(f"❌ Error: {str(e)[:200]}")
                st.stop()
        
        # Clear the flag
        st.session_state.run_overlap_query = False
    
    # Display results if available
    if st.session_state.current_results:
        results = st.session_state.current_results
        df = results['dataframe']
        
        # Summary statistics
        st.markdown('<h3>📊 Summary Statistics</h3>', unsafe_allow_html=True)
        
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
                st.metric("Total Overlap Area", f"{total_area:.1f} m²")
            
            with col4:
                st.metric("Building Pairs", len(df))
        
        # Data table
        st.markdown('<h3>📋 Overlapping Building Pairs</h3>', unsafe_allow_html=True)
        
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
        
        # Export options
        st.markdown('<h3>💾 Export Data</h3>', unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        
        with col1:
            # CSV Export
            csv_data = df.to_csv(index=False)
            st.download_button(
                label="📥 Download as CSV",
                data=csv_data,
                file_name=f"overlaps_{time.strftime('%Y%m%d_%H%M%S')}.csv",
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
                            label="🗺️ Download as GeoJSON",
                            data=geojson_str,
                            file_name=f"overlaps_{time.strftime('%Y%m%d_%H%M%S')}.geojson",
                            mime="application/geo+json",
                            use_container_width=True
                        )
                except Exception as e:
                    st.warning(f"Could not create GeoJSON: {str(e)[:100]}")

# ============================================================================
# TAB 2: CUSTOM QUERY
# ============================================================================

with tab2:
    st.markdown('<h2 class="sub-header">Custom SQL Query</h2>', unsafe_allow_html=True)
    
    st.markdown("""
    <div class="info-box">
    <h4>🔧 Run Custom Queries</h4>
    <p>Execute your own SQL queries against the Postpass database. Use the PostGIS schema 
    and OSM data to create custom analyses.</p>
    
    <h4>📚 Database Schema:</h4>
    <ul>
        <li><code>postpass_point</code> - Point geometries (nodes)</li>
        <li><code>postpass_line</code> - Line geometries (ways/relations)</li>
        <li><code>postpass_polygon</code> - Polygon geometries (ways/relations)</li>
        <li><code>postpass_pointpolygon</code> - Combined points and polygons view</li>
        <li><code>tags</code> column - JSONB containing all OSM tags</li>
    </ul>
    
    <p><b>Tip:</b> Use <code>tags->>'key'</code> to get tag values or <code>tags ? 'key'</code> to check tag existence.</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Query input
    query = st.text_area(
        "Enter your SQL query:",
        height=200,
        value="""SELECT 
    osm_type || '/' || osm_id as feature_id,
    tags->>'name' as name,
    tags->>'amenity' as amenity,
    ST_AsText(geom) as wkt_geom
FROM postpass_point
WHERE tags ? 'amenity'
AND geom && ST_MakeEnvelope(8.34,48.97,8.46,49.03,4326)
LIMIT 10""",
        help="Don't include semicolon at the end. Use options[geojson]=false for non-geometry queries."
    )
    
    col1, col2, col3 = st.columns([1, 1, 2])
    
    with col1:
        geojson_option = st.checkbox("Return GeoJSON", value=True, 
                                    help="Uncheck for CSV output (faster for large queries)")
    
    with col2:
        timeout_custom = st.number_input("Timeout (s)", value=60, min_value=10, max_value=300)
    
    with col3:
        if st.button("▶️ Execute Query", type="primary", use_container_width=True):
            st.session_state.run_custom_query = True
    
    if hasattr(st.session_state, 'run_custom_query') and st.session_state.run_custom_query:
        # Get cost estimate
        cost_estimate, queue_type = get_query_cost_estimate(query)
        
        st.info(f"**Query complexity:** {cost_estimate}")
        
        if queue_type == "slow":
            st.warning("⚠️ This query may take a long time to execute. Consider optimizing or using a smaller area.")
        
        # Execute query
        with st.spinner(f"Executing query..."):
            try:
                response = execute_postpass_query(query, timeout_custom, geojson=geojson_option)
                
                if response.status_code != 200:
                    st.error(f"❌ API Error {response.status_code}")
                    st.code(response.text[:500], language="text")
                    st.stop()
                
                # Display results
                if geojson_option:
                    try:
                        data = response.json()
                        st.success(f"✅ Query executed successfully")
                        
                        if "features" in data:
                            num_features = len(data["features"])
                            st.info(f"Found {num_features} features")
                            
                            # Display first few features
                            with st.expander("View GeoJSON data", expanded=False):
                                st.json(data)
                    except:
                        st.text_area("Response:", response.text[:2000], height=300)
                else:
                    # CSV output
                    headers, data_rows = parse_csv_response(response.text)
                    
                    if data_rows:
                        df_custom = pd.DataFrame(data_rows, columns=headers)
                        st.success(f"✅ Found {len(df_custom)} rows")
                        
                        st.dataframe(df_custom, use_container_width=True, height=400)
                        
                        # Download button
                        csv_custom = df_custom.to_csv(index=False)
                        st.download_button(
                            label="📥 Download CSV",
                            data=csv_custom,
                            file_name=f"query_{time.strftime('%Y%m%d_%H%M%S')}.csv",
                            mime="text/csv"
                        )
                    else:
                        st.info("Query executed successfully but returned no data.")
                
            except requests.exceptions.Timeout:
                st.error(f"⏰ Query timed out after {timeout_custom} seconds.")
            except Exception as e:
                st.error(f"❌ Error: {str(e)[:200]}")
        
        st.session_state.run_custom_query = False

# ============================================================================
# TAB 3: MAP VIEWER
# ============================================================================

with tab3:
    st.markdown('<h2 class="sub-header">Interactive Map Viewer</h2>', unsafe_allow_html=True)
    
    if st.session_state.current_results and 'wkt_geom' in st.session_state.current_results['dataframe'].columns:
        df = st.session_state.current_results['dataframe']
        west, south, east, north = st.session_state.current_results['bbox']
        
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
            center_lat = (south + north) / 2
            center_lon = (west + east) / 2
            
            m = folium.Map(
                location=[center_lat, center_lon],
                zoom_start=13,
                tiles="OpenStreetMap",
                control_scale=True
            )
            
            # Add search bounding box
            folium.Rectangle(
                bounds=[[south, west], [north, east]],
                color='#1f77b4',
                fill=False,
                weight=2,
                opacity=0.7,
                tooltip="Search Area",
                name="Search BBOX"
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
                    'fillColor': '#ff4444',
                    'color': '#ff0000',
                    'weight': 2,
                    'fillOpacity': 0.6
                },
                highlight_function=lambda x: {
                    'weight': 4,
                    'fillOpacity': 0.8,
                    'color': '#ff0000'
                }
            ).add_to(m)
            
            # Add layer control
            folium.LayerControl().add_to(m)
            
            # Display map
            st_folium(m, width=800, height=600)
            
            # Map statistics
            st.info(f"📍 Displaying {len(gdf)} overlapping areas on the map")
            
        else:
            st.warning("No valid geometries found for mapping.")
    else:
        st.info("👈 Run an overlap detection query first to see results on the map.")

# ============================================================================
# TAB 4: DOCUMENTATION
# ============================================================================

with tab4:
    st.markdown('<h2 class="sub-header">Postpass Documentation</h2>', unsafe_allow_html=True)
    
    # Quick reference
    with st.expander("📖 Quick Reference Guide", expanded=True):
        st.markdown("""
        ### Database Schema
        
        **Main Tables:**
        - `postpass_point` - Point geometries from OSM nodes
        - `postpass_line` - Line geometries from OSM ways/relations  
        - `postpass_polygon` - Polygon geometries from OSM ways/relations
        
        **Combined Views:**
        - `postpass_pointpolygon` - Points + Polygons
        - `postpass_pointline` - Points + Lines
        - `postpass_linepolygon` - Lines + Polygons
        - `postpass_pointlinepolygon` - All geometries
        
        **Tags Access:**
        ```sql
        -- Check if tag exists
        WHERE tags ? 'building'
        
        -- Get tag value
        SELECT tags->>'name' as name
        
        -- Multiple tags
        WHERE tags->>'amenity' = 'restaurant' 
          AND tags->>'cuisine' = 'italian'
        ```
        
        **Spatial Functions:**
        ```sql
        -- Bounding box filter (fast, uses index)
        AND geom && ST_MakeEnvelope(west, south, east, north, 4326)
        
        -- Area in square meters
        ST_Area(geom::geography)
        
        -- Intersection
        ST_Intersection(a.geom, b.geom)
        
        -- Overlap check
        ST_Overlaps(a.geom, b.geom)
        ```
        """)
    
    # API Information
    with st.expander("🔌 API Usage"):
        st.markdown("""
        ### API Endpoint
        ```
        POST https://postpass.geofabrik.de/api/0.2/interpreter
        ```
        
        ### Parameters
        - `data` - SQL query string (required)
        - `options[geojson]` - Set to `false` for CSV output
        - `options[collection]` - Set to `false` for single object
        - `options[own_agg]` - Set to `false` to disable JSON aggregation
        
        ### Example cURL
        ```bash
        curl -g "https://postpass.geofabrik.de/api/0.2/interpreter" \\
          --data-urlencode "data=SELECT * FROM postpass_point LIMIT 5" \\
          --data-urlencode "options[geojson]=false"
        ```
        
        ### Query Cost Estimation
        Postpass uses PostgreSQL's `EXPLAIN` to estimate query cost:
        - **🟢 Quick**: < 150 cost units
        - **🟡 Medium**: 150 - 150,000 cost units  
        - **🔴 Slow**: > 150,000 cost units
        
        Use `/api/0.2/interpreter?explain` to get cost estimate before running query.
        """)
    
    # Best Practices
    with st.expander("💡 Best Practices"):
        st.markdown("""
        ### Performance Tips
        
        1. **Always use bounding boxes**
           ```sql
           AND geom && ST_MakeEnvelope(...)
           ```
        
        2. **Use spatial indexes**
           - `&&` operator uses GIST index
           - Put bounding box check before `ST_Intersects`
        
        3. **Limit results**
           ```sql
           LIMIT 100
           ```
        
        4. **Use appropriate geometry type**
           - Use `postpass_point` for points
           - Use `postpass_polygon` for polygons
           - Use combined views only when necessary
        
        5. **Optimize tag queries**
           ```sql
           -- Fast: Existence check
           WHERE tags ? 'building'
           
           -- Slower: Value comparison  
           WHERE tags->>'building' = 'house'
           ```
        
        ### Common Queries
        
        **Count amenities in area:**
        ```sql
        SELECT COUNT(*), tags->>'amenity' 
        FROM postpass_point
        WHERE tags ? 'amenity'
        AND geom && ST_MakeEnvelope(...)
        GROUP BY tags->>'amenity'
        ```
        
        **Find overlapping buildings:**
        ```sql
        SELECT a.osm_id, b.osm_id,
          ST_Area(ST_Intersection(a.geom, b.geom)::geography) as overlap
        FROM postpass_polygon a
        JOIN postpass_polygon b 
        ON a.osm_id < b.osm_id 
        AND a.geom && b.geom
        WHERE a.tags ? 'building' 
        AND b.tags ? 'building'
        AND ST_Overlaps(a.geom, b.geom)
        ```
        """)
    
    # Examples
    with st.expander("🎯 Example Queries"):
        st.markdown("""
        ### Simple Queries
        
        **Get fast food places in Karlsruhe:**
        ```sql
        SELECT tags->>'name' as name, ST_AsText(geom) as location
        FROM postpass_point
        WHERE tags->>'amenity' = 'fast_food'
        AND geom && ST_MakeEnvelope(8.34,48.97,8.46,49.03,4326)
        LIMIT 20
        ```
        
        **Count building types:**
        ```sql
        SELECT tags->>'building' as type, COUNT(*) as count
        FROM postpass_polygon
        WHERE tags ? 'building'
        AND geom && ST_MakeEnvelope(...)
        GROUP BY tags->>'building'
        ORDER BY count DESC
        ```
        
        ### Advanced Queries
        
        **Find addresses without postcodes:**
        ```sql
        SELECT osm_id, tags->>'addr:street' as street
        FROM postpass_pointpolygon
        WHERE tags ? 'addr:street'
        AND NOT tags ? 'addr:postcode'
        AND geom && ST_MakeEnvelope(...)
        ```
        
        **Calculate highway lengths:**
        ```sql
        SELECT tags->>'highway' as type,
          SUM(ST_Length(geom::geography)) as length_m
        FROM postpass_line
        WHERE tags ? 'highway'
        AND geom && ST_MakeEnvelope(...)
        GROUP BY tags->>'highway'
        ```
        
        **Find intersections of different landuses:**
        ```sql
        SELECT 
          a.tags->>'landuse' as landuse1,
          b.tags->>'landuse' as landuse2,
          ST_Area(ST_Intersection(a.geom, b.geom)::geography) as overlap_m2
        FROM postpass_polygon a
        JOIN postpass_polygon b 
        ON a.osm_id < b.osm_id 
        AND a.geom && b.geom
        WHERE a.tags ? 'landuse'
        AND b.tags ? 'landuse'
        AND ST_Overlaps(a.geom, b.geom)
        ```
        """)

# ============================================================================
# FOOTER
# ============================================================================

st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666; padding: 2rem 0;">
    <p><b>Postpass Explorer v1.0</b> | Built with Streamlit and Postpass API</p>
    <p>Data source: <a href="https://www.openstreetmap.org" target="_blank">OpenStreetMap</a> | 
    API: <a href="https://postpass.geofabrik.de" target="_blank">Postpass</a> | 
    Documentation: <a href="https://github.com/woodpeck/postpass-ops" target="_blank">GitHub</a></p>
    <p>© 2025 | This tool is for educational and analytical purposes only</p>
</div>
""", unsafe_allow_html=True)
