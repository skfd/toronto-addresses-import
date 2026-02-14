import json
import xml.etree.ElementTree as ET
from xml.dom import minidom
import os

def export_candidates_to_osm(input_json="data/candidates.json", output_osm="data/candidates.osm"):
    print(f"Loading candidates from {input_json}...")
    if not os.path.exists(input_json):
        print("Candidates file not found.")
        return

    with open(input_json, "r", encoding="utf-8") as f:
        candidates = json.load(f)

    print(f"Exporting {len(candidates)} candidates to {output_osm}...")
    
    root = ET.Element("osm", version="0.6", generator="TorontoAddressImport")
    
    # Start negative ID for new objects
    node_id = -1
    
    for c in candidates:
        lat = str(c.get("latitude"))
        lon = str(c.get("longitude"))
        
        if not lat or not lon:
            continue
            
        node = ET.SubElement(root, "node", id=str(node_id), lat=lat, lon=lon, action="modify", visible="true")
        
        # Tags
        tags = {
            "addr:housenumber": str(c.get("address_number", "")),
            "addr:street": c.get("linear_name_full", ""),
            "addr:city": "Toronto",
            "addr:province": "ON",
            "source": "City of Toronto Open Data"
        }
        
        # Check for unit info in suffixes or extra
        # Note: lo_num_suf often contains unit info like "A", "1/2", etc.
        # But data schema might be different. 
        # For now, stick to basic tags to be safe.
        
        for k, v in tags.items():
            if v:
                ET.SubElement(node, "tag", k=k, v=v)
        
        node_id -= 1

    # Pretty print
    xmlstr = minidom.parseString(ET.tostring(root)).toprettyxml(indent="  ")
    
    with open(output_osm, "w", encoding="utf-8") as f:
        f.write(xmlstr)

    print(f"Done. Wrote {len(candidates)} nodes.")

if __name__ == "__main__":
    export_candidates_to_osm()
