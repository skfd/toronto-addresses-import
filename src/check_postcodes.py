import json

def check_postal_coverage():
    try:
        with open("data/osm_current.json", "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print("data/osm_current.json not found.")
        return

    total = 0
    with_postcode = 0
    
    for el in data:
        if "tags" in el and "addr:housenumber" in el["tags"]:
            total += 1
            if "addr:postcode" in el["tags"]:
                with_postcode += 1

    print(f"Total OSM Addresses: {total}")
    print(f"With Postal Code: {with_postcode} ({with_postcode/total*100:.1f}%)")

if __name__ == "__main__":
    check_postal_coverage()
