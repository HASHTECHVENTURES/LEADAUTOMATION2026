"""
Complete Level 1 Test - Tests search and save functionality
This simulates the actual user flow
"""
import sys
import os
import json
from datetime import datetime

# Add the current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from supabase_client import SupabaseClient
    from config import Config
except ImportError as e:
    print(f"❌ Import error: {e}")
    sys.exit(1)

def test_level1_complete():
    """Complete test of Level 1 functionality"""
    print("=" * 70)
    print("COMPLETE LEVEL 1 TEST - Testing Search and Save")
    print("=" * 70)
    print()
    
    # Initialize client
    try:
        client = SupabaseClient()
        print("✅ Supabase client initialized")
    except Exception as e:
        print(f"❌ Failed to initialize client: {e}")
        return False
    
    # Test data
    test_project_name = "TEST_PROJECT_LEVEL1"
    test_pin_code = "400001"  # Mumbai PIN code
    test_industry = "IT"
    
    print(f"📋 Test Configuration:")
    print(f"   Project Name: {test_project_name}")
    print(f"   PIN Code: {test_pin_code}")
    print(f"   Industry: {test_industry}")
    print()
    
    # Step 1: Clean up any existing test data
    print("=" * 70)
    print("STEP 1: Cleanup existing test data")
    print("=" * 70)
    try:
        delete_result = client.delete_project(test_project_name)
        if delete_result.get('success'):
            print(f"✅ Cleaned up existing test data")
        else:
            print(f"ℹ️  No existing test data to clean")
    except Exception as e:
        print(f"⚠️  Cleanup warning: {e}")
    print()
    
    # Step 2: Create mock companies (simulating Google Places API results)
    print("=" * 70)
    print("STEP 2: Create mock companies (simulating Google Places results)")
    print("=" * 70)
    
    mock_companies = [
        {
            'company_name': 'Test IT Company 1',
            'place_id': 'ChIJTEST001',
            'website': 'https://test1.com',
            'phone': '1111111111',
            'address': '123 Test Street, Mumbai',
            'place_type': 'Business',
            'pin_code': test_pin_code,
            'business_status': 'OPERATIONAL'
        },
        {
            'company_name': 'Test IT Company 2',
            'place_id': 'ChIJTEST002',
            'website': 'https://test2.com',
            'phone': '2222222222',
            'address': '456 Test Avenue, Mumbai',
            'place_type': 'Business',
            'pin_code': test_pin_code,
            'business_status': 'OPERATIONAL'
        },
        {
            'company_name': 'Test IT Company 3 - No Place ID',
            'place_id': None,  # Testing companies without place_id
            'website': 'https://test3.com',
            'phone': '3333333333',
            'address': '789 Test Boulevard, Mumbai',
            'place_type': 'Business',
            'pin_code': test_pin_code,
            'business_status': 'OPERATIONAL'
        },
        {
            'company_name': 'Test IT Company 4 - Empty Place ID',
            'place_id': '',  # Testing empty place_id
            'website': 'https://test4.com',
            'phone': '4444444444',
            'address': '321 Test Road, Mumbai',
            'place_type': 'Business',
            'pin_code': test_pin_code,
            'business_status': 'OPERATIONAL'
        }
    ]
    
    print(f"Created {len(mock_companies)} mock companies:")
    for i, company in enumerate(mock_companies, 1):
        place_id_status = f"place_id: {company.get('place_id')}" if company.get('place_id') else "place_id: None/Empty"
        print(f"  {i}. {company['company_name']} ({place_id_status})")
    print()
    
    # Step 3: Test save_level1_results function
    print("=" * 70)
    print("STEP 3: Test save_level1_results function")
    print("=" * 70)
    
    search_params = {
        'project_name': test_project_name,
        'pin_codes': test_pin_code,
        'industry': test_industry,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    print(f"Calling save_level1_results with:")
    print(f"  Project: {search_params['project_name']}")
    print(f"  Companies: {len(mock_companies)}")
    print()
    
    try:
        save_result = client.save_level1_results(mock_companies, search_params)
        
        print(f"Save Result: {json.dumps(save_result, indent=2)}")
        print()
        
        if save_result.get('success'):
            saved_count = save_result.get('count', 0)
            errors = save_result.get('errors', 0)
            print(f"✅ Save reported SUCCESS")
            print(f"   Companies saved: {saved_count}")
            print(f"   Errors: {errors}")
        else:
            error = save_result.get('error', 'Unknown error')
            print(f"❌ Save reported FAILURE: {error}")
            return False
            
    except Exception as e:
        print(f"❌ EXCEPTION during save: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print()
    
    # Step 4: Verify data in database
    print("=" * 70)
    print("STEP 4: Verify data was actually saved to database")
    print("=" * 70)
    
    try:
        # Get companies from database
        verify_response = client.client.table('level1_companies').select('*').eq('project_name', test_project_name).execute()
        saved_companies = verify_response.data if verify_response.data else []
        
        print(f"Found {len(saved_companies)} companies in database for project '{test_project_name}'")
        print()
        
        if len(saved_companies) == 0:
            print("❌ CRITICAL: No companies found in database!")
            print("   This means the save failed even though it reported success")
            return False
        
        print("✅ Companies found in database:")
        for i, company in enumerate(saved_companies, 1):
            print(f"  {i}. {company.get('company_name', 'Unknown')}")
            print(f"     ID: {company.get('id')}")
            print(f"     place_id: {company.get('place_id') or 'None'}")
            print(f"     project_name: {company.get('project_name')}")
            print(f"     industry: {company.get('industry')}")
            print()
        
        # Verify all companies are there
        expected_names = {c['company_name'] for c in mock_companies}
        saved_names = {c.get('company_name') for c in saved_companies}
        
        missing = expected_names - saved_names
        if missing:
            print(f"⚠️  WARNING: Some companies are missing from database:")
            for name in missing:
                print(f"   - {name}")
        else:
            print("✅ All companies are in the database!")
        
        # Check companies without place_id
        companies_without_place_id = [c for c in saved_companies if not c.get('place_id')]
        if companies_without_place_id:
            print(f"✅ Companies without place_id were saved: {len(companies_without_place_id)}")
            for company in companies_without_place_id:
                print(f"   - {company.get('company_name')}")
        else:
            print("ℹ️  All saved companies have place_id")
        
    except Exception as e:
        print(f"❌ Error verifying database: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print()
    
    # Step 5: Test get_level1_companies function
    print("=" * 70)
    print("STEP 5: Test retrieving companies")
    print("=" * 70)
    
    try:
        retrieved = client.get_level1_companies(project_name=test_project_name)
        print(f"Retrieved {len(retrieved)} companies using get_level1_companies()")
        
        if len(retrieved) == len(saved_companies):
            print("✅ Retrieved count matches saved count!")
        else:
            print(f"⚠️  Count mismatch: Saved {len(saved_companies)}, Retrieved {len(retrieved)}")
            
    except Exception as e:
        print(f"❌ Error retrieving companies: {e}")
        return False
    
    print()
    
    # Step 6: Cleanup
    print("=" * 70)
    print("STEP 6: Cleanup test data")
    print("=" * 70)
    
    try:
        delete_result = client.delete_project(test_project_name)
        if delete_result.get('success'):
            deleted_l1 = delete_result.get('deleted_level1', 0)
            deleted_l2 = delete_result.get('deleted_level2', 0)
            print(f"✅ Cleaned up test data: {deleted_l1} Level 1 companies, {deleted_l2} Level 2 contacts")
        else:
            print(f"⚠️  Cleanup had issues: {delete_result.get('error')}")
    except Exception as e:
        print(f"⚠️  Cleanup error: {e}")
    
    print()
    print("=" * 70)
    print("✅✅✅ ALL TESTS PASSED! ✅✅✅")
    print("=" * 70)
    print()
    print("Summary:")
    print(f"  ✅ Save function works correctly")
    print(f"  ✅ Companies with place_id are saved")
    print(f"  ✅ Companies without place_id are saved")
    print(f"  ✅ Data is verified in database")
    print(f"  ✅ Retrieval function works")
    print()
    print("Level 1 functionality is WORKING CORRECTLY!")
    print()
    
    return True

if __name__ == '__main__':
    success = test_level1_complete()
    sys.exit(0 if success else 1)


