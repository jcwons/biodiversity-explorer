import requests
from collections import Counter
from datetime import date, timedelta
import math

def get_wkt_from_aoi_ee(aoi_ee):
    # Add 10 km buffer (10,000 meters)
    buffered = aoi_ee.buffer(10000)

    # Simplify to reduce number of vertices (optional, helps keep WKT shorter)
    buffered = buffered.simplify(100)  # tolerance in meters

    # Extract coordinates
    coords = buffered.coordinates().getInfo()[0]

    # Build WKT string
    coord_str = ", ".join([f"{x} {y}" for x, y in coords])
    wkt = f"POLYGON(({coord_str}))"
    return wkt

def get_gbif_sample(aoi_ee, n_records=10000):
    """
    Fetch a sample of GBIF occurrences within the AOI (polygon WKT) up to n_records.
    """
    geometry_wkt = get_wkt_from_aoi_ee(aoi_ee)
    per_page = 300
    pages = n_records // per_page + 1
    occurrences = []

    # Today's date
    end_date = date.today()
    # One year ago
    start_date = end_date - timedelta(days=365)

    # Format as strings (YYYY-MM-DD)
    end_date_str = end_date.isoformat()
    start_date_str = start_date.isoformat()

    for i in range(pages):
        offset = i * per_page
        url = "https://api.gbif.org/v1/occurrence/search"
        params = {
            "geometry": geometry_wkt,
            "limit": per_page,
            "offset": offset,
            "eventDate": f"{start_date},{end_date}",
            "hasCoordinate": True
        }
        r = requests.get(url, params=params)
        data = r.json()
        occurrences.extend(data["results"])
        if len(data["results"]) < per_page:
            break  # no more results

    return occurrences[:n_records]



def get_number_of_occurrences(aoi_ee):
    # Today's date
    end_date = date.today()

    # One year ago
    start_date = end_date - timedelta(days=365)

    # Format as strings (YYYY-MM-DD)
    end_date_str = end_date.isoformat()
    start_date_str = start_date.isoformat()

    geometry_wkt = get_wkt_from_aoi_ee(aoi_ee)
    url = "https://api.gbif.org/v1/occurrence/search"
    params = {
        "geometry": geometry_wkt,
        "eventDate": f"{start_date},{end_date}",
        "limit": 0  # we only want the count
    }
    response = requests.get(url, params=params)
    data = response.json()
    return data["count"]


def get_biodiversity_indices(occurrences):
    """
    Calculate common biodiversity indices from a GBIF occurrence sample.

    Args:
        occurrences (list of dict): Each dict must contain a 'species' key.

    Returns:
        dict: biodiversity indices:
            - species_richness
            - shannon_index
            - simpson_index
            - evenness
            - berger_parker_dominance
    """
    # Extract species names
    species_list = [occ['species'] for occ in occurrences if 'species' in occ]

    if not species_list:
        return {
            "species_richness": 0,
            "shannon_index": 0,
            "simpson_index": 0,
            "evenness": 0,
            "berger_parker_dominance": 0
        }

    # Count species occurrences
    species_counts = Counter(species_list)
    N = sum(species_counts.values())
    S = len(species_counts)  # species richness

    # Shannon index
    shannon = -sum((n/N) * math.log(n/N) for n in species_counts.values())

    # Simpson index (1-D)
    simpson = 1 - sum((n/N)**2 for n in species_counts.values())

    # Evenness
    evenness = shannon / math.log(S) if S > 1 else 0

    # Berger-Parker dominance
    berger_parker = max(species_counts.values()) / N

    return {
        "species_richness": S,
        "shannon_index": shannon,
        "simpson_index": simpson,
        "evenness": evenness,
        "berger_parker_dominance": berger_parker
    }
