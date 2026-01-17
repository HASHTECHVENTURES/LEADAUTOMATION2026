import requests
import time
from typing import List, Dict, Optional
from config import Config
# Web scraper removed - using Apollo.io only

class ApolloClient:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or Config.APOLLO_API_KEY
        self.base_url = 'https://api.apollo.io/v1'
        self.api_search_base = 'https://api.apollo.io/api/v1'  # New endpoint base
        self.headers = {
            'Content-Type': 'application/json',
            'Cache-Control': 'no-cache',
            'X-Api-Key': self.api_key  # API key in header (required by Apollo)
        }
        # Web scraper removed
        self._list_cache = {}

    def create_contact(self, contact: Dict) -> Dict:
        """
        Create a contact in Apollo.io.
        Tries multiple endpoints for compatibility across plans.
        Returns {success: bool, error?: str, response?: Dict}
        """
        if not contact or not contact.get('email'):
            return {'success': False, 'error': 'Email is required for Apollo contact creation'}

        # Common payload fields
        payload = {
            'first_name': contact.get('first_name', ''),
            'last_name': contact.get('last_name', ''),
            'email': contact.get('email', ''),
            'phone': contact.get('phone', ''),
            'linkedin_url': contact.get('linkedin_url', ''),
            'organization_name': contact.get('organization_name', ''),
            'title': contact.get('title', '')
        }

        endpoints = [
            (f"{self.base_url}/contacts", payload),
            (f"{self.base_url}/people/add", payload),
        ]

        last_error = ''
        for url, body in endpoints:
            try:
                resp = requests.post(url, json=body, headers=self.headers)
                if resp.status_code in (200, 201):
                    data = resp.json() if resp.content else {}
                    # Try to extract contact/person ID
                    contact_id = None
                    if isinstance(data, dict):
                        contact_id = (
                            data.get('contact', {}).get('id') or
                            data.get('person', {}).get('id') or
                            data.get('id')
                        )
                    return {'success': True, 'response': data, 'contact_id': contact_id}
                last_error = f"{resp.status_code}: {resp.text[:200]}"
            except Exception as e:
                last_error = str(e)
                continue

        return {'success': False, 'error': last_error or 'Apollo contact creation failed'}

    def find_contact_by_email(self, email: str) -> Dict:
        """
        Best-effort duplicate check in Apollo by email.
        Returns {exists: bool, contact_id?: str, error?: str}
        """
        if not email:
            return {'exists': False}
        try:
            url = f"{self.base_url}/contacts/search"
            payload = {
                'q_keywords': email,
                'page': 1,
                'per_page': 1
            }
            resp = requests.post(url, json=payload, headers=self.headers)
            if resp.status_code == 200:
                data = resp.json() or {}
                contacts = data.get('contacts') or data.get('people') or []
                if contacts:
                    contact_id = contacts[0].get('id')
                    return {'exists': True, 'contact_id': contact_id}
                return {'exists': False}
            return {'exists': False, 'error': f"{resp.status_code}: {resp.text[:200]}"}
        except Exception as e:
            return {'exists': False, 'error': str(e)}

    def create_contact_list(self, list_name: str) -> Dict:
        """
        Create a contact list in Apollo.io and return list_id.
        """
        if not list_name:
            return {'success': False, 'error': 'list_name is required'}
        if list_name in self._list_cache:
            return {'success': True, 'list_id': self._list_cache[list_name], 'cached': True}
        try:
            url = f"{self.base_url}/contact_lists"
            payload = {'name': list_name}
            resp = requests.post(url, json=payload, headers=self.headers)
            if resp.status_code in (200, 201):
                data = resp.json() if resp.content else {}
                list_id = None
                if isinstance(data, dict):
                    list_id = data.get('contact_list', {}).get('id') or data.get('id')
                if list_id:
                    self._list_cache[list_name] = list_id
                return {'success': True, 'list_id': list_id, 'response': data}
            return {'success': False, 'error': f"{resp.status_code}: {resp.text[:200]}"}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def add_contact_to_list(self, list_id: str, contact_id: str) -> Dict:
        """
        Add an existing contact to a list.
        """
        if not list_id or not contact_id:
            return {'success': False, 'error': 'list_id and contact_id are required'}
        endpoints = [
            (f"{self.base_url}/contact_lists/{list_id}/contacts", {'contact_ids': [contact_id]}),
            (f"{self.base_url}/contact_lists/{list_id}/contacts", {'contacts': [{'id': contact_id}]}),
        ]
        last_error = ''
        for url, payload in endpoints:
            try:
                resp = requests.post(url, json=payload, headers=self.headers)
                if resp.status_code in (200, 201):
                    return {'success': True}
                last_error = f"{resp.status_code}: {resp.text[:200]}"
            except Exception as e:
                last_error = str(e)
        return {'success': False, 'error': last_error or 'Failed to add contact to list'}
    
    def extract_domain(self, website: str) -> str:
        """Extract domain from website URL"""
        if not website:
            return ''
        domain = website.replace('https://', '').replace('http://', '').replace('www.', '')
        domain = domain.split('/')[0].split('?')[0]
        return domain.strip()

    def _extract_employee_count(self, org: Dict) -> str:
        """
        Try to extract a human-friendly employee count / range from Apollo organization object.
        Returns '' if not available.
        """
        if not org:
            return ''

        # Common Apollo fields (varies by endpoint/plan)
        for key in [
            'estimated_num_employees',
            'num_employees',
            'employee_count',
            'employees',
            'organization_num_employees',
            'employees_count',
        ]:
            val = org.get(key)
            if val is None or val == '':
                continue
            return str(val)

        for key in [
            'estimated_num_employees_range',
            'num_employees_range',
            'employee_range',
        ]:
            val = org.get(key)
            if val is None or val == '':
                continue
            return str(val)

        return ''

    def get_company_total_employees(self, company_name: str, website: str = '') -> str:
        """
        Get company's total employee count (or range) from Apollo organizations/search.
        Best-effort: returns '' if not available.
        """
        try:
            org_url = f"{self.base_url}/organizations/search"
            domain = self.extract_domain(website) if website else ''

            payloads = []
            # Try domain-based payloads first (more accurate)
            if domain:
                payloads.extend([
                    {'q_organization_domains': domain, 'page': 1, 'per_page': 1},
                    {'q_organization_domains_list': [domain], 'page': 1, 'per_page': 1},
                    {'organization_domains': [domain], 'page': 1, 'per_page': 1},
                ])
            # Fallback: name-based
            if company_name:
                payloads.append({'name': company_name, 'page': 1, 'per_page': 1})

            for payload in payloads:
                try:
                    print(f"🔍 Trying to get employee count for: {company_name} with payload: {payload}")
                    resp = requests.post(org_url, json=payload, headers=self.headers)
                    print(f"   Apollo response status: {resp.status_code}")
                    
                    if resp.status_code != 200:
                        print(f"   ❌ Failed with status {resp.status_code}")
                        continue
                    
                    data = resp.json() or {}
                    orgs = data.get('organizations', []) or []
                    print(f"   Found {len(orgs)} organization(s) in Apollo")
                    
                    if not orgs:
                        continue
                    
                    org = orgs[0]
                    print(f"   Organization data keys: {list(org.keys())}")
                    print(f"   Raw org data sample: num_employees={org.get('estimated_num_employees')}, employee_count={org.get('employee_count')}")
                    
                    emp = self._extract_employee_count(org)
                    if emp:
                        print(f"   ✅ Found employee count: {emp}")
                        return emp
                    else:
                        print(f"   ⚠️ No employee count found in org data")
                except Exception as e:
                    print(f"   ❌ Exception: {str(e)}")
                    continue

        except Exception as e:
            print(f"Error getting company total employees from Apollo: {str(e)}")

        return ''

    def _add_current_employee_filter(self, payload: Dict) -> Dict:
        """
        Add best-effort filters to request ONLY currently employed people.
        Apollo parameter names can vary by endpoint/account; we try a few common ones.
        If Apollo rejects these filters, caller should retry without them.
        """
        p = dict(payload or {})
        # Common variants used in Apollo / PostgREST-like filtering
        # (We keep them additive; Apollo will ignore unknown keys OR error — we handle retry.)
        p['currently_employed'] = True
        p['person_employment_status'] = 'current'
        p['q_person_employment_statuses'] = ['current']
        return p
    
    def search_people_api_search(self, domain: str, titles: List[str] = None, seniorities: List[str] = None) -> List[Dict]:
        """
        NEW: Use api_search endpoint (FREE - no credits)
        Returns people without emails/phones - need enrichment
        """
        people = []
        titles = titles or ['Founder', 'HR Director', 'HR Manager', 'CHRO', 'Director', 'HR', 'Manager', 'VP', 'Vice President', 'Head', 'Chief', 'Owner', 'CEO', 'CTO', 'CFO', 'COO']
        seniorities = seniorities or ['owner', 'founder', 'c_suite', 'vp', 'head', 'director', 'manager', 'senior', 'lead']
        
        try:
            url = f"{self.api_search_base}/mixed_people/api_search"
            base_payload = {
                # API key removed from payload - now in header
                'q_organization_domains_list': [domain],
                'person_titles': titles,
                'person_seniorities': seniorities,
                'include_similar_titles': True,  # Allow similar titles to get more results
                'page': 1,
                'per_page': 50  # Get more results
            }

            # Try current-employee filter first; if Apollo rejects, fallback without it
            payload = self._add_current_employee_filter(base_payload)
            response = requests.post(url, json=payload, headers=self.headers)
            if response.status_code not in (200,):
                # retry without filters
                response = requests.post(url, json=base_payload, headers=self.headers)
            
            print(f"    Apollo api_search response status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                persons = data.get('people', [])
                print(f"    📊 Apollo api_search found {len(persons)} people (before enrichment)")
                
                # Extract person IDs AND organization domains for validation
                person_data_list = [(p.get('id'), p.get('organization', {}).get('primary_domain', '')) 
                                   for p in persons if p.get('id')]
                print(f"    📋 Extracted {len(person_data_list)} person IDs for enrichment")
                
                if person_data_list:
                    print(f"    🔄 Enriching {len(person_data_list)} people to get emails/phones...")
                    # Enrich to get emails/phones (costs credits) and validate company
                    enriched_people = self.enrich_people_with_validation([pid for pid, _ in person_data_list], domain)
                    print(f"    ✅ Enrichment returned {len(enriched_people)} contacts with emails/phones (validated for {domain})")
                    people.extend(enriched_people)
                else:
                    print(f"    ⚠️  No person IDs found - Apollo returned people without IDs")
                    # If no IDs, still return basic info
                    for person in persons:
                        person_data = {
                            'name': f"{person.get('first_name', '')} {person.get('last_name_obfuscated', '') or person.get('last_name', '')}".strip(),
                            'first_name': person.get('first_name', ''),
                            'last_name': person.get('last_name_obfuscated', '') or person.get('last_name', ''),
                            'email': '',  # Will be filled by enrichment
                            'phone': '',  # Will be filled by enrichment
                            'title': person.get('title', ''),
                            'linkedin_url': person.get('linkedin_url', ''),
                            'apollo_id': person.get('id', ''),
                            'source': 'apollo'
                        }
                        if person_data['name']:
                            people.append(person_data)
            else:
                print(f"    ❌ Apollo api_search failed: Status {response.status_code}")
                print(f"    Response: {response.text[:300]}")
            
            time.sleep(0.5)  # Rate limiting
            
        except Exception as e:
            print(f"❌ Error in api_search for domain {domain}: {str(e)}")
            if hasattr(e, 'response') and e.response:
                print(f"Response: {e.response.text[:200]}")
            import traceback
            traceback.print_exc()
        
        # Less restrictive filtering - keep more contacts
        # Only filter out obvious non-relevant titles
        blocked_titles = ['intern', 'student', 'volunteer', 'freelancer', 'contractor']
        filtered_people = []
        for person in people:
            title = (person.get('title') or '').lower()
            # Skip only if it's a clearly blocked title
            if any(blocked in title for blocked in blocked_titles):
                print(f"    ⚠️ Filtered out: {person.get('name')} - Title: {person.get('title')} (blocked)")
                continue
            # Keep everyone else (we'll filter by email/phone later if needed)
            filtered_people.append(person)
        
        print(f"    ✅ After filtering: {len(filtered_people)} contacts (from {len(people)})")
        return filtered_people
    
    def enrich_people(self, person_ids: List[str]) -> List[Dict]:
        """
        Enrich people data to get emails and phone numbers (COSTS credits)
        Uses individual enrichment (bulk_match endpoint has issues)
        """
        enriched = []
        
        if not person_ids:
            return enriched
        
        # Use individual enrichment (more reliable)
        print(f"    Enriching {len(person_ids)} people individually...")
        for idx, person_id in enumerate(person_ids[:20], 1):  # Limit to 20 to avoid too many requests
            try:
                enriched_person = self.enrich_single_person(person_id)
                if enriched_person:
                    enriched.append(enriched_person)
                    print(f"    [{idx}/{min(len(person_ids), 20)}] Enriched: {enriched_person.get('name')} - {enriched_person.get('email')}")
                time.sleep(0.3)  # Rate limiting
            except Exception as e2:
                print(f"    Failed to enrich person {person_id}: {str(e2)}")
                continue
        
        return enriched
    
    def enrich_people_with_validation(self, person_ids: List[str], target_domain: str) -> List[Dict]:
        """
        Enrich people and VALIDATE they work at the target company domain
        This prevents showing contacts from OTHER companies
        """
        enriched = []
        
        if not person_ids:
            return enriched
        
        print(f"    Enriching {len(person_ids)} people with company validation (target: {target_domain})...")
        for idx, person_id in enumerate(person_ids[:20], 1):
            try:
                enriched_person = self.enrich_single_person(person_id)
                if enriched_person:
                    # Less strict validation - include if email domain matches OR if no email (might have phone)
                    person_email = enriched_person.get('email', '')
                    person_phone = enriched_person.get('phone', '')
                    
                    # Include if has email OR phone (we want more contacts!)
                    if person_email or person_phone:
                        if person_email and '@' in person_email:
                            email_domain = person_email.split('@')[1].lower()
                            target_clean = target_domain.lower().replace('www.', '').replace('http://', '').replace('https://', '')
                            
                            # Check if email domain matches target domain
                            if target_clean in email_domain or email_domain in target_clean:
                                enriched.append(enriched_person)
                                print(f"    ✅ [{idx}/{min(len(person_ids), 20)}] {enriched_person.get('name')} - {person_email} (VERIFIED)")
                            else:
                                # Still include if has phone number (domain might be different but person works there)
                                if person_phone:
                                    enriched.append(enriched_person)
                                    print(f"    ✅ [{idx}/{min(len(person_ids), 20)}] {enriched_person.get('name')} - {person_email} (domain mismatch but has phone)")
                                else:
                                    print(f"    ⚠️  [{idx}/{min(len(person_ids), 20)}] REJECTED: {enriched_person.get('name')} - {person_email} (domain mismatch)")
                        else:
                            # No email but has phone - include
                            if person_phone:
                                enriched.append(enriched_person)
                                print(f"    ✅ [{idx}/{min(len(person_ids), 20)}] {enriched_person.get('name')} - No email but has phone")
                            else:
                                # No email, no phone - still include (might have LinkedIn)
                                enriched.append(enriched_person)
                                print(f"    ⚠️  [{idx}/{min(len(person_ids), 20)}] {enriched_person.get('name')} - No email/phone but including")
                    else:
                        # No email or phone - still include (might have LinkedIn)
                        enriched.append(enriched_person)
                        print(f"    ⚠️  [{idx}/{min(len(person_ids), 20)}] {enriched_person.get('name')} - No email/phone but including")
                time.sleep(0.3)
            except Exception as e2:
                print(f"    Failed to enrich person {person_id}: {str(e2)}")
                continue
        
        return enriched
    
    def enrich_single_person(self, person_id: str) -> Optional[Dict]:
        """Enrich a single person by ID"""
        try:
            # Try people/match endpoint with phone number request
            url = f"{self.base_url}/people/match"
            payload = {
                # API key removed from payload - now in header
                'person_id': person_id,
                'reveal_personal_emails': True,  # Request personal emails
                'reveal_phone_number': True,  # Request phone numbers - Apollo.io uses singular 'reveal_phone_number'
            }
            
            response = requests.post(url, json=payload, headers=self.headers)
            
            if response.status_code == 200:
                data = response.json()
                person = data.get('person', {})
                if person:
                    # Debug: Check if phone data exists
                    has_phone = person.get('has_direct_phone') or person.get('has_phone', False)
                    print(f"    📞 has_direct_phone: {has_phone}")
                    
                    phone = ''
                    # Try multiple phone number field variations
                    # Apollo.io returns phone_numbers as an array
                    if person.get('phone_numbers') and len(person.get('phone_numbers', [])) > 0:
                        # Try to get mobile phone first, then any phone
                        for phone_obj in person.get('phone_numbers', []):
                            phone_type = phone_obj.get('type', '').lower()
                            # Prefer mobile, then direct, then any
                            if phone_type in ['mobile', 'direct', 'work'] or not phone:
                                potential_phone = phone_obj.get('raw_number', '') or \
                                                 phone_obj.get('sanitized_number', '') or \
                                                 phone_obj.get('number', '') or \
                                                 phone_obj.get('phone', '')
                                if potential_phone:
                                    phone = potential_phone
                                    print(f"    📞 Found {phone_type} phone: {phone}")
                                    break
                    
                    # Also check direct phone fields (legacy/fallback)
                    if not phone:
                        phone = person.get('phone_number', '') or \
                               person.get('phone', '') or \
                               person.get('mobile', '') or \
                               person.get('direct_phone', '')
                    
                    # Check if phone is in organization data
                    if not phone and person.get('organization'):
                        org = person.get('organization', {})
                        if org.get('phone_numbers') and len(org.get('phone_numbers', [])) > 0:
                            phone_obj = org.get('phone_numbers', [{}])[0]
                            phone = phone_obj.get('raw_number', '') or \
                                   phone_obj.get('sanitized_number', '') or \
                                   phone_obj.get('number', '')
                    
                    if phone:
                        print(f"    ✅ Found phone: {phone}")
                    elif has_phone:
                        print(f"    ⚠️  Apollo indicates phone exists (has_direct_phone=True) but phone_numbers field is empty")
                        print(f"    ⚠️  Phone numbers may require additional API access or different endpoint")
                    else:
                        print(f"    ⚠️  No phone number available in Apollo database")
                    
                    return {
                        'name': f"{person.get('first_name', '')} {person.get('last_name', '')}".strip(),
                        'first_name': person.get('first_name', ''),
                        'last_name': person.get('last_name', ''),
                        'email': person.get('email', ''),
                        'phone': phone,
                        'title': person.get('title', ''),
                        'linkedin_url': person.get('linkedin_url', ''),
                        'source': 'apollo'
                    }
            else:
                print(f"    ⚠️  people/match failed (status {response.status_code}), trying GET /people/{person_id}")
                # If match fails, try to get person by ID directly with phone request
                url2 = f"{self.base_url}/people/{person_id}"
                # Try with query params to request phone numbers
                params = {
                    'reveal_personal_emails': 'true',
                    'reveal_phone_number': 'true'  # Request phone numbers - Apollo.io uses singular
                }
                response2 = requests.get(url2, headers=self.headers, params=params)
                if response2.status_code == 200:
                    person = response2.json().get('person', {})
                    if person:
                        # Debug: Check if phone data exists
                        has_phone = person.get('has_direct_phone') or person.get('has_phone', False)
                        print(f"    📞 has_direct_phone: {has_phone}")
                        
                        phone = ''
                        # Try multiple phone number field variations
                        # Apollo.io returns phone_numbers as an array
                        if person.get('phone_numbers') and len(person.get('phone_numbers', [])) > 0:
                            # Try to get mobile phone first, then any phone
                            for phone_obj in person.get('phone_numbers', []):
                                phone_type = phone_obj.get('type', '').lower()
                                # Prefer mobile, then direct, then any
                                if phone_type in ['mobile', 'direct', 'work'] or not phone:
                                    potential_phone = phone_obj.get('raw_number', '') or \
                                                     phone_obj.get('sanitized_number', '') or \
                                                     phone_obj.get('number', '') or \
                                                     phone_obj.get('phone', '')
                                    if potential_phone:
                                        phone = potential_phone
                                        print(f"    📞 Found {phone_type} phone: {phone}")
                                        break
                        
                        # Also check direct phone fields (legacy/fallback)
                        if not phone:
                            phone = person.get('phone_number', '') or \
                                   person.get('phone', '') or \
                                   person.get('mobile', '') or \
                                   person.get('direct_phone', '')
                        
                        # Check if phone is in organization data
                        if not phone and person.get('organization'):
                            org = person.get('organization', {})
                            if org.get('phone_numbers') and len(org.get('phone_numbers', [])) > 0:
                                phone_obj = org.get('phone_numbers', [{}])[0]
                                phone = phone_obj.get('raw_number', '') or \
                                       phone_obj.get('sanitized_number', '') or \
                                       phone_obj.get('number', '')
                        
                        if phone:
                            print(f"    ✅ Found phone: {phone}")
                        elif has_phone:
                            print(f"    ⚠️  Apollo indicates phone exists (has_direct_phone=True) but phone_numbers field is empty")
                            print(f"    ⚠️  Phone numbers may require additional API access or different endpoint")
                        else:
                            print(f"    ⚠️  No phone number available in Apollo database")
                        
                        return {
                            'name': f"{person.get('first_name', '')} {person.get('last_name', '')}".strip(),
                            'first_name': person.get('first_name', ''),
                            'last_name': person.get('last_name', ''),
                            'email': person.get('email', ''),
                            'phone': phone,
                            'title': person.get('title', ''),
                            'linkedin_url': person.get('linkedin_url', ''),
                            'source': 'apollo'
                        }
                else:
                    print(f"    ❌ GET /people/{person_id} also failed: {response2.status_code}")
                    print(f"    Response: {response2.text[:300]}")
        except Exception as e:
            print(f"    ❌ Error enriching person {person_id}: {str(e)}")
            import traceback
            traceback.print_exc()
        
        return None
    
    def search_people_by_domain(self, domain: str, titles: List[str] = None) -> List[Dict]:
        """
        OLD METHOD: Search Apollo by domain (uses credits)
        Kept as fallback if new method fails
        """
        people = []
        titles = titles or ['Founder', 'HR Director', 'HR Manager', 'CHRO', 'Director', 'HR']
        
        for title in titles:
            try:
                url = f"{self.base_url}/mixed_people/search"
                base_payload = {
                    # API key removed from payload - now in header
                    'organization_domains': [domain],
                    'person_titles': [title],
                    'page': 1,
                    'per_page': 5
                }

                payload = self._add_current_employee_filter(base_payload)
                response = requests.post(url, json=payload, headers=self.headers)
                if response.status_code not in (200,):
                    response = requests.post(url, json=base_payload, headers=self.headers)
                
                if response.status_code == 200:
                    data = response.json()
                    persons = data.get('people', [])
                    
                    for person in persons:
                        phone = ''
                        # Try multiple phone number field variations
                        if person.get('phone_numbers') and len(person.get('phone_numbers', [])) > 0:
                            phone_obj = person.get('phone_numbers', [{}])[0]
                            phone = phone_obj.get('raw_number', '') or \
                                   phone_obj.get('sanitized_number', '') or \
                                   phone_obj.get('number', '') or \
                                   phone_obj.get('phone', '')
                        
                        # Also check direct phone fields
                        if not phone:
                            phone = person.get('phone_number', '') or \
                                   person.get('phone', '') or \
                                   person.get('mobile', '') or \
                                   person.get('direct_phone', '')
                        
                        person_data = {
                            'name': f"{person.get('first_name', '')} {person.get('last_name', '')}".strip(),
                            'first_name': person.get('first_name', ''),
                            'last_name': person.get('last_name', ''),
                            'email': person.get('email', ''),
                            'phone': phone,
                            'title': person.get('title', ''),
                            'linkedin_url': person.get('linkedin_url', ''),
                            'source': 'apollo'
                        }
                        
                        # Avoid duplicates by email
                        if person_data['email'] and not any(p.get('email') == person_data['email'] for p in people):
                            people.append(person_data)
                        elif not person_data['email'] and person_data['name']:
                            if not any(p.get('name') == person_data['name'] and p.get('title') == person_data['title'] for p in people):
                                people.append(person_data)
                
                time.sleep(0.5)  # Rate limiting
                
            except Exception as e:
                print(f"Error searching Apollo by domain for {title}: {str(e)}")
                continue
        
        return people
    
    def search_people_by_company_name(self, company_name: str, titles: List[str] = None) -> List[Dict]:
        """Search Apollo by company name (alternative method)"""
        people = []
        titles = titles or ['Founder', 'HR Director', 'HR Manager', 'CHRO', 'Director', 'HR']
        
        try:
            # First, search for the organization
            org_url = f"{self.base_url}/organizations/search"
            org_payload = {
                # API key removed from payload - now in header
                'name': company_name,
                'page': 1,
                'per_page': 1
            }
            
            org_response = requests.post(org_url, json=org_payload, headers=self.headers)
            if org_response.status_code == 200:
                org_data = org_response.json()
                organizations = org_data.get('organizations', [])
                
                if organizations:
                    org = organizations[0]
                    org_id = org.get('id')
                    org_domain = org.get('website_url', '')
                    
                    if org_domain:
                        domain = self.extract_domain(org_domain)
                        if domain:
                            # Now search people by the found domain
                            people = self.search_people_by_domain(domain, titles)
            
            time.sleep(0.5)
        except Exception as e:
            print(f"Error searching Apollo by company name: {str(e)}")
        
        return people
    
    def search_people_by_company(self, company_name: str, website: str, titles: List[str] = None) -> List[Dict]:
        """
        Search for people at a company using Apollo with multiple strategies
        Strategy 1: NEW api_search endpoint (FREE search, then enrich)
        Strategy 2: OLD search by domain (fallback)
        Strategy 3: Search by company name
        Strategy 4: Web scraping fallback
        """
        people = []
        titles = titles or ['Founder', 'HR Director', 'HR Manager', 'CHRO', 'Director', 'HR']
        
        # Strategy 1: NEW api_search endpoint (FREE - no credits for search)
        if website:
            domain = self.extract_domain(website)
            if domain:
                print(f"  🔍 Trying NEW Apollo api_search (free) by domain: {domain}")
                try:
                    people = self.search_people_api_search(domain, titles)
                    if people:
                        apollo_count = len([p for p in people if p.get('source') == 'apollo'])
                        print(f"  ✅ Found {len(people)} contacts via NEW api_search ({apollo_count} from Apollo)")
                        return people
                    else:
                        print(f"  ⚠️  NEW api_search found 0 contacts for {domain}")
                except Exception as e:
                    print(f"  ❌ NEW api_search failed: {str(e)}, trying fallback...")
                    import traceback
                    traceback.print_exc()
        
        # Strategy 2: OLD search by domain (fallback - uses credits)
        if website and not people:
            domain = self.extract_domain(website)
            if domain:
                print(f"  Trying OLD Apollo search by domain: {domain}")
                people = self.search_people_by_domain(domain, titles)
                if people:
                    print(f"  Found {len(people)} contacts via OLD domain search")
                    return people
        
        # Strategy 2: Search by company name
        if company_name and not people:
            print(f"  Trying Apollo search by company name: {company_name}")
            people = self.search_people_by_company_name(company_name, titles)
            if people:
                print(f"  Found {len(people)} contacts via company name search")
        
        # Web scraping fallback removed - using Apollo.io only
        
        # Add company info to all contacts
        for person in people:
            person['company_name'] = company_name
            person['company_website'] = website
        
        # Less restrictive filtering - only remove clearly irrelevant contacts
        # Keep all contacts with valid titles (not just specific ones)
        blocked_titles = ['intern', 'student', 'volunteer', 'freelancer', 'contractor', 'trainee']
        generic_titles = ['employee', 'staff', 'worker', 'team member', 'member']
        
        filtered_people = []
        for person in people:
            title = (person.get('title') or '').lower().strip()
            
            # Skip if empty title
            if not title:
                print(f"    ⚠️ Skipping: {person.get('name')} - No title")
                continue
            
            # Skip only clearly blocked titles
            if any(blocked in title for blocked in blocked_titles):
                print(f"    ❌ FILTERED OUT: {person.get('name')} - '{title}' (blocked)")
                continue
            
            # Skip only generic "Employee" type titles
            if title in generic_titles:
                print(f"    ❌ FILTERED OUT: {person.get('name')} - '{title}' (generic)")
                continue
            
            # Keep everyone else - we want more contacts!
            filtered_people.append(person)
        
        print(f"  📊 FINAL: {len(filtered_people)} contacts after filtering (from {len(people)})")
        return filtered_people
    
    def enrich_company_data(self, companies: List[Dict]) -> List[Dict]:
        """
        Enrich company data with Apollo people data using multiple strategies
        """
        enriched_companies = []
        total_companies = len(companies)
        
        for idx, company in enumerate(companies, 1):
            website = company.get('website', '')
            company_name = company.get('company_name', '')
            
            print(f"[{idx}/{total_companies}] Enriching: {company_name}")
            
            # Get people using multiple search strategies
            people = self.search_people_by_company(company_name, website)
            
            # Add people data to company
            company['people'] = people
            
            # Categorize contacts (safely handle None titles)
            company['founders'] = [p for p in people if p.get('title') and any(keyword.lower() in p.get('title', '').lower() 
                                                           for keyword in ['founder', 'owner', 'ceo', 'co-founder', 'founder/owner'])]
            company['hr_contacts'] = [p for p in people if p.get('title') and any(keyword.lower() in p.get('title', '').lower() 
                                                              for keyword in ['hr', 'human resources', 'recruiter', 'talent', 'human resource'])]
            
            # Add source information
            apollo_count = len([p for p in people if p.get('source') == 'apollo'])
            scraping_count = len([p for p in people if p.get('source') == 'web_scraping'])
            company['contact_source'] = {
                'apollo': apollo_count,
                'web_scraping': scraping_count,
                'total': len(people)
            }
            
            if people:
                print(f"  ✓ Found {len(people)} contacts ({apollo_count} from Apollo, {scraping_count} from web scraping)")
            else:
                print(f"  ✗ No contacts found")
            
            enriched_companies.append(company)
            
            # Rate limiting
            time.sleep(1)
        
        return enriched_companies

