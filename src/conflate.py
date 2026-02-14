import json
import math
import re
from collections import defaultdict
from db import get_active_addresses

# Config
MATCH_RADIUS_M = 30  # Search radius in meters
MAX_DIST_ACCEPT_M = 25 # Max distance to accept a match if tags align well

# Normalization map
STREET_SUFFIXES = {
    "STREET": "ST", "ROAD": "RD", "AVENUE": "AVE", "BOULEVARD": "BLVD",
    "DRIVE": "DR", "LANE": "LN", "COURT": "CT", "PLACE": "PL",
    "TERRACE": "TER", "CRESCENT": "CRES", "SQUARE": "SQ", "GATE": "GTE",
    "CIRCLE": "CIR", "WAY": "WAY", "TRAIL": "TRL", "PARKWAY": "PKWY",
    "HIGHWAY": "HWY", "EXPRESSWAY": "EXPY"
}
DIRS = {
    "NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W"
}

def normalize_street(name):
    if not name: return ""
    parts = name.upper().replace(".", "").split()
    out = []
    for p in parts:
        if p in STREET_SUFFIXES:
            out.append(STREET_SUFFIXES[p])
        elif p in DIRS:
            out.append(DIRS[p])
        else:
            out.append(p)
    return " ".join(out)

class GridIndex:
    def __init__(self, cell_size_deg=0.002): # ~220m
        self.grid = defaultdict(list)
        self.cell_size = cell_size_deg

    def _key(self, lat, lon):
        return (int(lat / self.cell_size), int(lon / self.cell_size))

    def add(self, item, lat, lon):
        key = self._key(lat, lon)
        self.grid[key].append((lat, lon, item))

    def query(self, lat, lon):
        """Return items in the 9 surrounding cells."""
        ck = self._key(lat, lon)
        candidates = []
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                k = (ck[0] + dx, ck[1] + dy)
                candidates.extend(self.grid[k])
        return candidates

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000 # meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def conflate():
    print("Loading City Data...")
    city_data = get_active_addresses()
    print(f"Loaded {len(city_data)} city addresses.")

    print("Loading OSM Data...")
    with open("data/osm_current.json", "r", encoding="utf-8") as f:
        osm_elements = json.load(f)
    print(f"Loaded {len(osm_elements)} OSM elements.")

    print("Building Spatial Index...")
    index = GridIndex()
    count = 0
    for el in osm_elements:
        tags = el.get("tags", {})
        if "addr:housenumber" not in tags:
            continue
            
        lat, lon = None, None
        if el["type"] == "node":
            lat, lon = el.get("lat"), el.get("lon")
        elif "center" in el:
            lat, lon = el["center"].get("lat"), el["center"].get("lon")
        
        if lat and lon:
            # Pre-normalize for faster checking
            el["_norm_street"] = normalize_street(tags.get("addr:street", ""))
            el["_norm_number"] = tags.get("addr:housenumber", "").upper()
            index.add(el, lat, lon)
            count += 1
            
    print(f"Indexed {count} OSM addresses.")

    results = {
        "MATCH": 0,
        "MISSING": 0,
        "CONFLICT": 0, # Location match but different number
        "REVIEW": 0 # Close match but unsure
    }
    
    missing_list = []

    print("Running Conflation...")
    for i, city in enumerate(city_data):
        if i % 10000 == 0:
            print(f"Processed {i}/{len(city_data)}...")
            
        c_lat = city["latitude"]
        c_lon = city["longitude"]
        if not c_lat or not c_lon:
            continue

        c_num = str(city["address_number"]).upper()
        c_street = city["linear_name_full"] # e.g. "Yonge St"
        # We might need to construct the street name if linear_name_full is null, but assuming it's populated for now
        # Actually verify schema: linear_name_full usually "Yonge St"
        if not c_street:
             # Fallback
             c_street = f"{city.get('linear_name', '')} {city.get('linear_name_type', '')}"
        
        c_norm_street = normalize_street(c_street)

        candidates = index.query(c_lat, c_lon)
        
        match_found = False
        best_candidate = None
        min_dist = float('inf')

        for o_lat, o_lon, osm in candidates:
            dist = haversine(c_lat, c_lon, o_lat, o_lon)
            if dist > MATCH_RADIUS_M:
                continue
            
            # Check address match
            # 1. Number match?
            if osm["_norm_number"] == c_num:
                # 2. Street match?
                if osm["_norm_street"] == c_norm_street:
                    match_found = True
                    break # Perfect match found
                
                # Check Levenshtein or fuzzy? For now exact normalized
                # Maybe suffix mismatch "AVE" vs "RD"
        
        if match_found:
            results["MATCH"] += 1
        else:
            # No perfect match found within radius
            # Is there *any* address at this location?
            # If there's an address at the same location but number is different -> CONFLICT?
            # Or if number is same but street is different?
            
            # Check for close spatial matches to label as CONFLICT or REVIEW
            # For simplistic "Missing" detection:
            # If NO address exists within 5m, it's likely MISSING.
            # If address exists within 5m but different data, it's CONFLICT/UPDATE.
            
            has_close_neighbor = False
            for o_lat, o_lon, osm in candidates:
                dist = haversine(c_lat, c_lon, o_lat, o_lon)
                if dist < 10: # Very close
                    has_close_neighbor = True
                    break
            
            if has_close_neighbor:
                results["CONFLICT"] += 1
            else:
                results["MISSING"] += 1
                missing_list.append(city)

    print("\nConflation Results:")
    print(f"  MATCH:    {results['MATCH']:,}")
    print(f"  MISSING:  {results['MISSING']:,} (Candidate for import)")
    print(f"  CONFLICT: {results['CONFLICT']:,} (Needs review)")
    
    # Save missing list
    with open("data/candidates.json", "w", encoding="utf-8") as f:
        # Convert non-serializable stuff if needed
        json.dump(missing_list, f, default=str)
    print(f"Saved {len(missing_list)} candidates to data/candidates.json")

if __name__ == "__main__":
    conflate()
