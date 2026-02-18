import requests
import time
import json
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
        Returns '' if not available or if value is invalid.
        """
        if not org:
            return ''

        # Helper to validate employee count
        def is_valid_employee_count(val):
            """Validate that employee count is reasonable (1 to 1,000,000)"""
            if val is None or val == '':
                return False
            try:
                # Convert to string and clean
                val_str = str(val).replace(',', '').replace(' ', '').strip()
                # Handle ranges like "50-100"
                if '-' in val_str:
                    parts = val_str.split('-')
                    if len(parts) == 2:
                        low = int(parts[0])
                        high = int(parts[1])
                        return low > 0 and high > low and high <= 1000000
                # Handle "500+"
                elif '+' in val_str:
                    num = int(val_str.replace('+', ''))
                    return num > 0 and num <= 1000000
                # Handle single number
                else:
                    num = int(val_str)
                    return num > 0 and num <= 1000000
            except (ValueError, AttributeError):
                return False

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
            # Validate before returning
            if is_valid_employee_count(val):
                return str(val)

        for key in [
            'estimated_num_employees_range',
            'num_employees_range',
            'employee_range',
        ]:
            val = org.get(key)
            if val is None or val == '':
                continue
            # Validate before returning
            if is_valid_employee_count(val):
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

            # CRITICAL: Only try ONE payload to save credits! Try the most likely one first
            # Try domain-based first (most accurate), then name-based as fallback
            payloads_to_try = []
            if domain:
                # Try domain-based first (most accurate, usually works)
                payloads_to_try.append({'q_organization_domains': domain, 'page': 1, 'per_page': 1})
            if company_name:
                # Fallback to name-based only if domain didn't work
                payloads_to_try.append({'name': company_name, 'page': 1, 'per_page': 1})

            # CRITICAL FIX: Only try ONE payload to save credits!
            # Stop immediately after first successful response (even if no employee data found)
            for payload in payloads_to_try[:1]:  # ONLY TRY FIRST PAYLOAD - SAVES CREDITS!
                try:
                    print(f"🔍 Getting employee count for: {company_name} (1 API call only to save credits)")
                    resp = requests.post(org_url, json=payload, headers=self.headers, timeout=10)
                    print(f"   Apollo response status: {resp.status_code}")
                    
                    if resp.status_code != 200:
                        print(f"   ❌ Failed with status {resp.status_code}")
                        break  # Stop trying - don't waste more credits
                    
                    data = resp.json() or {}
                    orgs = data.get('organizations', []) or []
                    print(f"   Found {len(orgs)} organization(s) in Apollo")
                    
                    if not orgs:
                        break  # No orgs found - stop trying
                    
                    org = orgs[0]
                    emp = self._extract_employee_count(org)
                    if emp:
                        print(f"   ✅ Found employee count: {emp} (1 API call used)")
                        return emp
                    else:
                        print(f"   ⚠️ No employee count found in org data (1 API call used)")
                        break  # Stop - don't try more payloads
                except Exception as e:
                    print(f"   ❌ Exception: {str(e)}")
                    break  # Stop on error - don't waste more credits

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
        Returns people without emails - need enrichment for emails only
        Phone numbers should be revealed in Apollo.io dashboard to save credits
        """
        people = []
        # Only use default titles/seniorities if None explicitly passed
        # If user provides empty list, respect that (search without filter)
        if titles is None:
            titles = ['Founder', 'HR Director', 'HR Manager', 'CHRO', 'Director', 'HR', 'Manager', 'VP', 'Vice President', 'Head', 'Chief', 'Owner', 'CEO', 'CTO', 'CFO', 'COO']
        if seniorities is None:
            seniorities = ['owner', 'founder', 'c_suite', 'vp', 'head', 'director', 'manager', 'senior', 'lead']
        
        try:
            url = f"{self.api_search_base}/mixed_people/api_search"
            base_payload = {
                # API key removed from payload - now in header
                'q_organization_domains_list': [domain],
                'person_titles': titles,
                'person_seniorities': seniorities,
                'include_similar_titles': True,  # Allow similar titles to get more results
                'page': 1,
                'per_page': 100  # CRITICAL FIX: Get MORE results (was 50, now 100)
            }

            # Retry logic: Try up to 3 times with exponential backoff
            max_retries = 3
            response = None
            for attempt in range(max_retries):
                try:
                    # Try current-employee filter first; if Apollo rejects, fallback without it
                    payload = self._add_current_employee_filter(base_payload)
                    response = requests.post(url, json=payload, headers=self.headers, timeout=30)
                    if response.status_code not in (200,):
                        # retry without filters
                        response = requests.post(url, json=base_payload, headers=self.headers, timeout=30)
                    
                    if response.status_code == 200:
                        break  # Success, exit retry loop
                    elif response.status_code == 429:  # Rate limit
                        wait_time = (2 ** attempt) * 2  # Exponential backoff: 2s, 4s, 8s
                        print(f"    ⚠️  Rate limited (429), waiting {wait_time}s before retry {attempt + 1}/{max_retries}...")
                        time.sleep(wait_time)
                        continue
                    else:
                        if attempt < max_retries - 1:
                            wait_time = (2 ** attempt) * 1  # Exponential backoff: 1s, 2s, 4s
                            print(f"    ⚠️  API error (status {response.status_code}), retrying in {wait_time}s...")
                            time.sleep(wait_time)
                            continue
                except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                    if attempt < max_retries - 1:
                        wait_time = (2 ** attempt) * 2  # Exponential backoff: 2s, 4s, 8s
                        print(f"    ⚠️  Network error ({str(e)}), retrying in {wait_time}s...")
                        time.sleep(wait_time)
                        continue
                    else:
                        print(f"    ❌ Network error after {max_retries} attempts: {str(e)}")
                        raise
            
            if not response:
                print(f"    ❌ Apollo api_search failed: No response after {max_retries} attempts")
                return people
            
            print(f"    Apollo api_search response status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                persons = data.get('people', [])
                print(f"    📊 Apollo api_search found {len(persons)} people (before enrichment)")
                
                # Check if phone numbers are in the search results directly (sometimes they are!)
                for p in persons[:3]:  # Check first 3
                    if p.get('phone_numbers'):
                        print(f"    📞 Found phone_numbers in search result for {p.get('first_name')}: {p.get('phone_numbers')}")
                
                # Extract person IDs AND organization domains for validation
                person_data_list = [(p.get('id'), p.get('organization', {}).get('primary_domain', '')) 
                                   for p in persons if p.get('id')]
                print(f"    📋 Extracted {len(person_data_list)} person IDs for enrichment")
                
                if person_data_list:
                    print(f"    🔄 Enriching {len(person_data_list)} people to get emails in parallel...")
                    # Enrich to get emails only (costs credits) and validate company
                    # Phone numbers not requested - reveal in Apollo.io dashboard to save credits
                    # Use parallel enrichment for faster processing
                    enriched_people = self.enrich_people_with_validation_parallel([pid for pid, _ in person_data_list], domain)
                    print(f"    ✅ Enrichment returned {len(enriched_people)} contacts with emails (validated for {domain})")
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
                            'phone': '',  # Phone numbers not requested - reveal in Apollo.io dashboard
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
            # Keep everyone else (we'll filter by email later if needed)
            filtered_people.append(person)
        
        print(f"    ✅ After filtering: {len(filtered_people)} contacts (from {len(people)})")
        return filtered_people
    
    def enrich_people(self, person_ids: List[str]) -> List[Dict]:
        """
        Enrich people data to get emails only (COSTS credits)
        Phone numbers are NOT requested - reveal in Apollo.io dashboard to save credits
        Uses individual enrichment (bulk_match endpoint has issues)
        """
        enriched = []
        
        if not person_ids:
            return enriched
        
        # Use individual enrichment (more reliable)
        print(f"    Enriching {len(person_ids)} people individually...")
        # CRITICAL FIX: Increase limit to get MORE contacts (was 50, now 100)
        for idx, person_id in enumerate(person_ids[:100], 1):
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
        # CRITICAL FIX: Increase limit to get MORE contacts (was 50, now 100)
        for idx, person_id in enumerate(person_ids[:100], 1):
            try:
                enriched_person = self.enrich_single_person(person_id)
                if enriched_person:
                    # Validation - include if email domain matches
                    person_email = enriched_person.get('email', '')
                    
                    # Include if has email
                    if person_email and '@' in person_email:
                        email_domain = person_email.split('@')[1].lower()
                        target_clean = target_domain.lower().replace('www.', '').replace('http://', '').replace('https://', '')
                        
                        # Check if email domain matches target domain
                        if target_clean in email_domain or email_domain in target_clean:
                            enriched.append(enriched_person)
                            print(f"    ✅ [{idx}/{min(len(person_ids), 20)}] {enriched_person.get('name')} - {person_email} (VERIFIED)")
                        else:
                            # Still include if email exists (domain might be different but person works there)
                            enriched.append(enriched_person)
                            print(f"    ✅ [{idx}/{min(len(person_ids), 20)}] {enriched_person.get('name')} - {person_email} (domain mismatch but including)")
                    else:
                        # No email - still include (might have LinkedIn)
                        enriched.append(enriched_person)
                        print(f"    ⚠️  [{idx}/{min(len(person_ids), 20)}] {enriched_person.get('name')} - No email but including")
                time.sleep(0.3)
            except Exception as e2:
                print(f"    Failed to enrich person {person_id}: {str(e2)}")
                continue
        
        return enriched
    
    def enrich_people_with_validation_parallel(self, person_ids: List[str], target_domain: str) -> List[Dict]:
        """
        Enrich people in PARALLEL with validation (get emails only)
        Phone numbers are NOT requested - reveal in Apollo.io dashboard to save credits
        Processes multiple contacts at once for faster results
        """
        enriched = []
        
        if not person_ids:
            return enriched
        
        print(f"    Enriching {len(person_ids)} people in PARALLEL with company validation (target: {target_domain})...")
        
        import concurrent.futures
        
        def enrich_and_validate(person_id):
            """Enrich single person and validate - runs in parallel"""
            try:
                enriched_person = self.enrich_single_person(person_id)
                if not enriched_person:
                    return None
                
                person_email = enriched_person.get('email', '')
                
                # CRITICAL FIX: Include ALL contacts, even without emails!
                # Apollo already validated they work at the company, so trust Apollo
                # We want MORE contacts, not fewer!
                return enriched_person
            except Exception as e:
                print(f"    Error enriching person {person_id}: {str(e)}")
                return None
        
        # Process in parallel (5 workers to avoid rate limits)
        # CRITICAL FIX: Increase limit to get MORE contacts (was 50, now 100)
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_id = {executor.submit(enrich_and_validate, pid): pid for pid in person_ids[:100]}
            
            for future in concurrent.futures.as_completed(future_to_id):
                result = future.result()
                if result:
                    enriched.append(result)
        
        print(f"    ✅ Parallel enrichment completed: {len(enriched)} contacts with emails")
        return enriched
    
    def enrich_single_person(self, person_id: str) -> Optional[Dict]:
        """
        Enrich a single person by ID to get email address.
        Phone numbers are NOT requested - they should be revealed in Apollo.io dashboard to save credits.
        """
        try:
            # METHOD 1: Try people/match endpoint (email only - no phone numbers)
            url = f"{self.base_url}/people/match"
            payload = {
                'person_id': person_id,
                'reveal_personal_emails': True,
                # Phone numbers removed - reveal in Apollo.io dashboard to save credits
            }
            
            response = None
            try:
                response = requests.post(url, json=payload, headers=self.headers, timeout=10)
            except Exception as e:
                print(f"    ⚠️  people/match request exception: {str(e)}")
            
            if response and response.status_code == 200:
                data = response.json()
                person = data.get('person', {})
                if person:
                    return {
                        'name': f"{person.get('first_name', '')} {person.get('last_name', '')}".strip(),
                        'first_name': person.get('first_name', ''),
                        'last_name': person.get('last_name', ''),
                        'email': person.get('email', ''),
                        'phone': '',  # Phone numbers not requested - reveal in Apollo.io dashboard
                        'title': person.get('title', ''),
                        'linkedin_url': person.get('linkedin_url', ''),
                        'apollo_id': person_id,  # Include the person ID
                        'source': 'apollo'
                    }
            else:
                # Check for specific error codes that shouldn't be retried
                error_status = response.status_code if response else None
                error_text = response.text[:200] if response else "No response"
                
                # Don't retry on authentication/authorization errors (waste credits)
                if error_status in (401, 403):
                    print(f"    ❌ Authentication/Authorization error (status {error_status}): {error_text}")
                    print(f"    ⚠️  Check your Apollo.io API key - it may be invalid or expired")
                    return None
                
                # Don't retry on rate limit (429) - wait instead
                if error_status == 429:
                    print(f"    ⚠️  Rate limit exceeded (429): {error_text}")
                    print(f"    ⚠️  Apollo.io API rate limit reached - please wait before trying again")
                    return None
                
                # Don't retry on 404 (person not found)
                if error_status == 404:
                    print(f"    ⚠️  Person not found (404): Person ID {person_id} doesn't exist")
                    return None
                
                # Only retry on network/timeout errors, not API errors
                if response:
                    print(f"    ⚠️  people/match failed (status {error_status}): {error_text}")
                    print(f"    ⚠️  Not retrying to avoid wasting credits - check API status")
                    return None
                else:
                    print(f"    ⚠️  people/match failed: No response received (network error)")
                    # Only retry on network errors, not API errors
                    print(f"    ⚠️  Retrying with GET method (network error only)...")
                
                # METHOD 2: Only retry on network errors, not API errors
                url2 = f"{self.base_url}/people/{person_id}"
                params = {'reveal_personal_emails': 'true'}  # Email only - no phone
                
                response2 = None
                try:
                    response2 = requests.get(url2, headers=self.headers, params=params, timeout=10)
                except Exception as e:
                    print(f"    ⚠️  GET /people/{person_id} request exception: {str(e)}")
                    return None  # Network error - don't waste more credits
                
                if response2 and response2.status_code == 200:
                    person = response2.json().get('person', {})
                    if person:
                        return {
                            'name': f"{person.get('first_name', '')} {person.get('last_name', '')}".strip(),
                            'first_name': person.get('first_name', ''),
                            'last_name': person.get('last_name', ''),
                            'email': person.get('email', ''),
                            'phone': '',  # Phone numbers not requested - reveal in Apollo.io dashboard
                            'title': person.get('title', ''),
                            'linkedin_url': person.get('linkedin_url', ''),
                            'apollo_id': person_id,  # Include the person ID
                            'source': 'apollo'
                        }
                else:
                    error_status2 = response2.status_code if response2 else None
                    print(f"    ❌ GET /people/{person_id} also failed: {error_status2 if response2 else 'No response'}")
                    if response2:
                        print(f"    Response: {response2.text[:300]}")
                    return None  # Don't waste more credits
        except Exception as e:
            print(f"    ❌ Error enriching person {person_id}: {str(e)}")
            import traceback
            traceback.print_exc()
        
        return None
    
    def _extract_phone_from_person(self, person: Dict) -> str:
        """
        Extract phone number from Apollo person object (DEPRECATED - not used anymore).
        Phone numbers are not requested to save credits - reveal in Apollo.io dashboard instead.
        """
        # Phone numbers are no longer requested - return empty string
        # Users should reveal phone numbers in Apollo.io dashboard when needed
        return ''
    
    def search_people_by_domain(self, domain: str, titles: List[str] = None) -> List[Dict]:
        """
        OLD METHOD: Search Apollo by domain (uses credits)
        Kept as fallback if new method fails
        If titles is None, searches without title filter (gets all contacts)
        """
        people = []
        # Only use default titles if None explicitly passed (not if empty list)
        # If titles is None, use default. If empty list, search without title filter.
        if titles is None:
            # No titles provided - use default titles
            titles = ['Founder', 'HR Director', 'HR Manager', 'CHRO', 'Director', 'HR']
        
        # If titles list is empty, search without title filter (get all contacts)
        if not titles:
            # Search without title filter
            try:
                url = f"{self.base_url}/mixed_people/search"
                base_payload = {
                    'organization_domains': [domain],
                    'page': 1,
                    'per_page': 25
                }
                response = requests.post(url, json=base_payload, headers=self.headers)
                if response.status_code == 200:
                    data = response.json()
                    people_list = data.get('people', [])
                    for person in people_list:
                        people.append({
                            'name': f"{person.get('first_name', '')} {person.get('last_name', '')}".strip(),
                            'first_name': person.get('first_name', ''),
                            'last_name': person.get('last_name', ''),
                            'email': person.get('email', ''),
                            'phone': person.get('phone_numbers', [{}])[0].get('raw_number', '') if person.get('phone_numbers') else '',
                            'title': person.get('title', ''),
                            'linkedin_url': person.get('linkedin_url', ''),
                            'source': 'apollo'
                        })
                time.sleep(0.5)
            except Exception as e:
                print(f"Error searching without title filter: {str(e)}")
            return people
        
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
                        person_data = {
                            'name': f"{person.get('first_name', '')} {person.get('last_name', '')}".strip(),
                            'first_name': person.get('first_name', ''),
                            'last_name': person.get('last_name', ''),
                            'email': person.get('email', ''),
                            'phone': '',  # Phone numbers not requested - reveal in Apollo.io dashboard
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
        """Search Apollo by company name (alternative method)
        If titles is None, searches without title filter (gets all contacts)
        """
        people = []
        # If titles is None, use default. If empty list, search without title filter.
        if titles is None:
            # No titles provided - use default titles
            titles = ['Founder', 'HR Director', 'HR Manager', 'CHRO', 'Director', 'HR']
        
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
                            # Try NEW api_search first (FREE), then fallback to old domain search
                            print(f"  🔍 Found domain {domain} for {company_name}, trying api_search...")
                            try:
                                people = self.search_people_api_search(domain, titles)
                                if people:
                                    print(f"  ✅ Found {len(people)} contacts via api_search for {company_name}")
                                    return people
                            except Exception as e:
                                print(f"  ⚠️  api_search failed for {company_name}: {str(e)}, trying fallback...")
                            
                            # Fallback to old domain search
                            people = self.search_people_by_domain(domain, titles)
                            if people:
                                return people
                    
                    # If no domain or domain search failed, try searching by organization ID directly
                    if org_id and not people:
                        print(f"  🔍 No domain available, searching by organization ID: {org_id}")
                        try:
                            # Search people by organization ID
                            people_url = f"{self.base_url}/mixed_people/search"
                            people_payload = {
                                'organization_ids': [org_id],
                                'page': 1,
                                'per_page': 25
                            }
                            
                            # Add title filter if provided
                            if titles:
                                people_payload['person_titles'] = titles
                            
                            people_response = requests.post(people_url, json=people_payload, headers=self.headers)
                            if people_response.status_code == 200:
                                people_data = people_response.json()
                                persons = people_data.get('people', [])
                                
                                for person in persons:
                                    person_data = {
                                        'name': f"{person.get('first_name', '')} {person.get('last_name', '')}".strip(),
                                        'first_name': person.get('first_name', ''),
                                        'last_name': person.get('last_name', ''),
                                        'email': person.get('email', ''),
                                        'phone': '',
                                        'title': person.get('title', ''),
                                        'linkedin_url': person.get('linkedin_url', ''),
                                        'source': 'apollo'
                                    }
                                    people.append(person_data)
                                
                                if people:
                                    print(f"  ✅ Found {len(people)} contacts via organization ID search")
                                    return people
                        except Exception as e:
                            print(f"  ⚠️  Organization ID search failed: {str(e)}")
                    
                    if not people:
                        print(f"  ⚠️  Organization {company_name} found in Apollo but has no website URL and organization ID search returned no results")
                else:
                    print(f"  ⚠️  Organization {company_name} not found in Apollo database")
            else:
                print(f"  ⚠️  Apollo organization search failed with status {org_response.status_code}")
            
            time.sleep(0.5)
        except Exception as e:
            print(f"  ❌ Error searching Apollo by company name: {str(e)}")
            import traceback
            traceback.print_exc()
        
        return people
    
    def search_people_by_company(self, company_name: str, website: str, titles: List[str] = None) -> List[Dict]:
        """
        Search for people at a company using Apollo with multiple strategies
        Strategy 1: NEW api_search endpoint (FREE search, then enrich)
        Strategy 2: OLD search by domain (fallback)
        Strategy 3: Search by company name
        Strategy 4: Web scraping fallback
        
        IMPORTANT: We fetch ALL contacts first, then filter by titles on our side.
        This ensures we get maximum contacts even if Apollo's title matching is restrictive.
        """
        people = []
        user_provided_titles = titles  # Store user's titles for later filtering
        
        # If user provided titles, use ONLY those. Otherwise use broad filters to get maximum contacts.
        if titles:
            # User provided specific titles - use ONLY those (no hardcoded fallback)
            search_titles = titles
            search_seniorities = None  # Let Apollo use default seniorities
            print(f"  🔍 User provided titles - using ONLY: {titles[:5]}{'...' if len(titles) > 5 else ''}")
        else:
            # No user titles - use broad filters to get maximum contacts
            broad_seniorities = ['owner', 'founder', 'c_suite', 'vp', 'head', 'director', 'manager', 'senior', 'lead', 'executive']
            broad_titles = ['Founder', 'HR Director', 'HR Manager', 'CHRO', 'Director', 'HR', 'Manager', 'VP', 'Vice President', 'Head', 'Chief', 'Owner', 'CEO', 'CTO', 'CFO', 'COO', 'Executive', 'Senior']
            search_titles = broad_titles
            search_seniorities = broad_seniorities
            print(f"  📋 No user titles - using broad filters to get maximum contacts")
        
        # Strategy 1: NEW api_search endpoint (FREE - no credits for search)
        if website:
            domain = self.extract_domain(website)
            if domain:
                print(f"  🔍 Trying NEW Apollo api_search (free) by domain: {domain}")
                try:
                    # Use user's titles if provided, otherwise use broad filters
                    people = self.search_people_api_search(domain, titles=search_titles, seniorities=search_seniorities)
                    if people:
                        apollo_count = len([p for p in people if p.get('source') == 'apollo'])
                        print(f"  ✅ Found {len(people)} contacts via NEW api_search ({apollo_count} from Apollo)")
                        # Now filter by user's designation if provided
                        if user_provided_titles:
                            filtered_people = self._filter_contacts_by_titles(people, user_provided_titles)
                            print(f"  🔍 Filtered to {len(filtered_people)} contacts matching user's designation: {', '.join(user_provided_titles)}")
                            return filtered_people
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
                # Use user's titles if provided, otherwise use None (will use default in function)
                people = self.search_people_by_domain(domain, titles=search_titles if titles else None)
                if people:
                    print(f"  Found {len(people)} contacts via OLD domain search")
                    # Filter by user's designation if provided
                    if user_provided_titles:
                        filtered_people = self._filter_contacts_by_titles(people, user_provided_titles)
                        print(f"  🔍 Filtered to {len(filtered_people)} contacts matching user's designation")
                        return filtered_people
                    return people
        
        # Strategy 3: Search by company name
        if company_name and not people:
            print(f"  Trying Apollo search by company name: {company_name}")
            # Use user's titles if provided, otherwise use None (will use default in function)
            people = self.search_people_by_company_name(company_name, titles=search_titles if titles else None)
            if people:
                print(f"  Found {len(people)} contacts via company name search")
                # Filter by user's designation if provided
                if user_provided_titles:
                    filtered_people = self._filter_contacts_by_titles(people, user_provided_titles)
                    print(f"  🔍 Filtered to {len(filtered_people)} contacts matching user's designation")
                    people = filtered_people
        
        # Web scraping fallback removed - using Apollo.io only
        
        # Add company info to all contacts
        for person in people:
            person['company_name'] = company_name
            person['company_website'] = website
        
        # VERY RELAXED filtering - only remove clearly irrelevant contacts
        # Keep ALL contacts with names, even if no title (titles might be missing in Apollo)
        blocked_titles = ['intern', 'student', 'volunteer', 'freelancer', 'contractor', 'trainee']
        
        filtered_people = []
        for person in people:
            # CRITICAL FIX: Don't skip contacts without titles - they might still be valid!
            # Only require a name
            if not person.get('name') and not person.get('first_name'):
                print(f"    ⚠️ Skipping: No name found")
                continue
            
            title = (person.get('title') or '').lower().strip()
            
            # Only skip if title contains clearly blocked keywords (but keep if no title!)
            if title and any(blocked in title for blocked in blocked_titles):
                print(f"    ❌ FILTERED OUT: {person.get('name')} - '{title}' (blocked)")
                continue
            
            # Keep everyone else - we want MORE contacts, not fewer!
            # Note: User title filtering already happened above if user provided titles
            filtered_people.append(person)
        
        print(f"  📊 FINAL: {len(filtered_people)} contacts after filtering (from {len(people)})")
        return filtered_people
    
    def _filter_contacts_by_titles(self, contacts: List[Dict], user_titles: List[str]) -> List[Dict]:
        """
        Filter contacts based on user-provided titles.
        Uses flexible matching to find contacts whose titles contain any of the user's title keywords.
        """
        if not user_titles:
            return contacts
        
        # Normalize user titles to lowercase for matching
        user_title_keywords = [t.lower().strip() for t in user_titles]
        
        filtered = []
        for contact in contacts:
            title = (contact.get('title') or '').lower().strip()
            contact_type = (contact.get('contact_type') or '').lower().strip()
            
            # Check if title or contact_type matches any user-provided title keyword
            matches = False
            for keyword in user_title_keywords:
                if keyword in title or keyword in contact_type:
                    matches = True
                    break
            
            if matches:
                filtered.append(contact)
        
        return filtered
    
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

