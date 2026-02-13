"""Create test CSV snapshots from the sample GeoJSON."""
import json
import csv
import os
import re

os.makedirs("data", exist_ok=True)

with open("_sample_data/sample_WGS84.geojson", "r") as f:
    text = f.read()

# Fix trailing commas (invalid JSON in the sample file)
text = re.sub(r",\s*\]", "]", text)
text = re.sub(r",\s*\}", "}", text)
data = json.loads(text)

props = list(data["features"][0]["properties"].keys())
fieldnames = props + ["LONGITUDE", "LATITUDE"]

# Snapshot 1: direct conversion
with open("data/sample-snapshot-1.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    for feat in data["features"]:
        row = dict(feat["properties"])
        coords = feat["geometry"]["coordinates"][0]
        row["LONGITUDE"] = coords[0]
        row["LATITUDE"] = coords[1]
        writer.writerow(row)

print(f"Snapshot 1: {len(data['features'])} rows")

# Snapshot 2: with modifications
with open("data/sample-snapshot-1.csv", "r", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

# Modify row 0
rows[0]["ADDRESS_FULL"] = "15A Muskoka Ave"
rows[0]["ADDRESS_NUMBER"] = "15A"
rows[0]["LO_NUM_SUF"] = "A"

# Modify row 4
rows[4]["WARD_NAME"] = "Etobicoke-Centre"

# Remove row 2
removed = rows.pop(2)
print(f"Removed: {removed['ADDRESS_FULL']}")

# Add a new row
new_row = dict(rows[0])
new_row["ADDRESS_POINT_ID"] = "99999999"
new_row["ADDRESS_FULL"] = "100 Test St"
new_row["ADDRESS_NUMBER"] = "100"
new_row["LINEAR_NAME_FULL"] = "Test St"
new_row["LONGITUDE"] = "-79.4"
new_row["LATITUDE"] = "43.65"
rows.append(new_row)

with open("data/sample-snapshot-2.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

print(f"Snapshot 2: {len(rows)} rows")
print("Done.")
