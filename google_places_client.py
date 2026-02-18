import requests
import time
from typing import List, Dict, Optional
from config import Config

class GooglePlacesClient:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or Config.GOOGLE_PLACES_API_KEY
        self.base_url = 'https://maps.googleapis.com/maps/api/place'
        
    def search_by_pin_and_industry(self, pin_code: str, industry: str = None, max_results: int = 20) -> List[Dict]:
        """
        Search for places by PIN code (India) - PIN code is unique, no state needed
        Returns list of company data with pagination support to fetch all requested results
        """
        results = []
        
        # First, get location from PIN code using Geocoding API
        geocode_url = "https://maps.googleapis.com/maps/api/geocode/json"
        geocode_params = {
            'address': f"{pin_code}, India",
            'key': self.api_key
        }
        
        try:
            geocode_response = requests.get(geocode_url, params=geocode_params)
            geocode_data = geocode_response.json()
            
            print(f"📍 Geocoding response status: {geocode_data.get('status')}")
            if geocode_data['status'] != 'OK':
                error_msg = geocode_data.get('error_message', 'Unknown error')
                print(f"❌ Geocoding error: {geocode_data['status']} - {error_msg}")
                if geocode_data['status'] == 'ZERO_RESULTS':
                    print(f"   No location found for PIN: {pin_code}, India")
                return results
            
            location = geocode_data['results'][0]['geometry']['location']
            lat, lng = location['lat'], location['lng']
            
            # Build search query
            if industry:
                query = f"{industry} in {pin_code}, India"
            else:
                query = f"businesses in {pin_code}, India"
            
            # Search for places near this location with pagination support
            places_url = f"{self.base_url}/textsearch/json"
            next_page_token = None
            page_number = 1
            
            while len(results) < max_results:
                places_params = {
                    'query': query,
                    'location': f"{lat},{lng}",
                    'radius': 10000,  # 10km radius
                    'key': self.api_key
                }
                
                # Add pagination token if we have one
                if next_page_token:
                    places_params['pagetoken'] = next_page_token
                    print(f"📄 Fetching page {page_number} with pagination token...")
                    # Google requires a delay between pagination requests
                    time.sleep(2)
                
                places_response = requests.get(places_url, params=places_params)
                places_data = places_response.json()
                
                print(f"🏢 Places search response status (page {page_number}): {places_data.get('status')}")
                if places_data['status'] != 'OK':
                    error_msg = places_data.get('error_message', 'Unknown error')
                    print(f"❌ Places search error: {places_data['status']} - {error_msg}")
                    if places_data['status'] == 'ZERO_RESULTS':
                        print(f"   No businesses found for query: {query}")
                        break
                    elif places_data['status'] == 'OVER_QUERY_LIMIT':
                        print(f"   ⚠️  Google Places API quota exceeded!")
                        break
                    elif places_data['status'] == 'INVALID_REQUEST' and next_page_token:
                        # Token expired or invalid, stop pagination
                        print(f"   ⚠️  Pagination token expired or invalid, stopping pagination")
                        break
                    else:
                        break
                
                places_list = places_data.get('results', [])
                print(f"✅ Found {len(places_list)} places from Google Places API (page {page_number})")
                
                # Process each place until we reach max_results
                for place in places_list:
                    if len(results) >= max_results:
                        break
                    
                    place_id = place.get('place_id')
                    if place_id:
                        details = self.get_place_details(place_id)
                        if details:
                            # Preserve the user's search industry so Level 2 never mixes sessions/industries.
                            # Keep Google's detected type separately in details['place_type'].
                            details['place_type'] = details.get('industry', '')
                            details['industry'] = industry.strip() if industry else details.get('industry', '')
                            results.append(details)
                        time.sleep(0.1)  # Rate limiting
                
                # Check if there's a next page token
                next_page_token = places_data.get('next_page_token')
                if not next_page_token or len(results) >= max_results:
                    break
                
                page_number += 1
            
            print(f"✅ Total companies fetched: {len(results)} out of {max_results} requested")
            return results
            
        except Exception as e:
            error_msg = str(e)
            print(f"❌ Error in search for PIN {pin_code}: {error_msg}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            # Re-raise the exception so the caller knows what went wrong
            # This allows the web app to show proper error messages
            raise Exception(f"Google Places API error for PIN {pin_code}: {error_msg}") from e
    
    def get_place_details(self, place_id: str) -> Optional[Dict]:
        """Get detailed information about a place"""
        details_url = f"{self.base_url}/details/json"
        params = {
            'place_id': place_id,
            'fields': 'name,website,formatted_phone_number,formatted_address,types,business_status,rating,opening_hours',
            'key': self.api_key
        }
        
        try:
            response = requests.get(details_url, params=params)
            data = response.json()
            
            if data['status'] != 'OK':
                return None
            
            place = data['result']
            
            # Extract industry from types
            types = place.get('types', [])
            industry = 'General Business'
            for t in types:
                if t not in ['establishment', 'point_of_interest']:
                    industry = t.replace('_', ' ').title()
                    break
            
            return {
                'company_name': place.get('name', ''),
                'website': place.get('website', ''),
                'phone': place.get('formatted_phone_number', ''),
                'address': place.get('formatted_address', ''),
                'place_id': place_id,
                'industry': industry,
                'types': types,
                'business_status': place.get('business_status', ''),
                'rating': place.get('rating', ''),
                'opening_hours': place.get('opening_hours', {}).get('weekday_text', [])
            }
            
        except Exception as e:
            print(f"Error getting place details: {str(e)}")
            return None
    
    def search_by_place_and_industry(self, place_name: str, industry: str = None, max_results: int = 20) -> List[Dict]:
        """
        Search for places by place name (e.g., Mumbai, Pune, Bangalore)
        Returns list of company data with pagination support to fetch all requested results
        """
        results = []
        
        # First, get location from place name using Geocoding API
        geocode_url = "https://maps.googleapis.com/maps/api/geocode/json"
        geocode_params = {
            'address': f"{place_name}, India",
            'key': self.api_key
        }
        
        try:
            geocode_response = requests.get(geocode_url, params=geocode_params)
            geocode_data = geocode_response.json()
            
            print(f"📍 Geocoding response status: {geocode_data.get('status')}")
            if geocode_data['status'] != 'OK':
                error_msg = geocode_data.get('error_message', 'Unknown error')
                print(f"❌ Geocoding error: {geocode_data['status']} - {error_msg}")
                if geocode_data['status'] == 'ZERO_RESULTS':
                    print(f"   No location found for place: {place_name}, India")
                return results
            
            location = geocode_data['results'][0]['geometry']['location']
            lat, lng = location['lat'], location['lng']
            
            # Build search query
            if industry:
                query = f"{industry} in {place_name}, India"
            else:
                query = f"businesses in {place_name}, India"
            
            # Search for places near this location with pagination support
            places_url = f"{self.base_url}/textsearch/json"
            next_page_token = None
            page_number = 1
            
            while len(results) < max_results:
                places_params = {
                    'query': query,
                    'location': f"{lat},{lng}",
                    'radius': 50000,  # 50km radius for cities (larger than PIN codes)
                    'key': self.api_key
                }
                
                # Add pagination token if we have one
                if next_page_token:
                    places_params['pagetoken'] = next_page_token
                    print(f"📄 Fetching page {page_number} with pagination token...")
                    # Google requires a delay between pagination requests
                    time.sleep(2)
                
                places_response = requests.get(places_url, params=places_params)
                places_data = places_response.json()
                
                print(f"🏢 Places search response status (page {page_number}): {places_data.get('status')}")
                if places_data['status'] != 'OK':
                    error_msg = places_data.get('error_message', 'Unknown error')
                    print(f"❌ Places search error: {places_data['status']} - {error_msg}")
                    if places_data['status'] == 'ZERO_RESULTS':
                        print(f"   No businesses found for query: {query}")
                        break
                    elif places_data['status'] == 'OVER_QUERY_LIMIT':
                        print(f"   ⚠️  Google Places API quota exceeded!")
                        break
                    elif places_data['status'] == 'INVALID_REQUEST' and next_page_token:
                        # Token expired or invalid, stop pagination
                        print(f"   ⚠️  Pagination token expired or invalid, stopping pagination")
                        break
                    else:
                        break
                
                places_list = places_data.get('results', [])
                print(f"✅ Found {len(places_list)} places from Google Places API (page {page_number})")
                
                # Process each place until we reach max_results
                for place in places_list:
                    if len(results) >= max_results:
                        break
                    
                    place_id = place.get('place_id')
                    if place_id:
                        details = self.get_place_details(place_id)
                        if details:
                            # Preserve the user's search industry
                            details['place_type'] = details.get('industry', '')
                            details['industry'] = industry.strip() if industry else details.get('industry', '')
                            # Add place name for tracking
                            details['search_location'] = place_name
                            results.append(details)
                        time.sleep(0.1)  # Rate limiting
                
                # Check if there's a next page token
                next_page_token = places_data.get('next_page_token')
                if not next_page_token or len(results) >= max_results:
                    break
                
                page_number += 1
            
            print(f"✅ Total companies fetched: {len(results)} out of {max_results} requested")
            return results
            
        except Exception as e:
            error_msg = str(e)
            print(f"❌ Error in search for place {place_name}: {error_msg}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            raise Exception(f"Google Places API error for place {place_name}: {error_msg}") from e


