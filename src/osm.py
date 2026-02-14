import requests
import json
import os
import time

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Approx Toronto Bounding Box
# min_lat, min_lon, max_lat, max_lon
BBOX = (43.5810, -79.6392, 43.8555, -79.1169)

def _build_query(bbox, check_count=False):
    bbox_str = f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}"
    timeout = 180 if not check_count else 30
    
    # We want nodes, ways, and relations with addr:housenumber
    # For ways/relations, we want the center point for easier conflation initially
    
    q = f"[out:json][timeout:{timeout}];"
    q += f"("
    q += f'  node["addr:housenumber"]({bbox_str});'
    q += f'  way["addr:housenumber"]({bbox_str});'
    q += f'  relation["addr:housenumber"]({bbox_str});'
    q += f");"
    
    if check_count:
        q += "out count;"
    else:
        q += "out center;" # get center for ways/rels
        
    return q

def count_osm_addresses(bbox=BBOX):
    query = _build_query(bbox, check_count=True)
    print("Checking object count from Overpass...")
    try:
        resp = requests.post(OVERPASS_URL, data={"data": query})
        resp.raise_for_status()
        data = resp.json()
        
        total = 0
        if "elements" in data:
            # Overpass count output structure
            for el in data["elements"]:
                if "tags" in el and "total" in el["tags"]:
                    total += int(el["tags"]["total"])
                # Sometimes it returns id:0 with tags: {nodes: X, ways: Y, ...}
                if el.get("type") == "count":
                    total += int(el["tags"].get("nodes", 0))
                    total += int(el["tags"].get("ways", 0))
                    total += int(el["tags"].get("relations", 0))
        return total
    except Exception as e:
        print(f"Error fetching count: {e}")
        return -1

def fetch_osm_addresses(bbox=BBOX, out_file="data/osm_current.json"):
    query = _build_query(bbox, check_count=False)
    print(f"Fetching data from Overpass (bbox={bbox})...")
    
    try:
        resp = requests.post(OVERPASS_URL, data={"data": query})
        resp.raise_for_status()
        data = resp.json()
        
        elements = data.get("elements", [])
        print(f"Fetched {len(elements)} elements.")
        
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(elements, f, indent=2)
            
        return elements
    except Exception as e:
        print(f"Error fetching data: {e}")
        return []

if __name__ == "__main__":
    out_file = "data/osm_current.json"
    if os.path.exists(out_file):
        print(f"{out_file} already exists. Skipping download.")
        # Optional: load and count to verify
    else:
        c = count_osm_addresses()
        print(f"Estimated address objects in Toronto: {c}")
        if c > 0:
            print("Starting download...")
            fetch_osm_addresses(out_file=out_file)
            print("Download complete.")
