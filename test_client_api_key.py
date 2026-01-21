"""
Test script to verify the client's Google Places API key
"""
import requests
from google_places_client import GooglePlacesClient

# Client's test API key
CLIENT_API_KEY = "AIzaSyAEO0aq-QKAFNo6Jw-bP0BAIBxmB7DPVPs"

def test_api_key():
    print("=" * 70)
    print("TESTING CLIENT'S GOOGLE PLACES API KEY")
    print("=" * 70)
    print(f"API Key: {CLIENT_API_KEY[:20]}...{CLIENT_API_KEY[-10:]}")
    print()
    
    # Initialize client with client's API key
    client = GooglePlacesClient(api_key=CLIENT_API_KEY)
    
    # Test 1: Geocoding API
    print("TEST 1: Geocoding API (PIN Code lookup)")
    print("-" * 70)
    test_pin = "400001"  # Mumbai
    geocode_url = "https://maps.googleapis.com/maps/api/geocode/json"
    geocode_params = {
        'address': f"{test_pin}, India",
        'key': CLIENT_API_KEY
    }
    
    try:
        response = requests.get(geocode_url, params=geocode_params, timeout=10)
        data = response.json()
        
        status = data.get('status')
        print(f"Status: {status}")
        
        if status == 'OK':
            location = data['results'][0]['geometry']['location']
            print(f"✅ Geocoding works!")
            print(f"   PIN: {test_pin}")
            print(f"   Location: {location['lat']}, {location['lng']}")
            print(f"   Address: {data['results'][0]['formatted_address']}")
        elif status == 'REQUEST_DENIED':
            error_msg = data.get('error_message', 'No error message')
            print(f"❌ API Key is invalid or restricted: {error_msg}")
            return False
        elif status == 'OVER_QUERY_LIMIT':
            print(f"⚠️  API quota exceeded")
            return False
        else:
            print(f"❌ Error: {status}")
            print(f"   Message: {data.get('error_message', 'No message')}")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    print()
    
    # Test 2: Places Text Search API
    print("TEST 2: Places API - Text Search")
    print("-" * 70)
    places_url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    places_params = {
        'query': 'restaurants in Mumbai',
        'key': CLIENT_API_KEY
    }
    
    try:
        response = requests.get(places_url, params=places_params, timeout=10)
        data = response.json()
        
        status = data.get('status')
        print(f"Status: {status}")
        
        if status == 'OK':
            results = data.get('results', [])
            print(f"✅ Places API works!")
            print(f"   Found {len(results)} results")
            if results:
                first = results[0]
                print(f"   Example: {first.get('name')} - {first.get('formatted_address', 'N/A')}")
        elif status == 'REQUEST_DENIED':
            error_msg = data.get('error_message', 'No error message')
            print(f"❌ API Key is invalid or Places API not enabled: {error_msg}")
            return False
        elif status == 'OVER_QUERY_LIMIT':
            print(f"⚠️  API quota exceeded")
            return False
        else:
            print(f"❌ Error: {status}")
            print(f"   Message: {data.get('error_message', 'No message')}")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    print()
    
    # Test 3: Test with your actual search function
    print("TEST 3: Full Search Function (PIN + Industry)")
    print("-" * 70)
    try:
        results = client.search_by_pin_and_industry(
            pin_code="400001",
            industry="restaurants",
            max_results=3
        )
        
        if results:
            print(f"✅ Full search works!")
            print(f"   Found {len(results)} companies")
            for i, company in enumerate(results[:3], 1):
                print(f"\n   Company {i}:")
                print(f"     Name: {company.get('company_name', 'N/A')}")
                print(f"     Phone: {company.get('phone', 'N/A')}")
                print(f"     Website: {company.get('website', 'N/A')}")
                print(f"     Address: {company.get('address', 'N/A')[:60]}...")
        else:
            print(f"⚠️  No results found (might be normal if no businesses in area)")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    print()
    
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print("✅ Client's API key is working!")
    print("✅ Geocoding API: Enabled")
    print("✅ Places API: Enabled")
    print()
    print("To use this key in your app:")
    print("1. Set environment variable: export GOOGLE_PLACES_API_KEY='AIzaSyAEO0aq-QKAFNo6Jw-bP0BAIBxmB7DPVPs'")
    print("2. Or update config.py temporarily for testing")
    print("3. Restart your Flask server")
    print("=" * 70)
    
    return True

if __name__ == '__main__':
    test_api_key()


