# Toronto Address Import - OSM Preparation

This document outlines the methodology and tools developed to prepare City of Toronto Open Data address points for potential import into OpenStreetMap.

## 1. Methodology

The goal is to identify addresses present in the City's dataset that are **missing** from OpenStreetMap, while avoiding duplicates and respecting existing OSM data.

### Phase 1: Data Extraction
*   **Source**: `addresses.db` (SCD Type 2 history)
*   **Logic**: Extract all records valid in the most recent snapshot.
*   **Script**: `src/analyze.py` (verifies quality of extracted data).

### Phase 2: OSM Data Retrieval
*   **Source**: Overpass API
*   **Bounding Box**: Approx. Toronto (43.5810, -79.6392, 43.8555, -79.1169)
*   **Script**: `src/osm.py`
*   **Data**: Fetches `node`, `way`, and `relation` elements with `addr:housenumber`.

### Phase 3: Conflation
*   **Script**: `src/conflate.py`
*   **Logic**:
    1.  **Normalization**: Street names are normalized (e.g., "ST" -> "STREET", "West" -> "W") to ensure accurate comparison.
    2.  **Spatial Indexing**: Uses a custom Grid Index for fast neighbor lookups.
    3.  **Matching**:
        *   Checks for OSM addresses within **30 meters** of a City address.
        *   If House Number matches AND Normalized Street Name matches -> **MATCH**.
        *   If Location matches but details differ -> **CONFLICT** (flagged for review).
        *   If NO match found -> **MISSING** (Candidate for import).

### Phase 4: Candidate Generation
*   **Script**: `src/osm_export.py`
*   **Output**: `data/candidates.osm`
*   **Format**: JOSM-compatible XML.
*   **Tags**:
    *   `addr:housenumber`
    *   `addr:street`
    *   `addr:city` = "Toronto"
    *   `addr:province` = "ON"
    *   `source` = "City of Toronto Open Data"

## 2. Preliminary Results (Feb 2026)

*   **Total City Addresses**: ~525,000
*   **Existing OSM Addresses**: ~256,000
*   **Matched**: 136,256
*   **Conflicts**: 33,471
*   **New Candidates**: **355,630**

## 3. Usage

1.  **Fetch OSM Data**:
    ```bash
    python src/osm.py
    ```

2.  **Run Conflation**:
    ```bash
    python src/conflate.py
    ```
    (Generates `data/candidates.json`)

3.  **Generate OSM File**:
    ```bash
    python src/osm_export.py
    ```
    (Generates `data/candidates.osm`)

## 4. Next Steps

1.  **Community Consultation**: Share `candidates.osm` and this methodology with the local OSM community.
2.  **Manual Review**: Use JOSM to spot-check the candidates against imagery.
3.  **Import Plan**: Once approved, upload in small chunks by neighborhood.
