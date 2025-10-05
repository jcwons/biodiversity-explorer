import streamlit as st
import ee
import json
import tempfile
import os

# --- Initialize Earth Engine ---
service_account = st.secrets["gee"]["service_account"]
key_json_str = st.secrets["gee"]["key_json"]

# Write the JSON string to a temporary file
temp_path = None
try:
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
        f.write(key_json_str)
        temp_path = f.name  # save the path

    # Initialize Earth Engine using the temporary file
    credentials = ee.ServiceAccountCredentials(service_account, temp_path)
    ee.Initialize(credentials)

finally:
    # Remove the temporary file manually
    if temp_path and os.path.exists(temp_path):
        os.remove(temp_path)

import folium
import pandas as pd
from streamlit_folium import st_folium
import geemap.foliumap as geemap
from metrics.landcover_metrics import get_landcover_metrics, get_ndvi_rating_map, get_ndvi_rating_summary, create_pie_chart
from metrics.gbif_metrics import get_gbif_sample, get_number_of_occurrences, get_biodiversity_indices
from branca.element import Template, MacroElement

import streamlit as st
import folium
from folium.plugins import Draw
from streamlit_folium import st_folium
from shapely.geometry import Polygon, mapping



# -------------------------------
# Session state initialization
# -------------------------------
if "geojson_input" not in st.session_state:
    st.session_state.geojson_input = None
if "show_map" not in st.session_state:
    st.session_state.show_map = True
if "map_center" not in st.session_state:
    st.session_state.map_center = [51.1657, 10.4515]  # default: Germany
if "map_zoom" not in st.session_state:
    st.session_state.map_zoom = 4

# --- Helper function: Convert GeoJSON string to ee.Geometry ---
def geojson_to_ee(geojson_str: str):
    try:
        geojson = json.loads(geojson_str)

        if geojson["type"] == "FeatureCollection":
            geom = geojson["features"][0]["geometry"]
        elif geojson["type"] == "Feature":
            geom = geojson["geometry"]
        else:  # assume it's already a geometry dict
            geom = geojson

        return ee.Geometry(geom)

    except Exception as e:
        raise ValueError(f"Error processing GeoJSON: {e}")

def reset_aoi():
    st.session_state.geojson_input = None
    st.session_state.show_map = True
    # No need to call st.experimental_rerun() — Streamlit reruns automatically after callback

def set_region(region):
    """Update map center and zoom when a region button is clicked"""
    regions = {
        "Europe": ([54, 15], 4),
        "Africa": ([5, 20], 3),
        "Asia": ([35, 90], 3),
        "APAC": ([-10, 140], 3),
        "South America": ([-15, -60], 3),
        "North America": ([45, -100], 3),
    }
    st.session_state.map_center, st.session_state.map_zoom = regions[region]
    st.session_state.selected_region = region


# --- Legend helper function ---
def add_legend(map_object, legend_dict, title="Legend"):
    legend_html = """
    <div style="position: fixed; 
                bottom: 50px; left: 50px; width: 150px; height: auto; 
                z-index:9999; font-size:14px;
                background-color: white; padding: 10px; border:2px solid grey;">
    <b>{}</b><br>
    """.format(title)

    for name, color in legend_dict.items():
        legend_html += f'<i style="background:{color};width:15px;height:15px;float:left;margin-right:5px;"></i>{name}<br>'
    
    legend_html += "</div>"

    template = Template(legend_html)
    macro = MacroElement()
    macro._template = template
    map_object.get_root().add_child(macro)


# -------------------------------
# For Debugging
# -------------------------------
#st.write("DEBUG session_state:", dict(st.session_state))


st.title("🌱 EcoMetrics: Biodiversity in Your Area")

# Title (only shown until AOI is drawn)
if st.session_state.show_map:
    # --- Region buttons ---
    st.markdown("### 🌍 Choose region to start")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Europe"): set_region("Europe")
        if st.button("Africa"): set_region("Africa")
    with col2:
        if st.button("Asia"): set_region("Asia")
        if st.button("APAC"): set_region("APAC")
    with col3:
        if st.button("South America"): set_region("South America")
        if st.button("North America"): set_region("North America")

    st.markdown("---")

    st.markdown("""
                ### 🗺️ Select your Area of Interest
                1. **Zoom in** to your region of interest.  
                2. **Click the square icon ⬛** on the left toolbar to draw a rectangle.  
                3. **Draw** your area on the map.  
    
                
                ℹ️ Note that this is a demo so keep the area to a reasonable size or else...
                """)

    # --- Map creation ---
    m = folium.Map(location=st.session_state.map_center,
                   zoom_start=st.session_state.map_zoom)
    Draw(export=False).add_to(m)

    output = st_folium(m, width=700, height=500)

    if output and "all_drawings" in output and output["all_drawings"]:
        shape = output["all_drawings"][0]
        coords = shape["geometry"]["coordinates"][0]

        polygon = Polygon(coords)
        geojson_input = {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "geometry": mapping(polygon),
                "properties": {}
            }]
        }

        # Store as JSON string
        st.session_state.geojson_input = json.dumps(geojson_input)
        st.session_state.show_map = False  # hide map after drawing
        st.rerun()

else:
    # Everything cleared; no UI visible
    geojson_input = st.session_state["geojson_input"]

    # The variable now holds your AOI GeoJSON object
    st.sidebar.title("Analysis")

    if st.sidebar.button("Run Analysis"):
        try:
            aoi_ee = geojson_to_ee(geojson_input)
            st.sidebar.success("✅ AOI successfully parsed!")
            area_km2 = aoi_ee.area().divide(1e6).getInfo()
            MAX_AOI_KM2 = 500
            if area_km2>MAX_AOI_KM2:
                st.sidebar.warning('⚠️ Area exceeds limit of 500km²')
                st.sidebar.info('New area of 500km² buffered around center is used instead')
                centroid = aoi_ee.centroid()
                side_m = (MAX_AOI_KM2 * 1e6) ** 0.5
                aoi_ee = centroid.buffer(side_m / 2).bounds()


            # --- Draw New AOI button ---
            st.sidebar.markdown("---")
            st.sidebar.button("🗺️ Draw New Area of Interest", on_click=reset_aoi)


            # --- Run metrics ---
            metrics, worldcover = get_landcover_metrics(aoi_ee)
            ndvi_map = get_ndvi_rating_map(aoi_ee)

            # --- Create geemap Map ---
            m = geemap.Map()

            # Fit map to AOI bounds
            bounds = aoi_ee.bounds().getInfo()['coordinates'][0]
            lons = [pt[0] for pt in bounds]
            lats = [pt[1] for pt in bounds]
            sw = [min(lats), min(lons)]
            ne = [max(lats), max(lons)]
            m.fit_bounds([sw, ne])

            # --- Visualization params ---
            worldcover_vis = {
                "bands": ["Map"],
                "min": 10,
                "max": 100,
                "palette": [
                    "006400", "ffbb22", "ffff4c", "f096ff", "#2E2D2C",
                    "b4b4b4", "f0f0f0", "0064c8", "0096a0", "00cf75",
                    "fae6a0", "bbffbb", "e6e6e6"
                ]
            }
            ndvi_vis = {"min": 1, "max": 5, "palette": ["red", "#FF0000", "#006400", "#006400", "#006400"]}

            worldcover_legend = {
                "Tree cover": "#006400",
                "Shrubland": "#ffbb22",
                "Grassland": "#ffff4c",
                "Cropland": "#f096ff",
                "Built-up": "#2E2D2C",
                "Sparse vegetation": "#b4b4b4",
                "Snow / ice": "#f0f0f0",
                "Permanent water": "#0064c8",
                "Herbaceous wetland": "#0096a0",
                "Mangroves": "#00cf75",
                "Moss and lichen": "#fae6a0",
                "Herbaceous wetland": "#bbffbb",
                "Other": "#e6e6e6",
                "Stressed Vegetation": "#FF0000"
            }

            # Clip images to AOI
            worldcover_clipped = worldcover.clip(aoi_ee)
            ndvi_clipped = ndvi_map.clip(aoi_ee)

            # Add EE layers
            m.addLayer(worldcover_clipped, worldcover_vis, "WorldCover")
            m.addLayer(ndvi_clipped, ndvi_vis, "NDVI")
            m.add_legend(title="WorldCover Class", legend_dict=worldcover_legend)
            folium.LayerControl().add_to(m)


            # Show interactive map
            m.to_streamlit(height=500)
            
            # --- Placeholders ---
            text_placeholder = st.empty()
            text_placeholder.image("thinking.gif")

            # --- Main page layout: 3 columns ---
            col1, col2 = st.columns([1, 1])  # Adjust widths if needed

            # --- Column 1 placeholder ---
            with col1:
                aoi_ee = geojson_to_ee(geojson_input)

                # --- Run metrics ---
                metrics, worldcover = get_landcover_metrics(aoi_ee)
                natural_hab = metrics['natural_habitat_fraction']
                antro_hab = metrics['anthropogenic_habitat_fraction']


                
                df = pd.DataFrame( metrics['top_5_landcover'], columns=['Landcover', 'Area', 'Percentage (%)'])
                df['Area'] = df['Area']/100
                st.dataframe(df,
                            column_order=("Landcover", "Area"),
                            hide_index=True,
                            width=None,
                            column_config={
                                "Landcover": st.column_config.TextColumn(
                                    "Landcover",
                                ),
                                "Area": st.column_config.ProgressColumn(
                                    "Area (ha)",
                                    format="%d",
                                    min_value=0,
                                    max_value=sum(df['Area']),
                                )}
                            )
                
                # HTML title
                title_html = (
                    "<span style='font-size:18px'>"
                    "<span style='color:#2ecc71;'>■</span> Natural vs "
                    "<span style='color:#e74c3c;'>■</span> Anthropogenic Habitat"
                    "</span>"
                )

                # Show HTML above chart
                st.markdown(title_html, unsafe_allow_html=True)

                pie = create_pie_chart([natural_hab, antro_hab],200)
                st.plotly_chart(pie, use_container_width=False)


            # --- Column 3 placeholder ---
            with col2:
                occ_total = get_number_of_occurrences(aoi_ee)
                st.write("A total of {:,} animals were recorded in the last year in the area on GBIF".format(occ_total))
                if occ_total>10000:
                    n_samples = 10000
                    st.write("For biodiversity estimations only 10,000 recordings are used")
                else:
                    n_samples = occ_total
                with st.spinner("Collection samples from GBIF. This might take 15-30s ..."):
                    samples = get_gbif_sample(aoi_ee, n_samples)
                bio_metrics = get_biodiversity_indices(samples)
            
                subcol1, subcol2 = st.columns([1,1])
                with subcol1:
                    st.metric(label="Species Richness", value=bio_metrics['species_richness'])                
                with subcol2:
                    st.metric(label="Shannon Index", value=f"{bio_metrics['shannon_index']:.2f}")                
                
            
                bio_data = {
                    "Simpson Diversity": bio_metrics['simpson_index'],
                    "Evenness": bio_metrics['evenness'],
                    "Berger-Parker dominance": bio_metrics['berger_parker_dominance']
                    }
                df = pd.DataFrame(bio_data.items(), columns=['metric', 'value'])
                st.dataframe(df,
                            column_order=("metric", "value"),
                            hide_index=True,
                            width=None,
                            column_config={
                                "metric": st.column_config.TextColumn(
                                    "Metric",
                                ),
                                "value": st.column_config.ProgressColumn(
                                    "Value",
                                    format="%.2f",
                                    min_value=0,
                                    max_value=1,
                                )}
                            )
                
            st.sidebar.markdown("---")

            st.markdown("### ℹ️ About the Biodiversity Metrics")

            st.markdown("""
            The biodiversity metrics displayed above are derived from species occurrence data in GBIF:

            - **Species Richness**: The total number of unique species observed in the area. Higher values indicate a more diverse ecosystem.
            - **Shannon Index**: Measures both the number of species and the evenness of their abundances. Higher values indicate not only more species but also a more balanced distribution among them.
            - **Simpson Index**: Reflects the probability that two individuals randomly selected from the area belong to the same species. Lower values indicate higher diversity.
            - **Species Density**: Number of species per unit area. Useful for comparing regions of different sizes.
            - **Evenness**: Shows how evenly the individuals are distributed across species. Higher evenness means no single species dominates the community.

            These metrics together give a **holistic view of the ecological diversity** of the selected area. High species richness combined with high evenness generally indicates a healthy and resilient ecosystem.  
            """)

            #--------------------
            # NDVI rating
            #--------------------
            if area_km2>100:
                scale_adjusted = 100
            elif area_km2>50:
                scale_adjusted = 30
            elif area_km2>10:
                scale_adjusted = 20
            else:
                scale_adjusted = 10

            ndvi_rating = get_ndvi_rating_summary(ndvi_map, aoi_ee, scale_adjusted)
            total_pix = sum(ndvi_rating.values())
            good_vegetation = (
                ndvi_rating.get("3", 0) + 
                ndvi_rating.get("4", 0) +
                ndvi_rating.get("5", 0)
            )

            bad_vegetation = (
                ndvi_rating.get("1", 0) +
                ndvi_rating.get("2", 0)
            )                
            bad_vegetation_perc = bad_vegetation/total_pix*100
            bad_vegetation_ha = bad_vegetation * scale_adjusted**2 / 10**4

            # --- Fill the placeholder once data is ready ---
            text_placeholder.markdown(f"{bad_vegetation_ha:,.0f} ha ({bad_vegetation_perc:.2f}%) of the forest land show signs of degradation or vegetation stress compared to the average NDVI of the last 10 years.")

        except Exception as e:
            st.sidebar.error(f"Error: {e}")


