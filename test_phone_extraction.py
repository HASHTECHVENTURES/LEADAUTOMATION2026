#!/usr/bin/env python3
"""
Test script to verify Apollo.io phone number extraction
Tests with a real company from India
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from apollo_client import ApolloClient
from config import Config

def test_phone_extraction():
    """Test phone number extraction with a real Indian company"""
    print("=" * 60)
    print("TESTING APOLLO.IO PHONE NUMBER EXTRACTION")
    print("=" * 60)
    
    # Initialize Apollo client
    apollo = ApolloClient()
    
    # Test with a real Indian company (HealthAssure - we know this from your screenshots)
    test_company = "HealthAssure"
    test_website = "healthassure.in"
    
    print(f"\n🔍 Testing with company: {test_company}")
    print(f"🌐 Website: {test_website}")
    print("\n" + "-" * 60)
    
    # Search for people
    print("\n1️⃣ Searching for contacts...")
    people = apollo.search_people_by_company(test_company, test_website)
    
    print(f"\n✅ Found {len(people)} contacts")
    
    # Check phone numbers
    print("\n2️⃣ Checking phone numbers in results...")
    contacts_with_phone = 0
    contacts_without_phone = 0
    
    for idx, person in enumerate(people[:5], 1):  # Check first 5
        name = person.get('name', 'Unknown')
        email = person.get('email', 'No email')
        phone = person.get('phone', '') or person.get('phone_number', '')
        title = person.get('title', 'No title')
        
        print(f"\n   Contact {idx}: {name}")
        print(f"   Title: {title}")
        print(f"   Email: {email}")
        print(f"   Phone: {phone if phone else '❌ NO PHONE'}")
        
        if phone:
            contacts_with_phone += 1
            print(f"   ✅ HAS PHONE NUMBER")
        else:
            contacts_without_phone += 1
            print(f"   ❌ NO PHONE NUMBER")
    
    print("\n" + "=" * 60)
    print("SUMMARY:")
    print(f"   Total contacts found: {len(people)}")
    print(f"   Contacts WITH phone: {contacts_with_phone}")
    print(f"   Contacts WITHOUT phone: {contacts_without_phone}")
    print("=" * 60)
    
    # Test the extraction helper directly
    print("\n3️⃣ Testing phone extraction helper function...")
    if people:
        test_person = people[0]
        print(f"\n   Testing with: {test_person.get('name')}")
        
        # Simulate Apollo person object structure
        apollo_person = {
            'first_name': test_person.get('first_name', ''),
            'last_name': test_person.get('last_name', ''),
            'email': test_person.get('email', ''),
            'title': test_person.get('title', ''),
            'phone_numbers': [
                {'raw_number': '+919886638192', 'type': 'mobile'},
                {'raw_number': '+918860155000', 'type': 'work'}
            ] if not test_person.get('phone') else [{'raw_number': test_person.get('phone'), 'type': 'mobile'}]
        }
        
        extracted_phone = apollo._extract_phone_from_person(apollo_person)
        print(f"   Extracted phone: {extracted_phone if extracted_phone else '❌ NONE'}")
    
    print("\n✅ Test complete!")

if __name__ == '__main__':
    try:
        test_phone_extraction()
    except Exception as e:
        print(f"\n❌ Error during test: {str(e)}")
        import traceback
        traceback.print_exc()

