import json
from db import get_active_addresses, TRACKED_COLUMNS

def analyze():
    print("Fetching active addresses...")
    addresses = get_active_addresses()
    print(f"Total active addresses: {len(addresses):,}")
    
    if not addresses:
        print("No addresses found.")
        return

    # Check for potential issues
    missing_coords = 0
    missing_number = 0
    missing_street = 0
    
    sample = addresses[:5]
    print("\nSample records:")
    for addr in sample:
        print(f" - {addr['address_full']} ({addr['latitude']}, {addr['longitude']})")
        
    print("\nData Quality Scan:")
    for addr in addresses:
        if not addr['latitude'] or not addr['longitude']:
            missing_coords += 1
        if not addr['address_number']:
            missing_number += 1
        if not addr['linear_name_full']:
            missing_street += 1
            
    print(f"  Missing Coords: {missing_coords}")
    print(f"  Missing Number: {missing_number}")
    print(f"  Missing Street: {missing_street}")

if __name__ == "__main__":
    analyze()
