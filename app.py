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
# CUSTOM CSS - HIGH CONTRAST, CLEAN DESIGN
# ============================================================================

st.markdown("""
<style>
    /* High contrast light theme */
    .stApp {
        background-color: #ffffff;
    }
    
    /* Main text color - high contrast black */
    .stMarkdown, .stText, .stTitle, .stHeader, .stSubheader {
        color: #000000 !important;
    }
    
    /* Sidebar styling */
    section[data-testid="stSidebar"] {
        background-color: #f0f2f6;
    }
    
    section[data-testid="stSidebar"] .stMarkdown {
        color: #000000 !important;
    }
    
    /* Main headers - high contrast */
    .main-title {
        font-size: 2.5rem;
        color: #1a237e !important;
        font-weight: 700;
        margin-bottom: 1rem;
        text-align: center;
    }
    
    .section-title {
        font-size: 1.8rem;
        color: #0d47a1 !important;
        font-weight: 600;
        margin-top: 2rem;
        margin-bottom: 1rem;
        padding-bottom: 0.5rem;
        border-bottom: 3px solid #0d47a1;
    }
    
    /* Info cards with high contrast */
    .info-card {
        background-color: #e3f2fd;
        padding: 1.5rem;
        border-radius: 8px;
        margin: 1rem 0;
        border-left: 5px solid #1565c0;
        color: #000000 !important;
    }
    
    .warning-card {
        background-color: #fff3e0;
        padding: 1.5rem;
        border-radius: 8px;
        margin: 1rem 0;
        border-left: 5px solid #f57c00;
        color: #000000 !important;
    }
    
    .success-card {
        background-color: #e8f5e9;
        padding: 1.5rem;
        border-radius: 8px;
        margin: 1rem 0;
        border-left: 5px solid #2e7d32;
        color: #000000 !important;
    }
    
    .error-card {
        background-color: #ffebee;
        padding: 1.5rem;
        border-radius: 8px;
        margin: 1rem 0;
        border-left: 5px solid #c62828;
        color: #000000 !important;
    }
    
    /* Buttons with high contrast */
    .stButton > button {
        background-color: #1565c0;
        color: white !important;
        font-weight: 600;
        border: none;
        border-radius: 6px;
        padding: 0.75rem 1.5rem;
        font-size: 1rem;
        transition: all 0.3s ease;
    }
    
    .stButton > button:hover {
        background-color: #0d47a1;
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(13, 71, 161, 0.3);
    }
    
    /* Input fields and sliders */
    .stSlider > div > div > div {
        color: #000000 !important;
    }
    
    .stNumberInput > div > div > input {
        color: #000000 !important;
        background-color: white !important;
    }
    
    .stTextInput > div > div > input {
        color: #000000 !important;
        background-color: white !important;
    }
    
    /* Dataframe styling */
    .dataframe {
        background-color: white !important;
        border: 2px solid #e0e0e0 !important;
        color: #000000 !important;
    }
    
    .dataframe th {
        background-color: #1565c0 !important;
        color: white !important;
        font-weight: 600 !important;
    }
    
    .dataframe td {
        color: #000000 !important;
        background-color: white !important;
    }
    
    /* Code blocks */
    .stCodeBlock {
        background-color: #f5f5f5 !important;
        border: 2px solid #bdbdbd !important;
        border-radius: 6px;
        color: #000000 !important;
    }
    
    /* Metric displays */
    .stMetric {
        background-color: white;
        padding: 1rem;
        border-radius: 8px;
        border: 2px solid #1565c0;
        color: #000000 !important;
    }
    
    .stMetric label {
        color: #1565c0 !important;
        font-weight: 600 !important;
    }
    
    .stMetric div {
        color: #000000 !important;
        font-weight: 700 !important;
    }
    
    /* Expander */
    .streamlit-expanderHeader {
        background-color: #e3f2fd !important;
        color: #000000 !important;
        font-weight: 600 !important;
        border: 1px solid #1565c0 !important;
        border-radius: 6px;
    }
    
    /* Selectbox, radio, checkbox */
    .stSelectbox, .stRadio, .stCheckbox {
        color: #000000 !important;
    }
    
    .stSelectbox > div > div {
        background-color: white !important;
        color: #000000 !important;
        border: 2px solid #1565c0 !important;
    }
    
    /* Links */
    a {
        color: #1565c0 !important;
        font-weight: 600 !important;
    }
    
    a:hover {
        color: #0d47a1 !important;
        text-decoration: underline !important;
    }
    
    /* Footer */
    .footer {
        text-align: center;
        color: #424242 !important;
        padding: 2rem 0;
        font-size: 0.9rem;
        border-top: 2px solid #e0e0e0;
        margin-top: 2rem;
    }
    
    /* Make all text black by default */
    * {
        color: #000000 !important;
    }
    
    /* Override Streamlit's default text colors */
    p, h1, h2, h3, h4, h5, h6, span, div, label {
        color: #000000 !important;
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

def build_simpler_query(west, south, east, north, min_overlap=1.0, limit=50):
    """Build a simpler, faster query to avoid timeouts"""
    return f"""
SELECT 
    a.osm_id as building_a_id,
    b.osm_id as building_b_id,
    ROUND(ST_Area(ST_Intersection(a.geom, b.geom)::geography)::numeric, 2) as overlap_area_m2,
    ST_AsText(ST_Centroid(ST_Intersection(a.geom, b.geom))) as centroid_wkt
FROM postpass_polygon a
JOIN postpass_polygon b 
ON a.osm_id < b.osm_id 
AND a.geom && b.geom
WHERE 
    a.tags ? 'building' 
    AND b.tags ? 'building'
    AND a.geom && ST_MakeEnvelope({west}, {south}, {east}, {north}, 4326)
    AND ST_Area(ST_Intersection(a.geom, b.geom)::geography) > {min_overlap}
ORDER BY overlap_area_m2 DESC
LIMIT {limit}
"""

def execute_postpass_query(query, timeout=60):
    """Execute query on Postpass API with proper error handling"""
    post_data = {
        "data": query,
        "options[geojson]": "false"
    }
    
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
            status = check_api_status()
            if status["status"] == "online":
                st.success(status["message"])
                if "timestamp" in status:
                    st.caption(f"Last update: {status['timestamp']}")
            else:
                st.error(status["message"])
    
    st.markdown("---")
    
    # BBOX Input
    st.markdown("### 📍 Search Area")
    
    # Simple BBOX input
    bbox_input = st.text_input(
        "Enter BBOX (west,south,east,north):",
        value=st.session_state.bbox_input,
        help="Example: 8.34,48.97,8.46,49.03"
    )
    st.session_state.bbox_input = bbox_input
    
    # Quick examples
    st.caption("Quick examples:")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Karlsruhe", use_container_width=True):
            st.session_state.bbox_input = "8.34,48.97,8.46,49.03"
            st.rerun()
    with col2:
        if st.button("Small area", use_container_width=True):
            st.session_state.bbox_input = "8.40,48.98,8.42,49.00"
            st.rerun()
    
    st.markdown("---")
    
    # Analysis Settings
    st.markdown("### 🔧 Analysis Parameters")
    
    # Use smaller default values to avoid timeouts
    min_overlap = st.slider(
        "Minimum overlap (m²):",
        min_value=0.1,
        max_value=10.0,
        value=0.5,
        step=0.1,
        help="Start with 0.5 m² for small areas"
    )
    
    max_results = st.slider(
        "Maximum results:",
        min_value=10,
        max_value=100,
        value=30,
        step=5,
        help="Limit results to avoid timeouts"
    )
    
    timeout = st.slider(
        "Timeout (seconds):",
        min_value=30,
        max_value=120,
        value=60,
        step=10,
        help="Query timeout limit"
    )
    
    st.markdown("---")
    
    # Action Buttons
    if st.button("🔍 Find Overlaps", type="primary", use_container_width=True):
        st.session_state.run_query = True
    
    if st.button("🧹 Clear Results", use_container_width=True):
        st.session_state.current_results = None
        st.rerun()

# ============================================================================
# MAIN CONTENT
# ============================================================================

# Welcome message
st.markdown('<div class="info-card">', unsafe_allow_html=True)
st.markdown("""
### Welcome to the Postpass Building Overlap Detector

This tool helps you identify overlapping buildings in OpenStreetMap data using the **Postpass API**. 
Overlapping buildings often indicate data quality issues that can be fixed to improve map accuracy.

**How to use:**
1. **Enter a bounding box** in the sidebar (west,south,east,north)
2. **Adjust parameters** - start with small values
3. **Click "Find Overlaps"** to run the analysis
4. **View results** in the table and map below

**Tip:** Start with a small area like Karlsruhe (8.34,48.97,8.46,49.03) and minimum overlap of 0.5 m²
""")
st.markdown('</div>', unsafe_allow_html=True)

# Run query if requested
if 'run_query' in st.session_state and st.session_state.run_query and bbox_input:
    # Parse BBOX
    bbox_result, error = parse_bbox(bbox_input)
    
    if error:
        st.markdown('<div class="error-card">', unsafe_allow_html=True)
        st.error(f"❌ {error}")
        st.markdown('</div>', unsafe_allow_html=True)
        st.session_state.run_query = False
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
    
    # Build SIMPLER query to avoid timeouts
    query = build_simpler_query(west, south, east, north, min_overlap, max_results)
    
    # Show query
    with st.expander("📝 View SQL Query", expanded=False):
        st.code(query, language="sql")
    
    # Execute query
    with st.spinner("🔍 Querying Postpass API... This may take a moment"):
        start_time = time.time()
        
        try:
            response = execute_postpass_query(query, timeout)
            query_time = time.time() - start_time
            
            if response.status_code != 200:
                st.markdown('<div class="error-card">', unsafe_allow_html=True)
                st.error(f"❌ API Error {response.status_code}")
                st.code(response.text[:500], language="text")
                st.markdown('</div>', unsafe_allow_html=True)
                st.session_state.run_query = False
                st.stop()
            
            # Parse response
            headers, data_rows = parse_csv_response(response.text)
            
            if not data_rows:
                st.markdown('<div class="warning-card">', unsafe_allow_html=True)
                st.warning("⚠️ No overlapping buildings found in this area.")
                st.markdown("Try increasing the minimum overlap or selecting a different area.")
                st.markdown('</div>', unsafe_allow_html=True)
                st.session_state.run_query = False
                st.stop()
            
            # Create DataFrame
            df = pd.DataFrame(data_rows, columns=headers)
            
            # Convert numeric columns
            if 'overlap_area_m2' in df.columns:
                df['overlap_area_m2'] = pd.to_numeric(df['overlap_area_m2'], errors='coerce')
            
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
            
        except Exception as e:
            st.markdown('<div class="error-card">', unsafe_allow_html=True)
            error_msg = str(e)
            st.error(f"❌ {error_msg}")
            
            # Provide helpful suggestions
            if "timed out" in error_msg.lower():
                st.markdown("""
                **Suggestions to fix timeout:**
                1. **Use a smaller area** - try the "Small area" button in sidebar
                2. **Increase minimum overlap** to 2-5 m²
                3. **Reduce maximum results** to 20-30
                4. **Increase timeout** to 90-120 seconds
                5. **Try a different location** - some areas have more data
                """)
            elif "geometry column" in error_msg.lower():
                st.markdown("""
                **API Schema Error:**
                The query needs to include a geometry column. Try using the simplified query in the app.
                """)
            else:
                st.markdown("""
                **General suggestions:**
                1. Check your internet connection
                2. Verify the API is online using the "Check API Status" button
                3. Try a different bounding box
                """)
            
            st.markdown('</div>', unsafe_allow_html=True)
    
    # Clear the flag
    st.session_state.run_query = False

# Display results if available
if st.session_state.current_results:
    results = st.session_state.current_results
    df = results['dataframe']
    
    # Summary Statistics
    st.markdown("### 📊 Results Summary")
    
    if 'overlap_area_m2' in df.columns:
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if len(df) > 0:
                avg_area = df['overlap_area_m2'].mean()
                st.metric("Average Overlap", f"{avg_area:.1f} m²")
            else:
                st.metric("Average Overlap", "0 m²")
        
        with col2:
            if len(df) > 0:
                max_area = df['overlap_area_m2'].max()
                st.metric("Maximum Overlap", f"{max_area:.1f} m²")
            else:
                st.metric("Maximum Overlap", "0 m²")
        
        with col3:
            total_buildings = len(set(df['building_a_id'].tolist() + df['building_b_id'].tolist()))
            st.metric("Buildings Found", total_buildings)
    
    # Data Table
    st.markdown("### 📋 Overlapping Building Pairs")
    
    # Select columns to display
    display_cols = ['building_a_id', 'building_b_id', 'overlap_area_m2']
    
    if display_cols[0] in df.columns and display_cols[1] in df.columns:
        display_df = df[display_cols].copy()
        
        # Format numbers
        if 'overlap_area_m2' in display_df.columns:
            display_df['overlap_area_m2'] = display_df['overlap_area_m2'].apply(
                lambda x: f"{float(x):.1f} m²" if pd.notna(x) else "N/A"
            )
        
        st.dataframe(display_df, use_container_width=True, height=300)
    else:
        st.warning("Could not display all columns in the results.")
    
    # Export Options
    st.markdown("### 💾 Export Data")
    
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
        # Simple text export
        txt_data = f"Building Overlap Analysis\n"
        txt_data += f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        txt_data += f"BBOX: {results['bbox']}\n"
        txt_data += f"Total pairs found: {len(df)}\n\n"
        
        if 'overlap_area_m2' in df.columns and len(df) > 0:
            txt_data += f"Average overlap: {df['overlap_area_m2'].mean():.1f} m²\n"
            txt_data += f"Maximum overlap: {df['overlap_area_m2'].max():.1f} m²\n\n"
        
        st.download_button(
            label="📄 Download Summary",
            data=txt_data,
            file_name=f"overlap_summary_{time.strftime('%Y%m%d_%H%M%S')}.txt",
            mime="text/plain",
            use_container_width=True
        )
    
    # Map Viewer (if centroid data available)
    st.markdown("### 🗺️ Map View")
    
    if 'centroid_wkt' in df.columns:
        try:
            # Parse centroids for map
            points = []
            point_data = []
            
            for idx, row in df.iterrows():
                try:
                    centroid_wkt = row['centroid_wkt']
                    if pd.notna(centroid_wkt) and str(centroid_wkt).strip().lower() not in ['null', 'none', '']:
                        geom = wkt.loads(str(centroid_wkt))
                        if not geom.is_empty:
                            points.append(geom)
                            point_data.append({
                                'building_a': row.get('building_a_id', ''),
                                'building_b': row.get('building_b_id', ''),
                                'overlap': row.get('overlap_area_m2', '')
                            })
                except:
                    continue
            
            if points:
                gdf = gpd.GeoDataFrame(point_data, geometry=points, crs="EPSG:4326")
                
                # Create map
                west, south, east, north = results['bbox']
                center_lat = (south + north) / 2
                center_lon = (west + east) / 2
                
                m = folium.Map(
                    location=[center_lat, center_lon],
                    zoom_start=13,
                    tiles="OpenStreetMap"
                )
                
                # Add search bounding box
                folium.Rectangle(
                    bounds=[[south, west], [north, east]],
                    color='blue',
                    fill=False,
                    weight=2,
                    opacity=0.7,
                    tooltip="Search Area"
                ).add_to(m)
                
                # Add centroid points
                for idx, row in gdf.iterrows():
                    if row.geometry:
                        folium.CircleMarker(
                            location=[row.geometry.y, row.geometry.x],
                            radius=6,
                            color='red',
                            fill=True,
                            fill_color='red',
                            fill_opacity=0.7,
                            tooltip=f"Buildings: {row['building_a']} & {row['building_b']}<br>Overlap: {row['overlap']} m²"
                        ).add_to(m)
                
                # Display map
                st_folium(m, width=800, height=500)
                
                st.info(f"📍 Showing {len(points)} overlap centroids on the map")
            else:
                st.info("No valid centroid data available for mapping.")
                
        except Exception as e:
            st.warning(f"Could not create map: {str(e)[:100]}")
    else:
        st.info("No centroid data available for mapping.")

# ============================================================================
# FOOTER
# ============================================================================

st.markdown("""
<div class="footer">
    <p><b>Postpass Building Overlap Detector</b> • Built with Streamlit</p>
    <p>Data source: <a href="https://www.openstreetmap.org" target="_blank">OpenStreetMap</a> • 
    API: <a href="https://postpass.geofabrik.de" target="_blank">Postpass</a></p>
    <p>For best results, use small areas and conservative parameters</p>
</div>
""", unsafe_allow_html=True)
