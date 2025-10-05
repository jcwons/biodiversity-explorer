import ee
import numpy as np

# Landcover class legend
def get_landcover_legend():
    return {
        10: "Tree cover",
        20: "Shrubland",
        30: "Grassland",
        40: "Cropland",
        50: "Built-up",
        60: "Sparse vegetation",
        70: "Snow and ice",
        80: "Permanent water",
        90: "Herbaceous wetland",
        95: "Mangroves",
        100: "Moss and lichen"
    }

landcover_classes = {
    10: "Tree cover",
    20: "Shrubland",
    30: "Grassland",
    40: "Cropland",
    50: "Built-up",
    60: "Sparse vegetation",
    70: "Snow and ice",
    80: "Permanent water",
    90: "Herbaceous wetland",
    95: "Mangroves",
    100: "Moss and lichen"
}

# --------------------
# Biodiversity Indices
# --------------------

def get_shannon_index(counts: dict):
    total = sum(counts.values())
    proportions = [count / total for count in counts.values()]
    return -sum(p * np.log(p) for p in proportions if p > 0)

def get_simpson_index(counts: dict):
    total = sum(counts.values())
    proportions = [count / total for count in counts.values()]
    return 1 - sum(p ** 2 for p in proportions)

def get_evenness_index(counts: dict):
    number_of_classes = len(counts)
    shannon = get_shannon_index(counts)
    if number_of_classes > 1:
        return shannon / np.log(number_of_classes)
    return 0

def get_natural_habitat_fraction(counts: dict):
    natural_classes = [10, 20, 30, 90, 95, 100]
    natural_count = sum(counts.get(str(cls), 0) for cls in natural_classes)
    total = sum(counts.values())
    return natural_count / total if total > 0 else 0

def get_anthropogenic_habitat_fraction(counts: dict):
    anthropogenic_classes = [40, 50, 60, 70, 80]
    anthro_count = sum(counts.get(str(cls), 0) for cls in anthropogenic_classes)
    total = sum(counts.values())
    return anthro_count / total if total > 0 else 0

def get_top_5_landcover(counts: dict):
    top_5 = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:5]
    total = sum(counts.values())
    return [(landcover_classes[int(cls)], count, (count / total) * 100) for cls, count in top_5]

# --------------------
# Wrapper Function
# --------------------

def get_landcover_metrics(aoi_ee):
    # Fetch WorldCover 2021
    wc = ee.Image("ESA/WorldCover/v200/2021").clip(aoi_ee)

    # Pixel counts per class
    landcover_counts = wc.reduceRegion(
        reducer=ee.Reducer.frequencyHistogram(),
        geometry=aoi_ee,
        scale=10,
        maxPixels=1e13
    ).getInfo()

    counts = landcover_counts.get('Map', {})

    return {
        "shannon_index": get_shannon_index(counts),
        "simpson_index": get_simpson_index(counts),
        "evenness_index": get_evenness_index(counts),
        "natural_habitat_fraction": get_natural_habitat_fraction(counts),
        "anthropogenic_habitat_fraction": get_anthropogenic_habitat_fraction(counts),
        "top_5_landcover": get_top_5_landcover(counts),
        
    }, wc

# --------------------
# NDVI
# --------------------
# -----------------------------
# USER INPUT
# -----------------------------

cur_end = '2025-08-31' # change this to today
cur_start = '2025-06-01' # change this to today minus 3 months

hist_start_year = 2018
hist_end_year = 2024
scale = 20

def add_indices(img):
    ndvi = img.normalizedDifference(['B8', 'B4']).rename('NDVI')
    evi = img.expression(
        '2.5 * ((NIR - RED) / (NIR + 6*RED - 7.5*BLUE + 1))',
        {'NIR': img.select('B8'),
         'RED': img.select('B4'),
         'BLUE': img.select('B2')}
    ).rename('EVI')
    return img.addBands([ndvi, evi])

def get_ndvi_rating_map(aoi):
    
    worldcover = ee.ImageCollection('ESA/WorldCover/v100').first().select('Map')
    forest_mask = worldcover.eq(10)  # forest class


    # Current NDVI composite
    s2_cur = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
            .filterDate(cur_start, cur_end)
            .filterBounds(aoi)
            .map(add_indices)
            .median()
            )

    # Historical NDVI percentiles (seasonal)
    s2_hist_seasonal = ee.ImageCollection([])
    for year in range(hist_start_year, hist_end_year+1):
        start = f'{year}-{cur_start[5:]}'
        end = f'{year}-{cur_end[5:]}'
        imgs = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                .filterDate(start, end)
                .filterBounds(aoi)
                .map(add_indices))
        s2_hist_seasonal = s2_hist_seasonal.merge(imgs)

    percentiles = [25, 35, 70, 90]
    hist_percentiles_img = s2_hist_seasonal.select('NDVI').reduce(
        ee.Reducer.percentile(percentiles)
    ).rename(['NDVI_p25', 'NDVI_p35', 'NDVI_p70', 'NDVI_p90'])

    # Historical mean and std for anomaly
    hist_mean = s2_hist_seasonal.select('NDVI').mean()
    hist_std = s2_hist_seasonal.select('NDVI').reduce(ee.Reducer.stdDev())


    # NDVI percentile rating (1-5)
    ndvi_rating = s2_cur.expression(
        'ndvi >= p90 ? 5 :' 
        'ndvi >= p70 ? 4 :'
        'ndvi >= p35 ? 3 :'
        'ndvi >= p25 ? 2 : 1',
        {
            'ndvi': s2_cur.select('NDVI'),
            'p90': hist_percentiles_img.select('NDVI_p90'),
            'p70': hist_percentiles_img.select('NDVI_p70'),
            'p35': hist_percentiles_img.select('NDVI_p35'),
            'p25': hist_percentiles_img.select('NDVI_p25')
        }
    ).rename('NDVI_rating')

  # Apply mask to only keep forest area
    ndvi_rating_forest = ndvi_rating.updateMask(forest_mask)
    return ndvi_rating_forest

# -----------------------------
# Get NDVI rating summary
# -----------------------------

def get_ndvi_rating_summary(ee_image, aoi_ee, scale):
    landcover_counts = ee_image.reduceRegion(
        reducer=ee.Reducer.frequencyHistogram(),
        geometry=aoi_ee,
        scale=scale,
        maxPixels=1e13,
        tileScale=4  # increases parallelization
    ).getInfo()
    return landcover_counts['NDVI_rating']

""""
def get_ndvi_rating_summary(rating_img, aoi, scale):
    pixel_area = ee.Image.pixelArea()
    areas = []
    for r in [1,2,3,4,5]:
        mask_r = rating_img.eq(r)
        area_r = pixel_area.updateMask(mask_r).reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=aoi,
            scale=scale,
            maxPixels=1e13,
            bestEffort=True
        ).get('area')
        areas.append(ee.Number(area_r))
    
    areas_list = ee.List(areas)
    total_area = ee.Number(areas_list.reduce(ee.Reducer.sum()))
    fractions = areas_list.map(lambda a: ee.Number(a).divide(total_area).multiply(100))
    
        # Mean rating
    mean_rating = rating_img.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=aoi,
        scale=scale,
        maxPixels=1e13
    ).get('NDVI_rating')
     

    # Convert to Python numbers
    areas_py = [a.getInfo()/10000 for a in areas]  # ha
    total_area_py = total_area.getInfo()/10000
    fractions_py = fractions.getInfo()  # <- fixed
    mean_rating_py = mean_rating.getInfo()

    return {
        'total_ha': total_area_py,
        'area_by_rating_ha': areas_py,
        'area_by_rating_pct': fractions_py
    }
"""

# Print forest summary in a readable format
def print_summary(summary):
    total_area_ha = summary['total_ha']  # convert m^2 to hectares
    fractions = summary['area_by_rating_pct']
    #mean_rating = summary['mean_rating']
    
    print(f"Total area: {total_area_ha:.2f} ha")
    #print(f"Mean NDVI rating: {mean_rating:.2f} (1=Very poor, 5=Excellent)")
    for i, frac in enumerate(fractions, start=1):
        print(f"Area with rating {i}: {frac:.2f}%")
    good_excellent_pct = fractions[3] + fractions[4]
    print(f"Area rated Good or Excellent (4 or 5): {good_excellent_pct:.2f}%")
    print()

# -----------------------------
### Data Visualisation
# -----------------------------

import plotly.express as px

def create_pie_chart(values, size=400):
    """
    Create a styled Plotly pie chart.

    Args:
        values (list): List of numeric values.
        labels (list): List of category labels.
        size (int): Size of the chart (default=400).

    Returns:
        fig (plotly.graph_objs.Figure): Configured pie chart.
    """
    # Labels
    labels = ['Natural Habitat', 'Anthropogenic Habitat']
    # Create pie chart
    fig = px.pie(
        names=labels,
        values=values,
        hole=0.5,
        color_discrete_sequence=["#2ecc71", "#e74c3c", "#3498db", "#f1c40f"]  # supports >2 categories
    )

    # Update hover template
    fig.update_traces(
        hovertemplate="<b>%{label}</b><br>Percentage: %{percent}",
        textinfo="percent"
    )

    # Update layout (size & style)
    fig.update_layout(
        width=size,
        height=size,
        showlegend= False,
        margin=dict(t=40, b=20, l=20, r=20),
        plot_bgcolor="white",
        paper_bgcolor="white"
    )

    return fig

import plotly.graph_objects as go

def create_index_bar(index_name, value, min_val=0, max_val=1, size=(500, 80),
                     bar_color="#ff4b5c", hover_text=None):
    """
    Create a sleek horizontal bar visualizing an index value within a range.
    """
    normalized = (value - min_val) / (max_val - min_val)

    # If hover_text is not provided, use default
    if hover_text is None:
        hover_text = f"<b>{index_name}</b><br>Value: {value:.2f}<extra></extra>"

    fig = go.Figure()

    # Background bar
    fig.add_trace(go.Bar(
        x=[1],
        y=[index_name],
        orientation="h",
        marker=dict(color="#2c2c2c"),
        showlegend=False,
        hoverinfo="skip"
    ))

    # Value bar
    fig.add_trace(go.Bar(
        x=[normalized],
        y=[index_name],
        orientation="h",
        marker=dict(color=bar_color),
        showlegend=False,
        hovertemplate=hover_text
    ))

    # Text positioned just outside the background bar
    fig.add_trace(go.Scatter(
        x=[1.02],
        y=[index_name],
        text=[f"{value:.2f}"],
        mode="text",
        textposition="middle right",
        textfont=dict(color="white", size=14),
        showlegend=False,
        hoverinfo="skip"
    ))

    fig.update_layout(
        barmode="overlay",
        xaxis=dict(visible=False, range=[0, 1.2]),  # extra space for value
        yaxis=dict(
            visible=True,
            showticklabels=True,
            tickfont=dict(color="white", size=14)
        ),
        plot_bgcolor="#1e1e1e",
        paper_bgcolor="#1e1e1e",
        width=size[0],
        height=size[1],
        margin=dict(t=10, b=10, l=120, r=80)  # fixed left and right space
    )


    return fig
