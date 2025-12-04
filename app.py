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
    st.session_state.bbox_input = "8.405,48.985,8.410,48.990"  # Very small default

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

def build_simple_overlap_query(west, south, east, north, limit=20):
    """Very simple query to find overlapping buildings"""
    return f"""
SELECT 
    a.osm_id as building_a_id,
    b.osm_id as building_b_id
FROM postpass_polygon a
JOIN postpass_polygon b ON a.osm_id < b.osm_id 
WHERE a.tags ? 'building' 
AND b.tags ? 'building'
AND a.geom && ST_MakeEnvelope({west}, {south}, {east}, {north}, 4326)
AND b.geom && ST_MakeEnvelope({west}, {south}, {east}, {north}, 4326)
AND a.geom && b.geom
LIMIT {limit}
"""

def get_building_geometries_query(west, south, east, north, limit=100):
    """Get building geometries for the AOI"""
    return f"""
SELECT 
    osm_id,
    osm_type,
    ST_AsText(geom) as wkt_geom,
    tags->>'building' as building_type,
    tags->>'name' as name
FROM postpass_polygon 
WHERE tags ? 'building'
AND geom && ST_MakeEnvelope({west}, {south}, {east}, {north}, 4326)
LIMIT {limit}
"""

def execute_query(query, timeout=30):
    """Execute a query and return parsed data"""
    try:
        response = requests.post(
            "https://postpass.geofabrik.de/api/0.2/interpreter",
            data={"data": query, "options[geojson]": "false"},
            timeout=timeout
        )
        
        if response.status_code != 200:
            return None, f"API Error {response.status_code}"
        
        # Parse the response
        content = response.text.strip()
        if not content:
            return [], "Empty response"
        
        # Try to parse as CSV
        try:
            csv_reader = csv.reader(StringIO(content))
            rows = list(csv_reader)
            
            if not rows:
                return [], "No data"
            
            # Check if first row looks like headers
            if len(rows) > 1:
                # Use first row as headers, rest as data
                return rows[1:], rows[0]
            else:
                # Only one row, might be data without headers
                return rows, []
                
        except:
            # Try to parse as JSON
            try:
                data = json.loads(content)
                if isinstance(data, dict) and 'result' in data:
                    rows = data['result']
                    if rows and isinstance(rows, list) and len(rows) > 0:
                        # Convert dict rows to list rows
                        headers = list(rows[0].keys())
                        data_rows = [[row.get(h, '') for h in headers] for row in rows]
                        return data_rows, headers
            except:
                pass
            
            # If all parsing fails, return raw lines
            lines = content.split('\n')
            if len(lines) > 1:
                return lines[1:], lines[0].split(',')
            else:
                return lines, []
                
    except requests.exceptions.Timeout:
        return None, "Query timed out"
    except Exception as e:
        return None, f"Error: {str(e)}"

def create_dataframe_safe(data_rows, headers):
    """Safely create DataFrame with proper error handling"""
    if not data_rows:
        return pd.DataFrame()
    
    # If no headers provided, create generic ones
    if not headers:
        # Use the length of the first data row
        num_cols = len(data_rows[0]) if data_rows else 0
        headers = [f"col_{i}" for i in range(num_cols)]
    
    # Check if headers match data rows
    if len(headers) != len(data_rows[0]):
        # Adjust headers to match data
        if len(headers) < len(data_rows[0]):
            # Add missing headers
            for i in range(len(headers), len(data_rows[0])):
                headers.append(f"col_{i}")
        else:
            # Truncate headers
            headers = headers[:len(data_rows[0])]
    
    try:
        df = pd.DataFrame(data_rows, columns=headers)
        return df
    except Exception as e:
        st.error(f"Error creating DataFrame: {str(e)}")
        # Try with generic headers as fallback
        try:
            num_cols = len(data_rows[0])
            generic_headers = [f"column_{i}" for i in range(num_cols)]
            df = pd.DataFrame(data_rows, columns=generic_headers)
            return df
        except:
            return pd.DataFrame()

def create_geojson_from_overlaps(overlaps_df, buildings_df):
    """Create GeoJSON from overlaps and building data"""
    features = []
    
    # Add building geometries
    if not buildings_df.empty and 'wkt_geom' in buildings_df.columns:
        for _, row in buildings_df.iterrows():
            try:
                if pd.notna(row['wkt_geom']):
                    geom = wkt.loads(str(row['wkt_geom']))
                    properties = {
                        'type': 'building',
                        'osm_id': row.get('osm_id', ''),
                        'osm_type': row.get('osm_type', ''),
                        'building_type': row.get('building_type', ''),
                        'name': row.get('name', '')
                    }
                    
                    feature = {
                        "type": "Feature",
                        "geometry": json.loads(gpd.GeoSeries([geom]).to_json())['features'][0]['geometry'],
                        "properties": properties
                    }
                    features.append(feature)
            except Exception as e:
                continue
    
    # Add overlap markers (centroids of overlapping areas)
    if not overlaps_df.empty:
        for _, row in overlaps_df.iterrows():
            try:
                # Get building IDs
                building_a_id = row.get('building_a_id', '')
                building_b_id = row.get('building_b_id', '')
                
                # Find building geometries
                building_a = None
                building_b = None
                
                if not buildings_df.empty:
                    if 'osm_id' in buildings_df.columns:
                        building_a = buildings_df[buildings_df['osm_id'] == str(building_a_id)]
                        building_b = buildings_df[buildings_df['osm_id'] == str(building_b_id)]
                
                # Create a simple point feature for the overlap
                # In a real implementation, you'd calculate the intersection
                # For now, we'll create a marker between the two buildings
                if not building_a.empty and 'wkt_geom' in building_a.columns:
                    try:
                        geom_a = wkt.loads(str(building_a.iloc[0]['wkt_geom']))
                        centroid_a = geom_a.centroid
                        
                        properties = {
                            'type': 'overlap',
                            'building_a': building_a_id,
                            'building_b': building_b_id,
                            'note': 'Approximate overlap location'
                        }
                        
                        feature = {
                            "type": "Feature",
                            "geometry": {
                                "type": "Point",
                                "coordinates": [centroid_a.x, centroid_a.y]
                            },
                            "properties": properties
                        }
                        features.append(feature)
                    except:
                        pass
                        
            except Exception as e:
                continue
    
    geojson = {
        "type": "FeatureCollection",
        "features": features
    }
    
    return geojson

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
        max_value=50,
        value=15,
        step=5
    )
    
    timeout = st.slider(
        "Timeout (seconds):",
        min_value=10,
        max_value=60,
        value=25,
        step=5
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
1. **Enter a small area** in the sidebar (use "Tiny" button for testing)
2. **Click "Find Overlaps"** 
3. **View results** below
4. **Download GeoJSON** with building geometries

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
    
    # Step 1: Get building geometries
    with st.spinner("Fetching building geometries..."):
        buildings_query = get_building_geometries_query(west, south, east, north, max_results*2)
        
        with st.expander("📝 View Buildings Query", expanded=False):
            st.code(buildings_query, language="sql")
        
        buildings_data, buildings_headers = execute_query(buildings_query, timeout)
        
        if buildings_data is None:
            st.error(f"❌ {buildings_headers}")
            st.stop()
        
        buildings_df = create_dataframe_safe(buildings_data, buildings_headers)
        
        if buildings_df.empty:
            st.warning("⚠️ No buildings found in this area")
            st.stop()
        
        st.success(f"✅ Found {len(buildings_df)} buildings")
    
    # Step 2: Find overlaps
    with st.spinner("Finding overlapping buildings..."):
        overlaps_query = build_simple_overlap_query(west, south, east, north, max_results)
        
        with st.expander("📝 View Overlaps Query", expanded=False):
            st.code(overlaps_query, language="sql")
        
        overlaps_data, overlaps_headers = execute_query(overlaps_query, timeout)
        
        if overlaps_data is None:
            st.error(f"❌ {overlaps_headers}")
            st.stop()
        
        overlaps_df = create_dataframe_safe(overlaps_data, overlaps_headers)
        
        if overlaps_df.empty:
            st.info("ℹ️ No overlapping buildings found")
            st.stop()
        
        # Store results
        st.session_state.current_results = {
            'overlaps_df': overlaps_df,
            'buildings_df': buildings_df,
            'bbox': (west, south, east, north),
            'query_time': time.time()
        }
        
        # Success message
        st.markdown('<div class="success-box">', unsafe_allow_html=True)
        st.success(f"✅ Found {len(overlaps_df)} overlapping building pairs")
        st.markdown('</div>', unsafe_allow_html=True)
    
    st.session_state.run_query = False

# Display results
if st.session_state.current_results:
    results = st.session_state.current_results
    overlaps_df = results['overlaps_df']
    buildings_df = results['buildings_df']
    
    # Summary
    st.markdown("### 📊 Results Summary")
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Buildings Found", len(buildings_df))
    with col2:
        st.metric("Overlap Pairs", len(overlaps_df))
    
    # Display overlaps table
    st.markdown("### 📋 Overlapping Building Pairs")
    
    if not overlaps_df.empty:
        # Clean up display
        display_df = overlaps_df.copy()
        
        # Rename columns if they exist
        column_map = {
            'building_a_id': 'Building A ID',
            'building_b_id': 'Building B ID',
            'col_0': 'Building A ID',
            'col_1': 'Building B ID'
        }
        
        for old_col, new_col in column_map.items():
            if old_col in display_df.columns:
                display_df = display_df.rename(columns={old_col: new_col})
        
        # Select relevant columns
        display_cols = []
        for col in ['Building A ID', 'Building B ID', 'building_a_id', 'building_b_id', 'col_0', 'col_1']:
            if col in display_df.columns:
                display_cols.append(col)
                if len(display_cols) >= 2:
                    break
        
        if display_cols:
            st.dataframe(display_df[display_cols].head(20), use_container_width=True)
        else:
            st.dataframe(display_df.head(20), use_container_width=True)
    
    # Display buildings table (collapsed)
    with st.expander("📋 View Building Details", expanded=False):
        if not buildings_df.empty:
            st.dataframe(buildings_df.head(20), use_container_width=True)
    
    # Export Section
    st.markdown("### 💾 Export Results")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # CSV Export - Overlaps
        if not overlaps_df.empty:
            csv_data = overlaps_df.to_csv(index=False)
            st.download_button(
                label="📥 Overlaps CSV",
                data=csv_data,
                file_name="overlaps.csv",
                mime="text/csv",
                use_container_width=True
            )
    
    with col2:
        # CSV Export - Buildings
        if not buildings_df.empty:
            csv_data = buildings_df.to_csv(index=False)
            st.download_button(
                label="📥 Buildings CSV",
                data=csv_data,
                file_name="buildings.csv",
                mime="text/csv",
                use_container_width=True
            )
    
    with col3:
        # GeoJSON Export
        try:
            geojson_data = create_geojson_from_overlaps(overlaps_df, buildings_df)
            geojson_str = json.dumps(geojson_data, indent=2)
            
            st.download_button(
                label="🗺️ GeoJSON",
                data=geojson_str,
                file_name="overlaps.geojson",
                mime="application/geo+json",
                use_container_width=True
            )
        except Exception as e:
            st.error(f"Could not create GeoJSON: {str(e)[:100]}")
    
    # Map View
    st.markdown("### 🗺️ Map View")
    
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
        
        # Add AOI boundary
        folium.Rectangle(
            bounds=[[south, west], [north, east]],
            color='blue',
            fill=False,
            weight=2,
            tooltip="Search Area"
        ).add_to(m)
        
        # Add building markers
        if not buildings_df.empty and 'wkt_geom' in buildings_df.columns:
            for idx, row in buildings_df.iterrows():
                try:
                    if pd.notna(row['wkt_geom']):
                        geom = wkt.loads(str(row['wkt_geom']))
                        centroid = geom.centroid
                        
                        folium.CircleMarker(
                            location=[centroid.y, centroid.x],
                            radius=3,
                            color='green',
                            fill=True,
                            tooltip=f"Building: {row.get('osm_id', '')}"
                        ).add_to(m)
                except:
                    continue
        
        # Add overlap markers
        if not overlaps_df.empty:
            # Simple markers for overlaps - in real app, would calculate intersection
            for idx, row in overlaps_df.iterrows():
                try:
                    # Use first building's location as marker
                    building_id = row.get('building_a_id', row.get('col_0', ''))
                    if building_id and not buildings_df.empty:
                        # Find the building
                        if 'osm_id' in buildings_df.columns:
                            building = buildings_df[buildings_df['osm_id'] == str(building_id)]
                            if not building.empty and 'wkt_geom' in building.columns:
                                geom = wkt.loads(str(building.iloc[0]['wkt_geom']))
                                centroid = geom.centroid
                                
                                folium.CircleMarker(
                                    location=[centroid.y, centroid.x],
                                    radius=5,
                                    color='red',
                                    fill=True,
                                    tooltip=f"Overlap: {building_id} & {row.get('building_b_id', row.get('col_1', ''))}"
                                ).add_to(m)
                except:
                    continue
        
        st_folium(m, width=800, height=400)
        
    except Exception as e:
        st.warning(f"Map could not be displayed")

# ============================================================================
# FOOTER
# ============================================================================

st.divider()
st.markdown("""
<div style="text-align: center; color: #666; font-size: 0.9rem;">
    <p>Building Overlap Detector • Complete AOI Analysis • GeoJSON Export</p>
</div>
""", unsafe_allow_html=True)
