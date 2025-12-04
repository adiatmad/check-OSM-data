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
    
    /* Progress bar */
    .stProgress > div > div > div > div {
        background-color: #0066cc;
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

if 'building_geometries' not in st.session_state:
    st.session_state.building_geometries = {}

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

def calculate_area_size(west, south, east, north):
    """Calculate approximate area size in km²"""
    # Rough approximation (1° ≈ 111 km)
    width_km = abs(east - west) * 111.32
    height_km = abs(north - south) * 111.32
    return width_km * height_km

def get_buildings_in_area(west, south, east, north, batch_size=500):
    """Get all buildings in the area with their geometries"""
    query = f"""
SELECT 
    osm_id,
    osm_type,
    ST_AsText(geom) as wkt_geom,
    tags->>'building' as building_type
FROM postpass_polygon 
WHERE tags ? 'building'
AND geom && ST_MakeEnvelope({west}, {south}, {east}, {north}, 4326)
LIMIT {batch_size}
"""
    
    try:
        response = requests.post(
            "https://postpass.geofabrik.de/api/0.2/interpreter",
            data={"data": query, "options[geojson]": "false"},
            timeout=60
        )
        
        if response.status_code == 200:
            headers, rows = parse_api_response(response.text)
            if headers and rows:
                buildings = {}
                for row in rows:
                    if len(row) >= 4:
                        building_id = f"{row[1]}/{row[0]}" if len(row) > 1 else str(row[0])
                        buildings[building_id] = {
                            'osm_id': row[0],
                            'osm_type': row[1] if len(row) > 1 else 'W',
                            'wkt_geom': row[2] if len(row) > 2 else '',
                            'building_type': row[3] if len(row) > 3 else ''
                        }
                return buildings
    except Exception as e:
        st.warning(f"Could not fetch building geometries: {str(e)[:100]}")
    
    return {}

def find_overlaps_among_buildings(buildings_dict, limit=100):
    """Find overlaps among a dictionary of buildings"""
    import itertools
    from shapely.geometry import Polygon, MultiPolygon
    
    overlaps = []
    building_items = list(buildings_dict.items())
    
    # Limit number of comparisons for performance
    max_comparisons = min(1000, len(building_items) * (len(building_items) - 1) // 2)
    comparison_count = 0
    
    for i, (id1, data1) in enumerate(building_items):
        if i >= 100:  # Limit first building to prevent too many comparisons
            break
            
        for j, (id2, data2) in enumerate(building_items[i+1:], i+1):
            if comparison_count >= max_comparisons:
                break
                
            try:
                # Parse geometries
                geom1 = wkt.loads(data1['wkt_geom'])
                geom2 = wkt.loads(data2['wkt_geom'])
                
                # Check if geometries overlap
                if geom1.intersects(geom2):
                    intersection = geom1.intersection(geom2)
                    if not intersection.is_empty:
                        overlap_area = intersection.area * 111.32 * 111.32 * 1000000  # Approx m²
                        
                        overlaps.append({
                            'building_a_id': id1,
                            'building_b_id': id2,
                            'overlap_area_m2': round(overlap_area, 2),
                            'intersection_wkt': intersection.wkt,
                            'a_osm_id': data1['osm_id'],
                            'a_osm_type': data1['osm_type'],
                            'b_osm_id': data2['osm_id'],
                            'b_osm_type': data2['osm_type'],
                            'a_building_type': data1.get('building_type', ''),
                            'b_building_type': data2.get('building_type', '')
                        })
                        
                        comparison_count += 1
                        
                        if len(overlaps) >= limit:
                            return overlaps
                            
            except Exception as e:
                continue
    
    return overlaps

def build_smart_overlap_query(west, south, east, north, limit=50):
    """Smart query that finds overlaps efficiently"""
    return f"""
WITH building_candidates AS (
    SELECT 
        osm_id,
        osm_type,
        geom,
        tags->>'building' as building_type
    FROM postpass_polygon 
    WHERE tags ? 'building'
    AND geom && ST_MakeEnvelope({west}, {south}, {east}, {north}, 4326)
    LIMIT 200  -- Limit initial candidates
)
SELECT 
    a.osm_type || '/' || a.osm_id as building_a_id,
    b.osm_type || '/' || b.osm_id as building_b_id,
    ROUND(ST_Area(ST_Intersection(a.geom, b.geom)::geography)) as overlap_area_m2,
    ST_AsText(ST_Intersection(a.geom, b.geom)) as intersection_wkt,
    a.osm_id as a_osm_id,
    a.osm_type as a_osm_type,
    b.osm_id as b_osm_id,
    b.osm_type as b_osm_type,
    a.building_type as a_building_type,
    b.building_type as b_building_type
FROM building_candidates a
JOIN building_candidates b ON a.osm_id < b.osm_id 
WHERE ST_Intersects(a.geom, b.geom)
AND ST_Area(ST_Intersection(a.geom, b.geom)::geography) > 0.1
ORDER BY overlap_area_m2 DESC
LIMIT {limit}
"""

def execute_query_safely(query, timeout=30):
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

def create_overlap_geojson(overlaps_df, buildings_dict):
    """Create GeoJSON with overlap geometries and building info"""
    features = []
    
    for _, row in overlaps_df.iterrows():
        # Add intersection polygon
        if 'intersection_wkt' in row and pd.notna(row['intersection_wkt']):
            try:
                geom = wkt.loads(str(row['intersection_wkt']))
                if not geom.is_empty:
                    feature = {
                        "type": "Feature",
                        "geometry": json.loads(gpd.GeoSeries([geom]).to_json())['features'][0]['geometry'],
                        "properties": {
                            "type": "overlap_area",
                            "building_a": row.get('building_a_id', ''),
                            "building_b": row.get('building_b_id', ''),
                            "overlap_area_m2": row.get('overlap_area_m2', 0),
                            "a_building_type": row.get('a_building_type', ''),
                            "b_building_type": row.get('b_building_type', '')
                        }
                    }
                    features.append(feature)
            except:
                pass
        
        # Add building geometries if available
        for building_id in [row.get('building_a_id'), row.get('building_b_id')]:
            if building_id and building_id in buildings_dict:
                building = buildings_dict[building_id]
                if building.get('wkt_geom'):
                    try:
                        geom = wkt.loads(building['wkt_geom'])
                        feature = {
                            "type": "Feature",
                            "geometry": json.loads(gpd.GeoSeries([geom]).to_json())['features'][0]['geometry'],
                            "properties": {
                                "type": "building",
                                "building_id": building_id,
                                "osm_id": building.get('osm_id', ''),
                                "osm_type": building.get('osm_type', ''),
                                "building_type": building.get('building_type', '')
                            }
                        }
                        features.append(feature)
                    except:
                        pass
    
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
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Tiny", use_container_width=True):
            st.session_state.bbox_input = "8.405,48.985,8.410,48.990"
            st.rerun()
    with col2:
        if st.button("Small", use_container_width=True):
            st.session_state.bbox_input = "8.40,48.98,8.42,49.00"
            st.rerun()
    with col3:
        if st.button("Medium", use_container_width=True):
            st.session_state.bbox_input = "8.38,48.96,8.44,49.02"
            st.rerun()
    
    st.divider()
    
    # Analysis Settings
    st.subheader("🔧 Parameters")
    
    analysis_mode = st.radio(
        "Analysis mode:",
        ["Fast Detection", "Detailed Analysis"],
        help="Fast: Quick overlap check. Detailed: Get geometries and areas."
    )
    
    max_results = st.slider(
        "Max overlaps to find:",
        min_value=10,
        max_value=200,
        value=50,
        step=10
    )
    
    min_overlap = st.slider(
        "Min overlap area (m²):",
        min_value=0.1,
        max_value=10.0,
        value=0.5,
        step=0.1
    )
    
    timeout = st.slider(
        "Timeout (seconds):",
        min_value=20,
        max_value=120,
        value=45,
        step=10
    )
    
    st.divider()
    
    # Action buttons
    if st.button("🔍 Find Overlaps", type="primary", use_container_width=True):
        st.session_state.run_query = True
    
    if st.button("🧹 Clear", use_container_width=True):
        st.session_state.current_results = None
        st.session_state.building_geometries = {}
        st.rerun()

# ============================================================================
# MAIN CONTENT
# ============================================================================

# Welcome message
st.markdown('<div class="info-box">', unsafe_allow_html=True)
st.markdown("""
### 🎯 Complete AOI Overlap Detection

This tool now processes **entire AOIs** and exports **GeoJSON with building geometries**.

**Features:**
- ✅ Processes complete AOIs (not just samples)
- ✅ Exports GeoJSON with building polygons
- ✅ Calculates overlap areas
- ✅ Works with large areas using smart sampling

**How to use:**
1. Enter your AOI BBOX
2. Choose analysis mode
3. Click "Find Overlaps"
4. Download GeoJSON with results
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
    area_size = calculate_area_size(west, south, east, north)
    
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
    
    st.info(f"Area size: {area_size:.2f} km²")
    
    if area_size > 1.0:
        st.warning("⚠️ Large area detected. Analysis may take longer.")
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Step 1: Get building geometries
    with st.spinner("Step 1: Fetching building geometries from AOI..."):
        progress_bar = st.progress(0)
        buildings_dict = get_buildings_in_area(west, south, east, north, batch_size=300)
        progress_bar.progress(50)
        
        if not buildings_dict:
            st.error("❌ No buildings found in this area")
            st.stop()
        
        st.success(f"✅ Found {len(buildings_dict)} buildings in AOI")
        st.session_state.building_geometries = buildings_dict
        progress_bar.progress(100)
    
    # Step 2: Find overlaps
    with st.spinner("Step 2: Analyzing building overlaps..."):
        if analysis_mode == "Fast Detection":
            # Use smart query
            query = build_smart_overlap_query(west, south, east, north, max_results)
            
            with st.expander("📝 View SQL Query", expanded=False):
                st.code(query, language="sql")
            
            response = execute_query_safely(query, timeout)
            
            if response is None:
                st.error("❌ Query timed out")
                st.stop()
            
            if response.status_code != 200:
                st.error(f"❌ API Error {response.status_code}")
                st.code(response.text[:300], language="text")
                st.stop()
            
            headers, data_rows = parse_api_response(response.text)
            
        else:  # Detailed Analysis
            # Use local geometry analysis
            overlaps = find_overlaps_among_buildings(buildings_dict, max_results)
            
            if overlaps:
                headers = list(overlaps[0].keys())
                data_rows = [list(overlap.values()) for overlap in overlaps]
            else:
                headers, data_rows = [], []
        
        if not data_rows:
            st.info("ℹ️ No overlapping buildings found in this AOI")
            st.stop()
        
        # Create DataFrame
        df = pd.DataFrame(data_rows, columns=headers)
        
        # Filter by minimum overlap if column exists
        if 'overlap_area_m2' in df.columns:
            df['overlap_area_m2'] = pd.to_numeric(df['overlap_area_m2'], errors='coerce')
            df = df[df['overlap_area_m2'] >= min_overlap]
        
        if len(df) == 0:
            st.info(f"ℹ️ No overlaps found with minimum area of {min_overlap} m²")
            st.stop()
        
        # Store results
        st.session_state.current_results = {
            'dataframe': df,
            'bbox': (west, south, east, north),
            'area_size_km2': area_size,
            'building_count': len(buildings_dict),
            'analysis_mode': analysis_mode
        }
        
        # Success message
        st.markdown('<div class="success-box">', unsafe_allow_html=True)
        st.success(f"✅ Found {len(df)} overlapping pairs among {len(buildings_dict)} buildings")
        st.markdown('</div>', unsafe_allow_html=True)
    
    st.session_state.run_query = False

# Display results
if st.session_state.current_results:
    results = st.session_state.current_results
    df = results['dataframe']
    buildings_dict = st.session_state.building_geometries
    
    # Summary
    st.markdown("### 📊 Analysis Summary")
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("AOI Size", f"{results['area_size_km2']:.2f} km²")
    with col2:
        st.metric("Buildings", results['building_count'])
    with col3:
        st.metric("Overlaps Found", len(df))
    with col4:
        if 'overlap_area_m2' in df.columns:
            avg_area = df['overlap_area_m2'].mean()
            st.metric("Avg Overlap", f"{avg_area:.1f} m²")
    
    # Display table
    if len(df) > 0:
        st.markdown("### 📋 Overlapping Building Pairs")
        
        # Create display DataFrame
        display_cols = ['building_a_id', 'building_b_id']
        if 'overlap_area_m2' in df.columns:
            display_cols.append('overlap_area_m2')
        if 'a_building_type' in df.columns:
            display_cols.append('a_building_type')
        if 'b_building_type' in df.columns:
            display_cols.append('b_building_type')
        
        display_df = df[display_cols].copy()
        
        # Format columns
        column_names = {
            'building_a_id': 'Building A',
            'building_b_id': 'Building B',
            'overlap_area_m2': 'Overlap (m²)',
            'a_building_type': 'Type A',
            'b_building_type': 'Type B'
        }
        display_df = display_df.rename(columns=column_names)
        
        if 'Overlap (m²)' in display_df.columns:
            display_df['Overlap (m²)'] = display_df['Overlap (m²)'].apply(
                lambda x: f"{float(x):.1f}" if pd.notna(x) else ""
            )
        
        st.dataframe(display_df, use_container_width=True, height=400)
    
    # Export Section
    st.markdown("### 💾 Export Results")
    
    col1, col2, col3 = st.columns(3)
    
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
        # GeoJSON Export
        if buildings_dict and len(df) > 0:
            geojson_data = create_overlap_geojson(df, buildings_dict)
            geojson_str = json.dumps(geojson_data, indent=2)
            
            st.download_button(
                label="🗺️ Download GeoJSON",
                data=geojson_str,
                file_name=f"overlaps_{time.strftime('%Y%m%d_%H%M%S')}.geojson",
                mime="application/geo+json",
                use_container_width=True
            )
        else:
            st.info("No GeoJSON available")
    
    with col3:
        # Summary Export
        summary = f"""AOI Building Overlap Analysis
===============================
Date: {time.strftime('%Y-%m-%d %H:%M:%S')}
AOI BBOX: {results['bbox']}
AOI Size: {results['area_size_km2']:.2f} km²
Total Buildings: {results['building_count']}
Overlap Pairs Found: {len(df)}
Analysis Mode: {results['analysis_mode']}

Overlap Pairs:
"""
        for idx, row in df.iterrows():
            summary += f"\n{idx+1}. {row.get('building_a_id', '?')} ↔ {row.get('building_b_id', '?')}"
            if 'overlap_area_m2' in row and pd.notna(row['overlap_area_m2']):
                summary += f" - {row['overlap_area_m2']} m²"
        
        st.download_button(
            label="📄 Download Summary",
            data=summary,
            file_name=f"summary_{time.strftime('%Y%m%d_%H%M%S')}.txt",
            mime="text/plain",
            use_container_width=True
        )
    
    # Map View
    st.markdown("### 🗺️ Interactive Map")
    
    try:
        west, south, east, north = results['bbox']
        center_lat = (south + north) / 2
        center_lon = (west + east) / 2
        
        m = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=14,
            width="100%",
            height=500
        )
        
        # Add AOI bounding box
        folium.Rectangle(
            bounds=[[south, west], [north, east]],
            color='blue',
            fill=True,
            fill_opacity=0.1,
            weight=2,
            tooltip=f"AOI: {results['area_size_km2']:.2f} km²"
        ).add_to(m)
        
        # Add overlap markers if we have centroids
        if 'intersection_wkt' in df.columns:
            overlap_layer = folium.FeatureGroup(name='Overlap Areas', show=True)
            for idx, row in df.iterrows():
                try:
                    if pd.notna(row['intersection_wkt']):
                        geom = wkt.loads(str(row['intersection_wkt']))
                        centroid = geom.centroid
                        
                        folium.CircleMarker(
                            location=[centroid.y, centroid.x],
                            radius=5,
                            color='red',
                            fill=True,
                            fill_color='red',
                            fill_opacity=0.7,
                            tooltip=f"Overlap: {row.get('overlap_area_m2', '?')} m²"
                        ).add_to(overlap_layer)
                except:
                    continue
            overlap_layer.add_to(m)
        
        # Add building layer if we have geometries
        if buildings_dict:
            building_layer = folium.FeatureGroup(name='Buildings', show=False)
            for building_id, building in list(buildings_dict.items())[:100]:  # Limit for performance
                try:
                    if building.get('wkt_geom'):
                        geom = wkt.loads(building['wkt_geom'])
                        centroid = geom.centroid
                        
                        folium.CircleMarker(
                            location=[centroid.y, centroid.x],
                            radius=3,
                            color='green',
                            fill=True,
                            fill_color='green',
                            fill_opacity=0.5,
                            tooltip=f"Building: {building_id}"
                        ).add_to(building_layer)
                except:
                    continue
            building_layer.add_to(m)
        
        # Add layer control
        folium.LayerControl().add_to(m)
        
        st_folium(m, width=800, height=500)
        
    except Exception as e:
        st.warning(f"Map could not be displayed: {str(e)[:100]}")

# ============================================================================
# FOOTER
# ============================================================================

st.divider()
st.markdown("""
<div style="text-align: center; color: #666; font-size: 0.9rem;">
    <p>🏢 Building Overlap Detector • Complete AOI Analysis • GeoJSON Export</p>
    <p>Data: OpenStreetMap • API: Postpass</p>
</div>
""", unsafe_allow_html=True)
