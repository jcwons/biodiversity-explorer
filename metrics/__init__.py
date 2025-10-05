import ee
import numpy as np

# Initialize Earth Engine once
ee.Initialize()

# Landcover class legend
landcover_classes = {
    10: "Tree cover",
    20: "Shrubland",
    30: "Grassland",
    40: "Cropland",
    50: "Built-up",
    60: "Bare / sparse vegetation",
    70: "Snow and ice",
    80: "Permanent water bodies",
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
        "top_5_landcover": get_top_5_landcover(counts)
    }
