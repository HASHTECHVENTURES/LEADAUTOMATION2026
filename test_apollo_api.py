#!/usr/bin/env python3
"""
Test script to verify Apollo.io API calls are working properly
"""
import sys
from apollo_client import ApolloClient
from config import Config

def test_apollo_api():
    """Test Apollo.io API connection and search functionality"""
    print("=" * 60)
    print("TESTING APOLLO.IO API CONNECTION")
    print("=" * 60)
    
    # Check API key
    api_key = Config.APOLLO_API_KEY
    if not api_key:
        print("❌ ERROR: APOLLO_API_KEY not found in config.py")
        return False
    
    print(f"✅ API Key found: {api_key[:10]}...{api_key[-5:]}")
    print()
    
    # Initialize Apollo client
    try:
        apollo = ApolloClient()
        print("✅ Apollo client initialized successfully")
    except Exception as e:
        print(f"❌ ERROR: Failed to initialize Apollo client: {str(e)}")
        return False
    
    print()
    print("=" * 60)
    print("TEST 1: Search by Domain (api_search endpoint)")
    print("=" * 60)
    
    # Test with a known company
    test_domain = "google.com"  # Using Google as test
    test_titles = ["CEO", "CTO", "Director"]
    
    print(f"Testing search for domain: {test_domain}")
    print(f"With titles: {test_titles}")
    print()
    
    try:
        people = apollo.search_people_api_search(test_domain, titles=test_titles)
        print(f"\n✅ API Call Successful!")
        print(f"   Found {len(people)} contacts")
        
        if people:
            print(f"\n   Sample contacts:")
            for i, person in enumerate(people[:3], 1):
                print(f"   {i}. {person.get('name', 'N/A')} - {person.get('title', 'N/A')}")
                print(f"      Email: {person.get('email', 'N/A')}")
                print(f"      Phone: {person.get('phone', 'N/A')}")
        else:
            print("   ⚠️  No contacts found (this might be normal if domain has no matching titles)")
        
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR: API call failed")
        print(f"   Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_search_by_company():
    """Test search_people_by_company method"""
    print()
    print("=" * 60)
    print("TEST 2: Search by Company Name and Website")
    print("=" * 60)
    
    apollo = ApolloClient()
    test_company = "Google"
    test_website = "https://www.google.com"
    test_titles = ["CEO", "Director"]
    
    print(f"Testing search for company: {test_company}")
    print(f"Website: {test_website}")
    print(f"With titles: {test_titles}")
    print()
    
    try:
        people = apollo.search_people_by_company(test_company, test_website, titles=test_titles)
        print(f"\n✅ Search Successful!")
        print(f"   Found {len(people)} contacts")
        
        if people:
            print(f"\n   Sample contacts:")
            for i, person in enumerate(people[:3], 1):
                print(f"   {i}. {person.get('name', 'N/A')} - {person.get('title', 'N/A')}")
        else:
            print("   ⚠️  No contacts found")
        
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR: Search failed")
        print(f"   Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_employee_count():
    """Test getting company employee count"""
    print()
    print("=" * 60)
    print("TEST 3: Get Company Employee Count")
    print("=" * 60)
    
    apollo = ApolloClient()
    test_company = "Google"
    test_website = "https://www.google.com"
    
    print(f"Testing employee count for: {test_company}")
    print()
    
    try:
        employees = apollo.get_company_total_employees(test_company, test_website)
        print(f"\n✅ Employee Count Retrieved!")
        print(f"   Result: {employees if employees else 'Not available'}")
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR: Failed to get employee count")
        print(f"   Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("\n")
    
    # Run tests
    test1 = test_apollo_api()
    test2 = test_search_by_company()
    test3 = test_employee_count()
    
    print()
    print("=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Test 1 (API Search): {'✅ PASSED' if test1 else '❌ FAILED'}")
    print(f"Test 2 (Company Search): {'✅ PASSED' if test2 else '❌ FAILED'}")
    print(f"Test 3 (Employee Count): {'✅ PASSED' if test3 else '❌ FAILED'}")
    print()
    
    if all([test1, test2, test3]):
        print("✅ All tests passed! Apollo.io API is working correctly.")
        sys.exit(0)
    else:
        print("❌ Some tests failed. Check the errors above.")
        sys.exit(1)


