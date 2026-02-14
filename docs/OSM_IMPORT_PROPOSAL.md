# Import/Toronto Address Import 2026

**This is a draft proposal for the import of City of Toronto Address Points.**

> [!IMPORTANT]
> This import is currently in the **Proposal** stage. Community feedback is welcome on the [Imports mailing list](https://lists.openstreetmap.org/listinfo/imports).

## 1. Description
The goal of this project is to import missing address points from the [City of Toronto Open Data](https://open.toronto.ca/dataset/address-points-municipal-toronto-one-address-repository/) into OpenStreetMap.

Toronto has approximately **525,000** official address points. Currently, OpenStreetMap covers roughly **256,000** addresses. This import aims to fill the gap of ~355,000 missing addresses while strictly preserving existing high-quality OSM data.

## 2. Data

### 2.1 Data Source
*   **Dataset**: [Address Points (Municipal) - Toronto One Address Repository](https://open.toronto.ca/dataset/address-points-municipal-toronto-one-address-repository/)
*   **Publisher**: City of Toronto
*   **Format**: GeoJSON / CSV
*   **Update Frequency**: Daily (Source) / One-time import (This proposal)
*   **Excluded Data**: Postal codes are **not included** in the source dataset and will not be imported. Deriving them from proprietary sources (Canada Post) is not permitted.

### 2.2 License
*   **License**: [Open Government Licence – Toronto](https://open.toronto.ca/open-data-license/)
*   **ODbL Compatibility**: Validated. The Open Government Licence - Toronto is compatible with ODbL. The City of Toronto requires attribution, which will be provided via the `source` tag and wiki documentation.

## 3. Import Type
*   **Type**: One-time import (with potential for future updates via separate process).
*   **Methodology**: "Slow Import" / Community Review.
*   **Tools**: Custom Python scripts for conflation + JOSM for manual upload.

## 4. Data Preparation

### 4.1. Tag Mapping
Mapping City of Toronto fields to OSM tags:

| City Field | OSM Tag | Example |
| matches | matches | matches |
| `ADDRESS_NUMBER` + `LO_NUM_SUF` | `addr:housenumber` | `123`, `10A` |
| `LINEAR_NAME_FULL` | `addr:street` | `Yonge Street` |
| (Static) | `addr:city` | `Toronto` |
| (Static) | `addr:province` | `ON` |
| (Static) | `source` | `City of Toronto Open Data` |
| (*Missing*) | `addr:postcode` | *Not Imported* |

### 4.2. Conflation Logic
We use a conservative conflation algorithm to avoid duplicates:
1.  **Normalization**: Street coordinates are normalized (e.g. `St.` -> `Street`, `W` -> `West`) to align with OSM conventions.
2.  **Spatial Match**: We check for any existing OSM address node/way/relation within **30 meters**.
3.  **Attribute Match**:
    *   If **Number** AND **Street** match: **IGNORE** (Already exists).
    *   If **Location** matches but attributes differ: **SKIP** (Flag as Conflict for manual review).
    *   If **No match** within 30m: **IMPORT CANDIDATE**.

*Preliminary Stats*:
*   Matched: 136k
*   Conflicts: 33k
*   **Import Candidates**: 355k

## 5. Data Merge Workflow

1.  **Generate**: Run `src/osm_export.py` to generate `candidates.osm`.
2.  **Divide**: Split the dataset by Ward or Neighbourhood to create manageable chunks.
3.  **Review**:
    *   Open chunk in JOSM.
    *   Download existing OSM data for the area.
    *   Validate against satellite imagery (Bing/Esri).
    *   Run JOSM Validator to catch overlapping nodes.
    *   *(Optional)*: Manually add postal codes if known from survey/knowledge.
4.  **Upload**: Commit with comment: `Toronto Address Import 2026 #TorontoAddresses`.

## 6. Maintenance
This is a one-time import. Future updates will be handled by re-running the conflation analysis to generate "New Address" reports for the local community to map manually.

## 7. Team
*   **Lead**: skfd
*   **Support**: local Toronto OSM community.
