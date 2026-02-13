# Toronto Address Change Tracker

Tracks daily changes to the City of Toronto's [Address Points](https://open.toronto.ca/dataset/address-points-municipal-toronto-one-address-repository/) dataset — over 525,000 addresses across the city.

Every day, the City publishes a fresh snapshot of all address points. This tool downloads each snapshot, stores it, and produces a diff report showing which addresses were added, removed, or modified since the last run.

## Why?

The City of Toronto doesn't publish historical versions of this dataset — each daily update replaces the previous one. Without tracking changes over time, there's no way to know when an address appeared, disappeared, or was corrected.

This project fills that gap.

## Reports

Browse the latest change report on the [project page](https://skfd.github.io/toronto-addresses-import/).
