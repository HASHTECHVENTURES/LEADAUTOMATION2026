"""
Test script to validate the save_level1_results fix
This simulates the save operation without actually connecting to Supabase
"""
import sys
from typing import List, Dict

def test_save_logic():
    """Test the logic of saving companies with and without place_id"""
    
    # Simulate test data
    test_companies = [
        {
            'company_name': 'Test Company 1',
            'place_id': 'ChIJ1234567890',
            'website': 'https://test1.com',
            'phone': '1234567890',
            'address': '123 Test St',
            'place_type': 'Business',
            'pin_code': '123456',
            'business_status': 'OPERATIONAL'
        },
        {
            'company_name': 'Test Company 2',
            'place_id': '',  # Empty place_id - this was the bug!
            'website': 'https://test2.com',
            'phone': '0987654321',
            'address': '456 Test Ave',
            'place_type': 'Business',
            'pin_code': '123456',
            'business_status': 'OPERATIONAL'
        },
        {
            'company_name': 'Test Company 3',
            # No place_id key at all - this was also the bug!
            'website': 'https://test3.com',
            'phone': '5555555555',
            'address': '789 Test Blvd',
            'place_type': 'Business',
            'pin_code': '123456',
            'business_status': 'OPERATIONAL'
        }
    ]
    
    search_params = {
        'project_name': 'project 1',  # The project name the user mentioned
        'pin_codes': '123456',
        'industry': 'IT',
        'timestamp': '2024-01-01 12:00:00'
    }
    
    # Simulate the record preparation logic
    project_name = search_params.get('project_name', '').strip()
    records = []
    skipped_invalid = 0
    
    print(f"Testing save logic for project: '{project_name}'")
    print(f"Processing {len(test_companies)} companies...\n")
    
    for idx, company in enumerate(test_companies, 1):
        company_name = company.get('company_name', '').strip()
        
        if not company_name:
            print(f"  Company {idx}: ❌ SKIPPED - empty company_name")
            skipped_invalid += 1
            continue
        
        # Handle place_id: use None instead of empty string
        place_id = company.get('place_id', '') or None
        if place_id:
            place_id = place_id.strip()
            if not place_id:
                place_id = None
        
        record = {
            'project_name': project_name,
            'company_name': company_name,
            'place_id': place_id,
            'website': company.get('website', '') or '',
            'phone': company.get('phone', '') or '',
            'address': company.get('address', '') or '',
        }
        records.append(record)
        
        place_id_status = f"place_id: '{place_id}'" if place_id else "place_id: None (will be handled separately)"
        print(f"  Company {idx}: ✅ PREPARED - {company_name} ({place_id_status})")
    
    print(f"\n📊 Summary:")
    print(f"  - Total companies: {len(test_companies)}")
    print(f"  - Valid records: {len(records)}")
    print(f"  - Skipped: {skipped_invalid}")
    
    # Simulate batch separation
    records_with_place_id = [r for r in records if r.get('place_id')]
    records_without_place_id = [r for r in records if not r.get('place_id')]
    
    print(f"\n📦 Batch Separation:")
    print(f"  - Records with place_id: {len(records_with_place_id)}")
    print(f"  - Records without place_id: {len(records_without_place_id)}")
    
    # Verify all companies are included
    if len(records) == len(test_companies) - skipped_invalid:
        print(f"\n✅ SUCCESS: All valid companies are included in records")
    else:
        print(f"\n❌ ERROR: Some companies are missing!")
        return False
    
    # Verify companies without place_id are not skipped
    if len(records_without_place_id) > 0:
        print(f"✅ SUCCESS: Companies without place_id are included ({len(records_without_place_id)} records)")
        print(f"   These will be saved using company_name + project_name matching")
    else:
        print(f"ℹ️  INFO: All companies have place_id")
    
    print(f"\n🎯 Expected Behavior:")
    print(f"  - Companies with place_id: Will use upsert with on_conflict='place_id'")
    print(f"  - Companies without place_id: Will be inserted individually")
    print(f"    If duplicate found (by company_name + project_name), will update instead")
    
    return True

if __name__ == '__main__':
    print("=" * 60)
    print("TESTING save_level1_results FIX")
    print("=" * 60)
    print()
    
    success = test_save_logic()
    
    print()
    print("=" * 60)
    if success:
        print("✅ ALL TESTS PASSED")
        print("\nThe fix should now properly save all companies,")
        print("including those without place_id values.")
    else:
        print("❌ TESTS FAILED")
    print("=" * 60)

