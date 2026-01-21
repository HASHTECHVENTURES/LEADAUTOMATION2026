"""
Diagnostic script to test why saves are failing
Run this to identify the exact issue
"""
import sys
import os
from datetime import datetime

# Add the current directory to path to import modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from supabase_client import SupabaseClient
    from config import Config
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Make sure you're in the correct directory and all dependencies are installed")
    sys.exit(1)

def test_database_connection():
    """Test basic database connection"""
    print("=" * 60)
    print("TEST 1: Database Connection")
    print("=" * 60)
    try:
        client = SupabaseClient()
        print("✅ Supabase client initialized successfully")
        print(f"   URL: {client.url[:50]}...")
        print(f"   Using: {'SERVICE_ROLE' if Config.SUPABASE_SERVICE_ROLE_KEY else 'ANON'} key")
        return client
    except Exception as e:
        print(f"❌ Failed to initialize Supabase client: {e}")
        return None

def test_simple_insert(client):
    """Test a simple insert to see if we can write to the database"""
    print("\n" + "=" * 60)
    print("TEST 2: Simple Insert Test")
    print("=" * 60)
    
    test_record = {
        'project_name': 'DIAGNOSTIC_TEST',
        'company_name': 'Test Company Diagnostic',
        'website': 'https://test.com',
        'phone': '1234567890',
        'address': 'Test Address',
        'industry': 'IT',
        'place_type': 'Test',
        'pin_code': '123456',
        'pin_codes_searched': '123456',
        'search_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'place_id': None,  # Test with None place_id
        'business_status': 'OPERATIONAL',
        'selected_for_level2': False,
        'created_at': datetime.now().isoformat()
    }
    
    try:
        print(f"Attempting to insert test record...")
        print(f"  project_name: {test_record['project_name']}")
        print(f"  company_name: {test_record['company_name']}")
        print(f"  place_id: {test_record['place_id']}")
        
        response = client.client.table('level1_companies').insert(test_record).execute()
        
        if response.data:
            print(f"✅ SUCCESS: Inserted test record with ID: {response.data[0].get('id')}")
            
            # Clean up - delete the test record
            try:
                client.client.table('level1_companies').delete().eq('id', response.data[0].get('id')).execute()
                print("✅ Cleaned up test record")
            except Exception as cleanup_error:
                print(f"⚠️  Could not clean up test record: {cleanup_error}")
            
            return True
        else:
            print("❌ FAILED: Insert returned no data")
            return False
            
    except Exception as e:
        error_msg = str(e)
        print(f"❌ FAILED: {error_msg}")
        
        # Provide helpful error messages
        if 'permission' in error_msg.lower() or 'policy' in error_msg.lower() or 'rls' in error_msg.lower():
            print("\n💡 SUGGESTION: Row Level Security (RLS) might be enabled.")
            print("   Check your Supabase dashboard -> Authentication -> Policies")
            print("   Make sure there's a policy allowing INSERT for authenticated users")
        elif 'constraint' in error_msg.lower() or 'violates' in error_msg.lower():
            print("\n💡 SUGGESTION: Database constraint violation.")
            print("   Check your database schema constraints")
        elif 'connection' in error_msg.lower() or 'timeout' in error_msg.lower():
            print("\n💡 SUGGESTION: Connection issue.")
            print("   Check your SUPABASE_URL and API keys in config.py")
        
        return False

def test_save_function(client):
    """Test the actual save_level1_results function"""
    print("\n" + "=" * 60)
    print("TEST 3: Save Function Test")
    print("=" * 60)
    
    test_companies = [
        {
            'company_name': 'Diagnostic Company 1',
            'place_id': 'ChIJTEST123456',
            'website': 'https://test1.com',
            'phone': '1111111111',
            'address': 'Test Address 1',
            'place_type': 'Business',
            'pin_code': '123456',
            'business_status': 'OPERATIONAL'
        },
        {
            'company_name': 'Diagnostic Company 2',
            'place_id': None,  # No place_id - this was the original bug
            'website': 'https://test2.com',
            'phone': '2222222222',
            'address': 'Test Address 2',
            'place_type': 'Business',
            'pin_code': '123456',
            'business_status': 'OPERATIONAL'
        }
    ]
    
    search_params = {
        'project_name': 'project 1',  # The exact project name the user mentioned
        'pin_codes': '123456',
        'industry': 'IT',
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    print(f"Testing save_level1_results with:")
    print(f"  project_name: '{search_params['project_name']}'")
    print(f"  companies: {len(test_companies)}")
    print(f"  Companies with place_id: {sum(1 for c in test_companies if c.get('place_id'))}")
    print(f"  Companies without place_id: {sum(1 for c in test_companies if not c.get('place_id'))}")
    
    try:
        result = client.save_level1_results(test_companies, search_params)
        
        print(f"\nResult: {result}")
        
        if result.get('success'):
            count = result.get('count', 0)
            print(f"✅ SUCCESS: Function reported {count} companies saved")
            
            # Verify in database
            verify = client.client.table('level1_companies').select('id', count='exact').eq('project_name', 'project 1').execute()
            actual_count = verify.count if hasattr(verify, 'count') else (len(verify.data) if verify.data else 0)
            print(f"✅ Verified: Found {actual_count} companies in database for 'project 1'")
            
            if actual_count > 0:
                print("✅✅✅ SAVE FUNCTION IS WORKING! ✅✅✅")
                return True
            else:
                print("❌ Function reported success but database is empty!")
                return False
        else:
            error = result.get('error', 'Unknown error')
            print(f"❌ FAILED: {error}")
            return False
            
    except Exception as e:
        print(f"❌ EXCEPTION: {e}")
        import traceback
        print(traceback.format_exc())
        return False

def main():
    print("\n" + "=" * 60)
    print("DIAGNOSTIC SCRIPT: Testing Save Functionality")
    print("=" * 60 + "\n")
    
    # Test 1: Connection
    client = test_database_connection()
    if not client:
        print("\n❌ Cannot proceed - database connection failed")
        return
    
    # Test 2: Simple insert
    if not test_simple_insert(client):
        print("\n❌ Cannot proceed - simple insert failed")
        print("   Fix the database connection/permissions issue first")
        return
    
    # Test 3: Save function
    success = test_save_function(client)
    
    print("\n" + "=" * 60)
    if success:
        print("✅ ALL TESTS PASSED - Save function is working!")
        print("\nIf you're still having issues, check:")
        print("  1. Application logs for detailed error messages")
        print("  2. Supabase dashboard for RLS policies")
        print("  3. Network connectivity to Supabase")
    else:
        print("❌ TESTS FAILED - See errors above")
        print("\nNext steps:")
        print("  1. Check the error messages above")
        print("  2. Verify Supabase credentials in config.py")
        print("  3. Check Supabase dashboard for table permissions")
    print("=" * 60)

if __name__ == '__main__':
    main()


