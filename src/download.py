"""Fetch Toronto address points through address-vault (the central tiered store).

The tracker no longer downloads the City portal directly; it pulls the dataset's
latest snapshot via address-vault and returns the same ``(status, path, headers)``
contract the importer expects. Requires ADDRESSVAULT_DIR set to the vault folder.
"""

SLUG = "toronto"

# Kept for the vault Source registration / documentation; the actual download is
# performed by address-vault, not here.
DATASET_URL = (
    "https://ckan0.cf.opendata.inter.prod-toronto.ca/dataset/"
    "abedd8bc-e3dd-4d45-8e69-79165a76e4fa/resource/"
    "b1c2ab72-dfe7-4b29-8550-6d1cfaa61733/download/address-points-4326.geojson"
)


def _vault():
    from addressvault import Source, Vault
    v = Vault()  # uses ADDRESSVAULT_DIR
    if not v.cat.get_source(SLUG):  # self-register if the vault hasn't seen it
        v.add_source(Source(slug=SLUG, provider="City of Toronto",
                            data_url=DATASET_URL, access="static", format="geojson"))
    return v


def download(force=False):
    """Pull today's Toronto snapshot via address-vault.

    Returns ``(status, data, extra)``:
      ``("DOWNLOADED", <geojson path>, {"Last-Modified": ..., "Content-Length": ...})``
      ``("SKIPPED", <reason>, None)`` when the vault deduped today against a prior day.
    """
    from addressvault import Archived
    v = _vault()
    snap = v.pull(SLUG, force=force)

    # Vault content-dedup: today's bytes match an earlier day -> nothing new to import.
    if snap.unchanged_since and not force:
        return "SKIPPED", f"Content unchanged since {snap.unchanged_since}.", None

    try:
        path = v.path(SLUG, "latest")
    except Archived:  # latest resolved to a cold canonical -> thaw it back to hot
        v.thaw(SLUG, v.snapshot(SLUG, "latest").date)
        path = v.path(SLUG, "latest")

    row = v.cat.get_snapshot(SLUG, snap.date)
    headers = {
        "Last-Modified": row["src_last_modified"],
        "Content-Length": row["src_content_length"],
    }
    return "DOWNLOADED", path, headers
