import requests
import time
import json
import re
import logging
from typing import List, Dict, Optional
from config import Config

logger = logging.getLogger(__name__)

# region agent log helper
def _agent_debug_log(hypothesis_id: str, location: str, message: str, data: Dict):
    """
    Lightweight NDJSON logger for debugging Apollo credit usage vs data returned.
    Writes to the dedicated debug log file for this session.
    """
    try:
        payload = {
            "sessionId": "b341be",
            "runId": "initial",
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data or {},
            "timestamp": int(time.time() * 1000),
        }
        with open("/Users/sujalpatel/Documents/lead Automation /.cursor/debug-b341be.log", "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        # Never let debug logging break the main flow
        pass
# endregion

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

        # region agent log
        _agent_debug_log(
            hypothesis_id="INIT",
            location="apollo_client.py:__init__",
            message="apollo_client_initialized",
            data={
                "has_api_key": bool(self.api_key),
                "base_url": self.base_url,
                "api_search_base": self.api_search_base,
            },
        )
        # endregion

    def _normalize_domain(self, d: str) -> str:
        if not d:
            return ''
        d = (d or '').strip().lower().replace('www.', '').split('/')[0].split('?')[0]
        return d

    def _email_domain_matches(self, email: str, company_domain: str) -> bool:
        """Return True if email is at company_domain or a subdomain (e.g. mail.company.com)."""
        if not email or '@' not in email or not company_domain:
            return False
        email_domain = email.split('@', 1)[1].strip().lower()
        company_clean = self._normalize_domain(company_domain)
        if not company_clean:
            return False
        return email_domain == company_clean or email_domain.endswith('.' + company_clean)

    def _person_org_matches_domain(self, person: Dict, domain: str) -> bool:
        """Return True if the person's organization primary_domain matches the search domain,
        or if org data is missing (api_search free tier often omits it — trust Apollo's match)."""
        if not domain:
            return True
        org = person.get('organization') or {}
        org_domain = (org.get('primary_domain') or '').strip().lower()
        if not org_domain:
            return True
        return self._normalize_domain(org_domain) == self._normalize_domain(domain)

    def _person_org_matches_company_name(self, person: Dict, company_name: str) -> bool:
        """Return True only if the person's organization name matches the search company (strict match).
        Requires the first significant token of our company name to appear in Apollo's org name
        so we don't match unrelated companies (e.g. 'Solutions India' for 'Natech Solutions')."""
        if not company_name:
            return True
        org = person.get('organization') or {}
        org_name = (org.get('name') or '').strip().lower()
        if not org_name:
            return False  # No org in response = cannot verify, reject to avoid wrong contacts
        # Normalize: remove common suffixes for comparison
        def key_part(name):
            s = (name or '').lower().strip()
            for suf in [' pvt.', ' pvt', ' ltd.', ' ltd', ' limited', ' private', ' (india)', ' india']:
                s = re.sub(re.escape(suf) + r'\b', '', s, flags=re.IGNORECASE)
            return re.sub(r'\s+', ' ', s).strip()
        want = key_part(company_name)
        got = key_part(org_name)
        if not want:
            return False
        # Require first significant token of search company to appear in org name (e.g. "natech" for "Natech Solutions")
        want_tokens = [t for t in want.split() if len(t) > 1]
        first_token = want_tokens[0] if want_tokens else want.split()[0][:10]
        if first_token and first_token not in got:
            return False
        # Then require meaningful overlap: either full want in got, or got in want (same company, different wording)
        return want in got or got in want or (len(want) >= 6 and want[:15] in got) or (len(got) >= 6 and got[:15] in want)

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

        # Trial: send industry via Apollo custom field so client can filter by industry in People
        industry = (contact.get('industry') or '').strip()
        field_id = getattr(Config, 'APOLLO_INDUSTRY_CUSTOM_FIELD_ID', None) or None
        if industry and field_id:
            payload['typed_custom_fields'] = {field_id: industry}

        # Lists in Apollo: pass list name(s) so contact appears in that list (Apollo creates list if needed)
        label_names = contact.get('label_names')
        if not label_names and contact.get('list_name'):
            label_names = [contact.get('list_name')]
        if label_names:
            payload['label_names'] = [str(n).strip() for n in label_names if str(n).strip()]

        endpoints = [
            (f"{self.api_search_base}/contacts", payload),  # Official: api/v1/contacts
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

    def get_contact_custom_fields(self) -> List[Dict]:
        """
        Fetch custom fields for contacts (used to find Industry field ID for APOLLO_INDUSTRY_CUSTOM_FIELD_ID).
        Requires master API key. Returns list of {id, name, type, modality}.
        """
        out = []
        try:
            url = f"{self.api_search_base}/typed_custom_fields"
            resp = requests.get(url, headers=self.headers, timeout=10)
            if resp.status_code != 200:
                return out
            data = resp.json() or {}
            for f in (data.get('typed_custom_fields') or []):
                if (f.get('modality') or '').lower() == 'contact':
                    out.append({
                        'id': f.get('id'),
                        'name': f.get('name'),
                        'type': f.get('type', ''),
                        'modality': f.get('modality', '')
                    })
        except Exception as e:
            logger.error(f"get_contact_custom_fields error: {e}")
        return out

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
            # Apollo list endpoints use api/v1 base (docs: https://api.apollo.io/api/v1)
            base = getattr(self, 'api_search_base', None) or 'https://api.apollo.io/api/v1'
            url = f"{base}/contact_lists"
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
        base = getattr(self, 'api_search_base', None) or 'https://api.apollo.io/api/v1'
        endpoints = [
            (f"{base}/contact_lists/{list_id}/contacts", {'contact_ids': [contact_id]}),
            (f"{base}/contact_lists/{list_id}/contacts", {'contacts': [{'id': contact_id}]}),
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

    def create_account(self, name: str, domain: str = '', phone: str = '', raw_address: str = '') -> Dict:
        """
        Create a company (account) in Apollo.io Companies section.
        Requires at least name or domain. Returns {success: bool, account_id?: str, error?: str}.
        """
        name = (name or '').strip()
        domain = (domain or '').strip().replace('www.', '').split('/')[0].split('?')[0]
        if not name and not domain:
            return {'success': False, 'error': 'At least name or domain is required'}
        payload = {}
        if name:
            payload['name'] = name
        if domain:
            payload['domain'] = domain
        if phone:
            payload['phone'] = phone
        if raw_address:
            payload['raw_address'] = raw_address
        try:
            url = f"{self.api_search_base}/accounts"
            resp = requests.post(url, json=payload, headers=self.headers, timeout=15)
            if resp.status_code in (200, 201):
                data = resp.json() if resp.content else {}
                acc = (data.get('account') or data) if isinstance(data, dict) else {}
                aid = acc.get('id') if isinstance(acc, dict) else None
                return {'success': True, 'account_id': aid, 'response': data}
            return {'success': False, 'error': f"{resp.status_code}: {(resp.text or '')[:200]}"}
        except Exception as e:
            return {'success': False, 'error': str(e)}

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
                    logger.info(f"Getting employee count for: {company_name} (1 API call only to save credits)")
                    resp = requests.post(org_url, json=payload, headers=self.headers, timeout=10)
                    logger.info(f"Apollo response status: {resp.status_code}")
                    
                    if resp.status_code != 200:
                        logger.error(f"Failed with status {resp.status_code}")
                        break  # Stop trying - don't waste more credits
                    
                    data = resp.json() or {}
                    orgs = data.get('organizations', []) or []
                    logger.info(f"Found {len(orgs)} organization(s) in Apollo")
                    
                    if not orgs:
                        break  # No orgs found - stop trying
                    
                    org = orgs[0]
                    emp = self._extract_employee_count(org)
                    if emp:
                        logger.info(f"Found employee count: {emp} (1 API call used)")
                        return emp
                    else:
                        logger.warning(f"No employee count found in org data (1 API call used)")
                        break  # Stop - don't try more payloads
                except Exception as e:
                    logger.error(f"Exception: {str(e)}")
                    break  # Stop on error - don't waste more credits

        except Exception as e:
            logger.error(f"Error getting company total employees from Apollo: {str(e)}")

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
            # REMOVED STRICT FILTERS: Don't send person_titles or person_seniorities to Apollo
            # This lets Apollo return ALL contacts for the domain, then we filter locally
            base_payload = {
                # API key removed from payload - now in header
                'q_organization_domains_list': [domain],
                # REMOVED: 'person_titles': titles,  # Too strict - let Apollo return all contacts
                # REMOVED: 'person_seniorities': seniorities,  # Too strict - filter locally instead
                'include_similar_titles': True,  # Get more results from Apollo
                'page': 1,
                'per_page': getattr(Config, 'APOLLO_API_SEARCH_PER_PAGE', 100)
            }
            # DEBUG: Log what we're sending to Apollo
            logger.debug(f"api_search domain={domain}")

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
                    elif response.status_code in (400, 401, 403, 404):
                        logger.error(f"Non-retryable error ({response.status_code}), stopping")
                        break
                    elif response.status_code == 429:  # Rate limit
                        wait_time = (2 ** attempt) * 2  # Exponential backoff: 2s, 4s, 8s
                        logger.warning(f"Rate limited (429), waiting {wait_time}s before retry {attempt + 1}/{max_retries}...")
                        time.sleep(wait_time)
                        continue
                    elif response.status_code >= 500:
                        if attempt < max_retries - 1:
                            wait_time = (2 ** attempt) * 1  # Exponential backoff: 1s, 2s, 4s
                            logger.warning(f"Server error (status {response.status_code}), retrying in {wait_time}s...")
                            time.sleep(wait_time)
                            continue
                    else:
                        logger.warning(f"Unexpected status {response.status_code}, not retrying")
                        break
                except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                    if attempt < max_retries - 1:
                        wait_time = (2 ** attempt) * 2  # Exponential backoff: 2s, 4s, 8s
                        logger.warning(f"Network error ({str(e)}), retrying in {wait_time}s...")
                        time.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"Network error after {max_retries} attempts: {str(e)}")
                        raise
            
            if not response:
                logger.error(f"Apollo api_search failed: No response after {max_retries} attempts")
                # region agent log
                _agent_debug_log(
                    hypothesis_id="A",
                    location="apollo_client.py:search_people_api_search",
                    message="api_search_no_response",
                    data={
                        "domain": domain,
                        "status": None,
                        "attempts": max_retries,
                    },
                )
                # endregion
                return people
            
            logger.debug(f"api_search status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                persons = data.get('people', [])
                logger.debug(f"api_search found {len(persons)} people before filter")
                # CRITICAL: Keep only people whose organization actually matches this domain (fix wrong data mix-up)
                before_org = len(persons)
                persons = [p for p in persons if self._person_org_matches_domain(p, domain)]
                if before_org != len(persons):
                    logger.info(f"Org validation: kept {len(persons)} contacts that match domain {domain} (removed {before_org - len(persons)} from other orgs)")
                
                # DEBUG: Show sample titles from Apollo to understand what we're getting
                if persons and len(persons) > 0:
                    sample_titles = [p.get('title', 'No Title') for p in persons[:5]]
                    logger.debug(f"Sample titles: {sample_titles}")
                
                # CRITICAL: Filter by titles BEFORE enrichment to save API credits!
                # Use smart matching: user's exact input matches various title formats
                # But NO hardcoded keyword expansions - use only what user entered
                if titles:
                    user_titles_lower = [t.lower().strip() for t in titles]
                    excluded_titles = ['employee', 'staff', 'worker', 'member', 'personnel']
                    filtered_persons = []
                    for p in persons:
                        person_title = (p.get('title') or '').lower().strip()
                        # KEEP people with empty/missing titles (api_search free tier often omits titles)
                        if not person_title:
                            filtered_persons.append(p)
                            continue
                        if person_title in excluded_titles:
                            continue
                        matches = False
                        for user_title in user_titles_lower:
                            if user_title in person_title:
                                matches = True
                                break
                            if re.search(r'\b' + re.escape(user_title) + r'\b', person_title):
                                matches = True
                                break
                            if user_title == 'hr' and 'human resources' in person_title:
                                matches = True
                                break
                            if user_title == 'ceo' and 'chief executive' in person_title:
                                matches = True
                                break
                            if user_title == 'cto' and ('chief technology' in person_title or 'chief technical' in person_title):
                                matches = True
                                break
                            if user_title == 'cfo' and 'chief financial' in person_title:
                                matches = True
                                break
                            if user_title == 'coo' and 'chief operating' in person_title:
                                matches = True
                                break
                            if user_title == 'chro' and ('chief human resources' in person_title or 'chief hr' in person_title):
                                matches = True
                                break
                        
                        if matches and person_title not in excluded_titles:
                            filtered_persons.append(p)
                    
                    original_count = len(persons)
                    persons = filtered_persons
                    if original_count != len(persons):
                        logger.info(f"FILTERED: {original_count} -> {len(persons)} contacts (saved {original_count - len(persons)} enrichment credits!)")
                        if original_count > 0 and len(persons) == 0:
                            logger.warning(f"All {original_count} contacts were filtered out!")
                            logger.warning(f"User titles: {user_titles_lower}")
                            logger.warning(f"Sample filtered titles: {[(p.get('title', 'No Title'), p.get('name', 'No Name')) for p in data.get('people', [])[:3]]}")
                    elif original_count == 0:
                        logger.warning(f"Apollo returned 0 contacts - check if company exists in Apollo database")
                
                # Check if phone numbers are in the search results directly (sometimes they are!)
                for p in persons[:3]:  # Check first 3
                    if p.get('phone_numbers'):
                        logger.debug(f"Found phone_numbers in search result for {p.get('first_name')}: {p.get('phone_numbers')}")
                
                # CRITICAL: Only enrich if we have contacts after filtering (saves credits!)
                # If filtering removed all contacts, skip enrichment completely
                if not persons or len(persons) == 0:
                    logger.warning(f"No contacts found after filtering - SKIPPING enrichment (saved credits!)")
                    logger.info(f"CREDIT USAGE: 0 credits (no contacts to enrich)")
                    # region agent log
                    _agent_debug_log(
                        hypothesis_id="A",
                        location="apollo_client.py:search_people_api_search",
                        message="api_search_zero_after_filter",
                        data={
                            "domain": domain,
                            "titles": titles or [],
                            "initial_count": before_org,
                            "final_count": 0,
                        },
                    )
                    # endregion
                    return people
                
                # Extract person IDs AND organization domains for validation
                # NOW only extracting IDs for filtered contacts (saves credits!)
                person_data_list = [(p.get('id'), p.get('organization', {}).get('primary_domain', '')) 
                                   for p in persons if p.get('id')]
                logger.info(f"Extracted {len(person_data_list)} person IDs for enrichment (AFTER filtering)")
                
                # CRITICAL: Only enrich if we have person IDs (prevents wasting credits on empty results)
                if person_data_list and len(person_data_list) > 0:
                    logger.info(f"Enriching {len(person_data_list)} people to get emails in parallel...")
                    logger.info(f"CREDIT USAGE: Will use ~{len(person_data_list)} credits for enrichment")
                    # Enrich to get emails only (costs credits) and validate company
                    # Phone numbers not requested - reveal in Apollo.io dashboard to save credits
                    # Use parallel enrichment for faster processing
                    enriched_people = self.enrich_people_with_validation_parallel([pid for pid, _ in person_data_list], domain)
                    logger.info(f"Enrichment returned {len(enriched_people)} contacts with emails (validated for {domain})")
                    logger.info(f"CREDIT USAGE: Used ~{len(enriched_people)} credits (enriched {len(enriched_people)} contacts)")
                    
                    # CRITICAL: Keep only contacts whose email domain matches this company (fix wrong contacts from Apollo)
                    # Keep contacts with no email; only drop when email is from another domain
                    before_email_filter = len(enriched_people)
                    def _keep_domain(p):
                        email = (p.get('email') or '').strip()
                        if not email:
                            return True
                        return self._email_domain_matches(email, domain)
                    enriched_people = [p for p in enriched_people if _keep_domain(p)]
                    if before_email_filter != len(enriched_people):
                        logger.info(f"Email-domain filter: kept {len(enriched_people)} contacts @ {domain} (removed {before_email_filter - len(enriched_people)} from other domains)")
                    
                    # CRITICAL: If enrichment returned fewer contacts than requested, log the waste
                    if len(enriched_people) < len(person_data_list):
                        wasted = len(person_data_list) - len(enriched_people)
                        logger.warning(f"{wasted} contacts were enriched but not returned (possible validation failure)")
                    
                    people.extend(enriched_people)
                    # region agent log
                    _agent_debug_log(
                        hypothesis_id="A",
                        location="apollo_client.py:search_people_api_search",
                        message="api_search_enriched",
                        data={
                            "domain": domain,
                            "titles": titles or [],
                            "filtered_person_count": len(persons),
                            "person_ids_count": len(person_data_list),
                            "enriched_count": len(enriched_people),
                        },
                    )
                    # endregion
                else:
                    logger.warning(f"No person IDs found after filtering - SKIPPING enrichment (saved credits!)")
                    logger.info(f"CREDIT USAGE: 0 credits (no person IDs to enrich)")
                    # region agent log
                    _agent_debug_log(
                        hypothesis_id="A",
                        location="apollo_client.py:search_people_api_search",
                        message="api_search_no_person_ids",
                        data={
                            "domain": domain,
                            "titles": titles or [],
                            "filtered_person_count": len(persons),
                        },
                    )
                    # endregion
                    # If no IDs and no filtered persons, return empty (don't waste credits)
                    if not persons:
                        return people
                    # If no IDs but we have persons, still return basic info (but don't enrich)
                    for person in persons:
                        person_data = {
                            'name': f"{person.get('first_name', '')} {person.get('last_name_obfuscated', '') or person.get('last_name', '')}".strip(),
                            'first_name': person.get('first_name', ''),
                            'last_name': person.get('last_name_obfuscated', '') or person.get('last_name', ''),
                            'email': '',  # No email (not enriched to save credits)
                            'phone': '',  # Phone numbers not requested - reveal in Apollo.io dashboard
                            'title': person.get('title', ''),
                            'linkedin_url': person.get('linkedin_url', ''),
                            'apollo_id': person.get('id', ''),
                            'source': 'apollo'
                        }
                        if person_data['name']:
                            people.append(person_data)
            else:
                logger.error(f"Apollo api_search failed: Status {response.status_code}")
                logger.error(f"Response: {response.text[:300]}")
                # region agent log
                _agent_debug_log(
                    hypothesis_id="C",
                    location="apollo_client.py:search_people_api_search",
                    message="api_search_http_error",
                    data={
                        "domain": domain,
                        "status": response.status_code,
                    },
                )
                # endregion
            
            time.sleep(0.5)  # Rate limiting
            
        except Exception as e:
            logger.error(f"Error in api_search for domain {domain}: {str(e)}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Response: {e.response.text[:200]}")
            logger.exception("api_search traceback")
        
        # Less restrictive filtering - keep more contacts
        # Only filter out obvious non-relevant titles
        blocked_titles = ['intern', 'student', 'volunteer', 'freelancer', 'contractor']
        filtered_people = []
        for person in people:
            title = (person.get('title') or '').lower()
            # Skip only if it's a clearly blocked title
            if any(blocked in title for blocked in blocked_titles):
                logger.warning(f"Filtered out: {person.get('name')} - Title: {person.get('title')} (blocked)")
                continue
            # Keep everyone else (we'll filter by email later if needed)
            filtered_people.append(person)
        
        logger.info(f"After filtering: {len(filtered_people)} contacts (from {len(people)})")
        return filtered_people

    def search_people_api_search_by_org_name(self, company_name: str, titles: List[str] = None, seniorities: List[str] = None, domain_for_filter: Optional[str] = None) -> List[Dict]:
        """
        FREE fallback for api_search: search by organization name instead of domain.
        Some companies return 0 people by domain but return people by org name.
        We keep Apollo-side filters OFF (no titles/seniorities) and filter locally.
        If domain_for_filter is provided, only keep enriched contacts whose email is @ that domain.
        """
        if not company_name:
            return []

        # Reuse the same defaults as domain-based api_search (used only for local filtering)
        if titles is None:
            titles = ['Founder', 'HR Director', 'HR Manager', 'CHRO', 'Director', 'HR', 'Manager', 'VP', 'Vice President', 'Head', 'Chief', 'Owner', 'CEO', 'CTO', 'CFO', 'COO']
        if seniorities is None:
            seniorities = ['owner', 'founder', 'c_suite', 'vp', 'head', 'director', 'manager', 'senior', 'lead']

        try:
            url = f"{self.api_search_base}/mixed_people/api_search"
            base_payload = {
                'q_organization_names': [company_name],
                'include_similar_titles': True,
                'page': 1,
                'per_page': getattr(Config, 'APOLLO_API_SEARCH_PER_PAGE', 100)
            }
            logger.debug(f"api_search org_name={company_name}")

            response = requests.post(url, json=base_payload, headers=self.headers, timeout=30)
            logger.debug(f"api_search(org_name) status: {response.status_code}")
            if response.status_code != 200:
                return []

            data = response.json() or {}
            persons = data.get('people', []) or []
            logger.debug(f"api_search(org_name) found {len(persons)} people")
            # CRITICAL: Keep only people whose organization actually matches this company (fix wrong data mix-up)
            before_org = len(persons)
            persons = [p for p in persons if self._person_org_matches_company_name(p, company_name)]
            if before_org != len(persons):
                logger.info(f"Org validation: kept {len(persons)} contacts that match company (removed {before_org - len(persons)} from other orgs)")

            # Apply the exact same local filtering + enrichment behavior as the domain-based function
            # by reusing its core logic with a minimal adaptation (we don't have a domain string here).
            people = []

            if titles:
                user_titles_lower = [t.lower().strip() for t in titles]
                excluded_titles = ['employee', 'staff', 'worker', 'member', 'personnel']
                filtered_persons = []
                for p in persons:
                    person_title = (p.get('title') or '').lower().strip()
                    # KEEP people with empty/missing titles (api_search free tier often omits titles)
                    if not person_title:
                        filtered_persons.append(p)
                        continue
                    if person_title in excluded_titles:
                        continue
                    matches = False
                    for user_title in user_titles_lower:
                        if user_title in person_title:
                            matches = True
                            break
                        if re.search(r'\b' + re.escape(user_title) + r'\b', person_title):
                            matches = True
                            break
                        if user_title == 'hr' and 'human resources' in person_title:
                            matches = True
                            break
                        if user_title == 'ceo' and 'chief executive' in person_title:
                            matches = True
                            break
                        if user_title == 'cto' and ('chief technology' in person_title or 'chief technical' in person_title):
                            matches = True
                            break
                        if user_title == 'cfo' and 'chief financial' in person_title:
                            matches = True
                            break
                        if user_title == 'coo' and 'chief operating' in person_title:
                            matches = True
                            break
                        if user_title == 'chro' and ('chief human resources' in person_title or 'chief hr' in person_title):
                            matches = True
                            break
                    if matches and person_title not in excluded_titles:
                        filtered_persons.append(p)

                original_count = len(persons)
                persons = filtered_persons
                if original_count != len(persons):
                    logger.info(f"FILTERED: {original_count} -> {len(persons)} contacts (saved {original_count - len(persons)} enrichment credits!)")

            if not persons:
                logger.warning(f"No contacts found after filtering - SKIPPING enrichment (saved credits!)")
                logger.info(f"CREDIT USAGE: 0 credits (no contacts to enrich)")
                return []

            person_ids = [p.get('id') for p in persons if p.get('id')]
            if not person_ids:
                logger.warning(f"No person IDs found after filtering - SKIPPING enrichment (saved credits!)")
                logger.info(f"CREDIT USAGE: 0 credits (no person IDs to enrich)")
                return []

            logger.info(f"Enriching {len(person_ids)} people to get emails in parallel...")
            logger.info(f"CREDIT USAGE: Will use ~{len(person_ids)} credits for enrichment")
            enriched_people = self.enrich_people_with_validation_parallel(person_ids, company_name)
            # If we have domain (e.g. from website), keep only contacts whose email is @ that domain
            # Keep contacts with no email; only drop when email is from another domain
            if domain_for_filter:
                before_f = len(enriched_people)
                def _keep_org(p):
                    email = (p.get('email') or '').strip()
                    if not email:
                        return True
                    return self._email_domain_matches(email, domain_for_filter)
                enriched_people = [p for p in enriched_people if _keep_org(p)]
                if before_f != len(enriched_people):
                    logger.info(f"Email-domain filter (org-name path): kept {len(enriched_people)} @ {domain_for_filter} (removed {before_f - len(enriched_people)} from other domains)")
            people.extend(enriched_people)

            # Apply the same post-filtering as domain-based function
            blocked_titles = ['intern', 'student', 'volunteer', 'freelancer', 'contractor']
            filtered_people = []
            for person in people:
                title = (person.get('title') or '').lower()
                if any(blocked in title for blocked in blocked_titles):
                    continue
                filtered_people.append(person)

            logger.info(f"After filtering: {len(filtered_people)} contacts (from {len(people)})")
            return filtered_people

        except Exception as e:
            logger.error(f"Error in api_search(org_name) for {company_name}: {str(e)}")
            logger.exception("api_search(org_name) traceback")

        return []
    
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
        max_enrich = getattr(Config, 'APOLLO_MAX_CONTACTS_TO_ENRICH', 100)
        logger.info(f"Enriching {len(person_ids)} people individually...")
        for idx, person_id in enumerate(person_ids[:max_enrich], 1):
            try:
                enriched_person = self.enrich_single_person(person_id)
                if enriched_person:
                    enriched.append(enriched_person)
                    logger.info(f"[{idx}/{min(len(person_ids), 20)}] Enriched: {enriched_person.get('name')} - {enriched_person.get('email')}")
                time.sleep(0.3)  # Rate limiting
            except Exception as e2:
                logger.error(f"Failed to enrich person {person_id}: {str(e2)}")
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
        
        max_enrich = getattr(Config, 'APOLLO_MAX_CONTACTS_TO_ENRICH', 100)
        logger.info(f"Enriching {len(person_ids)} people with company validation (target: {target_domain})...")
        for idx, person_id in enumerate(person_ids[:max_enrich], 1):
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
                            logger.info(f"[{idx}/{min(len(person_ids), 20)}] {enriched_person.get('name')} - {person_email} (VERIFIED)")
                        else:
                            # Still include if email exists (domain might be different but person works there)
                            enriched.append(enriched_person)
                            logger.info(f"[{idx}/{min(len(person_ids), 20)}] {enriched_person.get('name')} - {person_email} (domain mismatch but including)")
                    else:
                        # No email - still include (might have LinkedIn)
                        enriched.append(enriched_person)
                        logger.warning(f"[{idx}/{min(len(person_ids), 20)}] {enriched_person.get('name')} - No email but including")
                time.sleep(0.3)
            except Exception as e2:
                logger.error(f"Failed to enrich person {person_id}: {str(e2)}")
                continue
        
        return enriched
    
    def enrich_people_with_validation_parallel(self, person_ids: List[str], target_domain: str) -> List[Dict]:
        """
        Enrich people in PARALLEL with validation (get emails only)
        Phone numbers are NOT requested - reveal in Apollo.io dashboard to save credits
        Processes multiple contacts at once for faster results
        """
        enriched = []
        
        # CRITICAL: Don't enrich if no person IDs provided (saves credits!)
        if not person_ids or len(person_ids) == 0:
            logger.warning(f"No person IDs provided - SKIPPING enrichment (saved credits!)")
            # region agent log
            _agent_debug_log(
                hypothesis_id="A",
                location="apollo_client.py:enrich_people_with_validation_parallel",
                message="no_person_ids_provided",
                data={
                    "target_domain": target_domain,
                    "person_ids_count": 0,
                },
            )
            # endregion
            return enriched
        
        max_enrich = getattr(Config, 'APOLLO_MAX_CONTACTS_TO_ENRICH', 100)
        max_workers = getattr(Config, 'APOLLO_ENRICH_PARALLEL_WORKERS', 5)
        logger.info(f"Enriching {len(person_ids)} people in PARALLEL with company validation (target: {target_domain})...")
        
        import concurrent.futures
        
        def enrich_and_validate(person_id):
            """Enrich single person and validate - runs in parallel"""
            try:
                time.sleep(0.1)
                enriched_person = self.enrich_single_person(person_id)
                if not enriched_person:
                    return None
                
                person_email = enriched_person.get('email', '')
                
                # CRITICAL FIX: Include ALL contacts, even without emails!
                # Apollo already validated they work at the company, so trust Apollo
                # We want MORE contacts, not fewer!
                return enriched_person
            except Exception as e:
                logger.error(f"Error enriching person {person_id}: {str(e)}")
                return None
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_id = {executor.submit(enrich_and_validate, pid): pid for pid in person_ids[:max_enrich]}
            
            for future in concurrent.futures.as_completed(future_to_id):
                result = future.result()
                if result:
                    enriched.append(result)
        
        logger.info(f"Parallel enrichment completed: {len(enriched)} contacts with emails")
        logger.info(f"CREDIT USAGE: Enriched {len(enriched)} contacts (used ~{len(enriched)} credits)")
        
        # CRITICAL: Warn if we enriched but got fewer results (wasted credits)
        if len(enriched) < len(person_ids):
            wasted = len(person_ids) - len(enriched)
            logger.warning(f"{wasted} contacts were enriched but not returned (wasted ~{wasted} credits)")
        
        # region agent log
        _agent_debug_log(
            hypothesis_id="A",
            location="apollo_client.py:enrich_people_with_validation_parallel",
            message="parallel_enrichment_completed",
            data={
                "target_domain": target_domain,
                "person_ids_count": len(person_ids),
                "enriched_count": len(enriched),
            },
        )
        # endregion
        
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
                logger.warning(f"people/match request exception: {str(e)}")
                # region agent log
                _agent_debug_log(
                    hypothesis_id="E",
                    location="apollo_client.py:enrich_single_person",
                    message="people_match_network_exception",
                    data={
                        "person_id": person_id,
                        "error": str(e),
                    },
                )
                # endregion
            
            if response and response.status_code == 200:
                data = response.json()
                person = data.get('person', {})
                email_val = person.get('email', '')
                # region agent log
                _agent_debug_log(
                    hypothesis_id="E",
                    location="apollo_client.py:enrich_single_person",
                    message="people_match_success",
                    data={
                        "person_id": person_id,
                        "has_email": bool(email_val),
                    },
                )
                # endregion
                if person:
                    return {
                        'name': f"{person.get('first_name', '')} {person.get('last_name', '')}".strip(),
                        'first_name': person.get('first_name', ''),
                        'last_name': person.get('last_name', ''),
                        'email': email_val,
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
                
                # region agent log
                _agent_debug_log(
                    hypothesis_id="E",
                    location="apollo_client.py:enrich_single_person",
                    message="people_match_http_error",
                    data={
                        "person_id": person_id,
                        "status": error_status,
                    },
                )
                # endregion
                
                # Don't retry on authentication/authorization errors (waste credits)
                if error_status in (401, 403):
                    logger.error(f"Authentication/Authorization error (status {error_status}): {error_text}")
                    logger.warning(f"Check your Apollo.io API key - it may be invalid or expired")
                    return None
                
                # Don't retry on rate limit (429) - wait instead
                if error_status == 429:
                    logger.warning(f"Rate limit exceeded (429): {error_text}")
                    logger.warning(f"Apollo.io API rate limit reached - please wait before trying again")
                    return None
                
                # Don't retry on 404 (person not found)
                if error_status == 404:
                    logger.warning(f"Person not found (404): Person ID {person_id} doesn't exist")
                    return None
                
                # Only retry on network/timeout errors, not API errors
                if response:
                    logger.warning(f"people/match failed (status {error_status}): {error_text}")
                    logger.warning(f"Not retrying to avoid wasting credits - check API status")
                    return None
                else:
                    logger.warning(f"people/match failed: No response received (network error)")
                    # Only retry on network errors, not API errors
                    logger.warning(f"Retrying with GET method (network error only)...")
                
                # METHOD 2: Only retry on network errors, not API errors
                url2 = f"{self.base_url}/people/{person_id}"
                params = {'reveal_personal_emails': 'true'}  # Email only - no phone
                
                response2 = None
                try:
                    response2 = requests.get(url2, headers=self.headers, params=params, timeout=10)
                except Exception as e:
                    logger.warning(f"GET /people/{person_id} request exception: {str(e)}")
                    # region agent log
                    _agent_debug_log(
                        hypothesis_id="E",
                        location="apollo_client.py:enrich_single_person",
                        message="people_get_network_exception",
                        data={
                            "person_id": person_id,
                            "error": str(e),
                        },
                    )
                    # endregion
                    return None  # Network error - don't waste more credits
                
                if response2 and response2.status_code == 200:
                    person = response2.json().get('person', {})
                    email_val2 = person.get('email', '')
                    # region agent log
                    _agent_debug_log(
                        hypothesis_id="E",
                        location="apollo_client.py:enrich_single_person",
                        message="people_get_success",
                        data={
                            "person_id": person_id,
                            "has_email": bool(email_val2),
                        },
                    )
                    # endregion
                    if person:
                        return {
                            'name': f"{person.get('first_name', '')} {person.get('last_name', '')}".strip(),
                            'first_name': person.get('first_name', ''),
                            'last_name': person.get('last_name', ''),
                            'email': email_val2,
                            'phone': '',  # Phone numbers not requested - reveal in Apollo.io dashboard
                            'title': person.get('title', ''),
                            'linkedin_url': person.get('linkedin_url', ''),
                            'apollo_id': person_id,  # Include the person ID
                            'source': 'apollo'
                        }
                else:
                    error_status2 = response2.status_code if response2 else None
                    logger.error(f"GET /people/{person_id} also failed: {error_status2 if response2 else 'No response'}")
                    if response2:
                        logger.error(f"Response: {response2.text[:300]}")
                    return None  # Don't waste more credits
        except Exception as e:
            logger.error(f"Error enriching person {person_id}: {str(e)}")
            logger.exception("enrich_single_person traceback")
            # region agent log
            _agent_debug_log(
                hypothesis_id="E",
                location="apollo_client.py:enrich_single_person",
                message="enrich_single_person_exception",
                data={
                    "person_id": person_id,
                    "error": str(e),
                },
            )
            # endregion
        
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
                    'per_page': getattr(Config, 'APOLLO_MIXED_PEOPLE_SEARCH_PER_PAGE', 25)
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
                logger.error(f"Error searching without title filter: {str(e)}")
            return people
        
        for title in titles:
            try:
                url = f"{self.base_url}/mixed_people/search"
                base_payload = {
                    # API key removed from payload - now in header
                    'organization_domains': [domain],
                    'person_titles': [title],
                    'page': 1,
                    'per_page': getattr(Config, 'APOLLO_MIXED_PEOPLE_SEARCH_PER_TITLE_PER_PAGE', 5)
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
                logger.error(f"Error searching Apollo by domain for {title}: {str(e)}")
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
                    org_name = (org.get('name') or '').strip()
                    
                    # Validate that Apollo returned the RIGHT company (not google.com for "TCS")
                    if not self._person_org_matches_company_name({'organization': org}, company_name):
                        logger.warning(f"Apollo org search returned '{org_name}' for '{company_name}' - name mismatch, skipping to save credits")
                        org_domain = ''
                        org_id = None
                    
                    if org_domain:
                        domain = self.extract_domain(org_domain)
                        # Reject obviously wrong generic domains
                        generic_domains = {'google.com', 'facebook.com', 'linkedin.com', 'twitter.com', 'youtube.com', 'instagram.com', 'gmail.com', 'yahoo.com', 'outlook.com', 'microsoft.com', 'apple.com', 'amazon.com'}
                        if domain and domain in generic_domains:
                            logger.warning(f"Apollo returned generic domain '{domain}' for '{company_name}' - skipping to avoid wrong contacts")
                            domain = ''
                        if domain:
                            logger.info(f"Found domain {domain} for {company_name}, trying api_search...")
                            try:
                                people = self.search_people_api_search(domain, titles)
                                if people:
                                    logger.info(f"Found {len(people)} contacts via api_search for {company_name}")
                                    return people
                            except Exception as e:
                                logger.warning(f"api_search failed for {company_name}: {str(e)}, trying fallback...")
                            
                            # Fallback to old domain search
                            people = self.search_people_by_domain(domain, titles)
                            if people:
                                return people
                    
                    # If no domain or domain search failed, try searching by organization ID directly
                    if org_id and not people:
                        logger.info(f"No domain available, searching by organization ID: {org_id}")
                        try:
                            # Search people by organization ID
                            people_url = f"{self.base_url}/mixed_people/search"
                            people_payload = {
                                'organization_ids': [org_id],
                                'page': 1,
                                'per_page': getattr(Config, 'APOLLO_MIXED_PEOPLE_SEARCH_PER_PAGE', 25)
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
                                    logger.info(f"Found {len(people)} contacts via organization ID search")
                                    return people
                        except Exception as e:
                            logger.warning(f"Organization ID search failed: {str(e)}")
                    
                    if not people:
                        logger.warning(f"Organization {company_name} found in Apollo but has no website URL and organization ID search returned no results")
                else:
                    logger.warning(f"Organization {company_name} not found in Apollo database")
            else:
                logger.warning(f"Apollo organization search failed with status {org_response.status_code}")
            
            time.sleep(0.5)
        except Exception as e:
            logger.error(f"Error searching Apollo by company name: {str(e)}")
            logger.exception("search_people_by_company_name traceback")
        
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
        
        # If user provided titles, use ONLY those for local filtering.
        # If no titles provided, pass empty list so title filtering is SKIPPED entirely.
        # The api_search endpoint (free) often returns people WITHOUT the title field,
        # so filtering before enrichment removes everyone and shows 0 contacts.
        if titles:
            search_titles = titles
            search_seniorities = None
            logger.info(f"User provided titles - using ONLY: {titles[:5]}{'...' if len(titles) > 5 else ''}")
        else:
            search_titles = []
            search_seniorities = None
            logger.info(f"No user titles - skipping title filter to get ALL contacts")
        
        # Strategy 1: NEW api_search endpoint (FREE - no credits for search)
        if website:
            domain = self.extract_domain(website)
            if domain:
                logger.info(f"Trying NEW Apollo api_search (free) by domain: {domain}")
                try:
                    # Use user's titles if provided, otherwise use broad filters
                    people = self.search_people_api_search(domain, titles=search_titles, seniorities=search_seniorities)
                    if people:
                        apollo_count = len([p for p in people if p.get('source') == 'apollo'])
                        logger.info(f"Found {len(people)} contacts via NEW api_search ({apollo_count} from Apollo)")
                        # Now filter by user's designation if provided
                        if user_provided_titles:
                            filtered_people = self._filter_contacts_by_titles(people, user_provided_titles)
                            logger.info(f"Filtered to {len(filtered_people)} contacts matching user's designation: {', '.join(user_provided_titles)}")
                            # region agent log
                            _agent_debug_log(
                                hypothesis_id="B",
                                location="apollo_client.py:search_people_by_company",
                                message="api_search_returned_with_user_titles",
                                data={
                                    "company_name": company_name,
                                    "domain": domain,
                                    "website": website,
                                    "total_contacts": len(people),
                                    "filtered_contacts": len(filtered_people),
                                },
                            )
                            # endregion
                            return filtered_people
                        # region agent log
                        _agent_debug_log(
                            hypothesis_id="B",
                            location="apollo_client.py:search_people_by_company",
                            message="api_search_returned_no_user_titles",
                            data={
                                "company_name": company_name,
                                "domain": domain,
                                "website": website,
                                "total_contacts": len(people),
                            },
                        )
                        # endregion
                        return people
                    else:
                        logger.warning(f"NEW api_search found 0 contacts for {domain}")
                        # FREE fallback: try searching by org name when domain returns 0
                        if company_name:
                            logger.info(f"Trying NEW Apollo api_search (free) by org name: {company_name}")
                            people = self.search_people_api_search_by_org_name(company_name, titles=search_titles, seniorities=search_seniorities, domain_for_filter=domain)
                            if people:
                                apollo_count = len([p for p in people if p.get('source') == 'apollo'])
                                logger.info(f"Found {len(people)} contacts via NEW api_search(org_name) ({apollo_count} from Apollo)")
                                if user_provided_titles:
                                    filtered_people = self._filter_contacts_by_titles(people, user_provided_titles)
                                    logger.info(f"Filtered to {len(filtered_people)} contacts matching user's designation: {', '.join(user_provided_titles)}")
                                    # region agent log
                                    _agent_debug_log(
                                        hypothesis_id="B",
                                        location="apollo_client.py:search_people_by_company",
                                        message="api_search_org_name_returned_with_user_titles",
                                        data={
                                            "company_name": company_name,
                                            "website": website,
                                            "total_contacts": len(people),
                                            "filtered_contacts": len(filtered_people),
                                        },
                                    )
                                    # endregion
                                    return filtered_people
                                # region agent log
                                _agent_debug_log(
                                    hypothesis_id="B",
                                    location="apollo_client.py:search_people_by_company",
                                    message="api_search_org_name_returned_no_user_titles",
                                    data={
                                        "company_name": company_name,
                                        "website": website,
                                        "total_contacts": len(people),
                                    },
                                )
                                # endregion
                                return people
                except Exception as e:
                    logger.error(f"NEW api_search failed: {str(e)}, trying fallback...")
                    logger.exception("api_search fallback traceback")
        
        # Strategy 2: OLD search by domain (fallback - uses credits)
        if website and not people:
            domain = self.extract_domain(website)
            if domain:
                logger.info(f"Trying OLD Apollo search by domain: {domain}")
                # Use user's titles if provided, otherwise use None (will use default in function)
                people = self.search_people_by_domain(domain, titles=search_titles if titles else None)
                if people:
                    logger.info(f"Found {len(people)} contacts via OLD domain search")
                    # Filter by user's designation if provided
                    if user_provided_titles:
                        filtered_people = self._filter_contacts_by_titles(people, user_provided_titles)
                        logger.info(f"Filtered to {len(filtered_people)} contacts matching user's designation")
                        return filtered_people
                    return people
        
        # Strategy 3: Search by company name
        if company_name and not people:
            logger.info(f"Trying Apollo search by company name: {company_name}")
            # Use user's titles if provided, otherwise use None (will use default in function)
            people = self.search_people_by_company_name(company_name, titles=search_titles if titles else None)
            if people:
                logger.info(f"Found {len(people)} contacts via company name search")
                # Filter by user's designation if provided
                if user_provided_titles:
                    filtered_people = self._filter_contacts_by_titles(people, user_provided_titles)
                    logger.info(f"Filtered to {len(filtered_people)} contacts matching user's designation")
                    # region agent log
                    _agent_debug_log(
                        hypothesis_id="B",
                        location="apollo_client.py:search_people_by_company",
                        message="company_name_search_with_user_titles",
                        data={
                            "company_name": company_name,
                            "website": website,
                            "total_contacts": len(people),
                            "filtered_contacts": len(filtered_people),
                        },
                    )
                    # endregion
                    people = filtered_people
        
        # Web scraping fallback removed - using Apollo.io only
        
        # Add company info to all contacts
        for person in people:
            person['company_name'] = company_name
            person['company_website'] = website

        # CRITICAL: If we have company website, keep only contacts whose email is @ company domain
        # (fixes wrong contacts e.g. Bill Gates / Google employees shown for unrelated companies)
        # Keep contacts with no email; only drop when email is clearly from another domain
        if website and people:
            domain = self.extract_domain(website)
            if domain:
                before = len(people)
                people = [p for p in people if (not (p.get('email') or '').strip()) or self._email_domain_matches((p.get('email') or '').strip(), domain)]
                if before != len(people):
                    logger.info(f"Final email-domain filter: kept {len(people)} contacts @ {domain} (removed {before - len(people)} from other domains)")
        
        # VERY RELAXED filtering - only remove clearly irrelevant contacts
        # Keep ALL contacts with names, even if no title (titles might be missing in Apollo)
        blocked_titles = ['intern', 'student', 'volunteer', 'freelancer', 'contractor', 'trainee']
        
        filtered_people = []
        for person in people:
            # CRITICAL FIX: Don't skip contacts without titles - they might still be valid!
            # Only require a name
            if not person.get('name') and not person.get('first_name'):
                logger.warning(f"Skipping: No name found")
                continue
            
            title = (person.get('title') or '').lower().strip()
            
            # Only skip if title contains clearly blocked keywords (but keep if no title!)
            if title and any(blocked in title for blocked in blocked_titles):
                logger.error(f"FILTERED OUT: {person.get('name')} - '{title}' (blocked)")
                continue
            
            # Keep everyone else - we want MORE contacts, not fewer!
            # Note: User title filtering already happened above if user provided titles
            filtered_people.append(person)
        
        logger.info(f"FINAL: {len(filtered_people)} contacts after filtering (from {len(people)})")
        # region agent log
        _agent_debug_log(
            hypothesis_id="D",
            location="apollo_client.py:search_people_by_company",
            message="final_contacts_after_all_filters",
            data={
                "company_name": company_name,
                "website": website,
                "final_contacts": len(filtered_people),
                "initial_contacts": len(people),
            },
        )
        # endregion
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
            
            logger.info(f"[{idx}/{total_companies}] Enriching: {company_name}")
            
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
                logger.info(f"Found {len(people)} contacts ({apollo_count} from Apollo, {scraping_count} from web scraping)")
            else:
                logger.warning(f"No contacts found")
            
            enriched_companies.append(company)
            
            # Rate limiting
            time.sleep(1)
        
        return enriched_companies

    def search_sequences(self, q_name: Optional[str] = None, page: int = 1, per_page: int = 20) -> Dict:
        """
        Search for sequences (emailer campaigns) in Apollo.
        Requires a master API key.
        Returns list of sequences with id and name for dropdown / "Add batch to sequence".
        """
        url = f"{self.api_search_base}/emailer_campaigns/search"
        params = {"page": page, "per_page": per_page}
        if q_name and str(q_name).strip():
            params["q_name"] = str(q_name).strip()
        try:
            resp = requests.post(url, headers=self.headers, params=params, timeout=15)
            if resp.status_code == 401:
                logger.warning("Apollo Search Sequences: invalid credentials")
                return {"success": False, "error": "Invalid API key", "sequences": []}
            if resp.status_code == 403:
                data = resp.json() if resp.content else {}
                msg = data.get("error") or data.get("message") or "Access denied"
                logger.warning(f"Apollo Search Sequences: {msg}")
                return {"success": False, "error": msg, "sequences": []}
            if resp.status_code == 429:
                logger.warning("Apollo Search Sequences: rate limited")
                return {"success": False, "error": "Rate limit exceeded. Try again later.", "sequences": []}
            if resp.status_code != 200:
                logger.warning(f"Apollo Search Sequences: status {resp.status_code}")
                return {"success": False, "error": f"Apollo returned {resp.status_code}", "sequences": []}
            data = resp.json() if resp.content else {}
            campaigns = data.get("emailer_campaigns") or []
            pagination = data.get("pagination") or {}
            sequences = [{"id": c.get("id"), "name": c.get("name") or "Unnamed"} for c in campaigns if c.get("id")]
            logger.info(f"Apollo Search Sequences: found {len(sequences)} sequences")
            return {
                "success": True,
                "sequences": sequences,
                "pagination": {"page": pagination.get("page", 1), "per_page": pagination.get("per_page"), "total_entries": pagination.get("total_entries"), "total_pages": pagination.get("total_pages")},
            }
        except Exception as e:
            logger.exception("Apollo Search Sequences request failed")
            return {"success": False, "error": str(e), "sequences": []}

    def add_contacts_to_sequence(
        self,
        sequence_id: str,
        contact_ids: List[str],
        send_email_from_email_account_id: str,
        *,
        send_email_from_email_address: Optional[str] = None,
        sequence_no_email: bool = False,
        sequence_unverified_email: bool = False,
        sequence_active_in_other_campaigns: bool = False,
        sequence_finished_in_other_campaigns: bool = False,
        status: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Dict:
        """
        Add contacts to an Apollo sequence (emailer campaign).
        Requires master API key. contact_ids must be Apollo contact IDs (from Create Contact / Search Contacts).
        send_email_from_email_account_id is required (get from Get a List of Email Accounts).
        """
        if not sequence_id or not send_email_from_email_account_id:
            return {"success": False, "error": "sequence_id and send_email_from_email_account_id are required", "contacts": [], "skipped_contact_ids": {}}
        if not contact_ids:
            return {"success": False, "error": "contact_ids or label_names required", "contacts": [], "skipped_contact_ids": {}}
        url = f"{self.api_search_base}/emailer_campaigns/{sequence_id}/add_contact_ids"
        params: List[tuple] = [
            ("emailer_campaign_id", sequence_id),
            ("send_email_from_email_account_id", send_email_from_email_account_id),
        ]
        for cid in contact_ids:
            if cid:
                params.append(("contact_ids[]", cid))
        if send_email_from_email_address:
            params.append(("send_email_from_email_address", send_email_from_email_address))
        if sequence_no_email:
            params.append(("sequence_no_email", "true"))
        if sequence_unverified_email:
            params.append(("sequence_unverified_email", "true"))
        if sequence_active_in_other_campaigns:
            params.append(("sequence_active_in_other_campaigns", "true"))
        if sequence_finished_in_other_campaigns:
            params.append(("sequence_finished_in_other_campaigns", "true"))
        if status in ("active", "paused"):
            params.append(("status", status))
        if user_id:
            params.append(("user_id", user_id))
        try:
            resp = requests.post(url, headers=self.headers, params=params, timeout=30)
            if resp.status_code == 401:
                return {"success": False, "error": "Invalid API key", "contacts": [], "skipped_contact_ids": {}}
            if resp.status_code == 403:
                data = resp.json() if resp.content else {}
                msg = data.get("error") or data.get("message") or "Master API key required"
                return {"success": False, "error": msg, "contacts": [], "skipped_contact_ids": {}}
            if resp.status_code == 422:
                data = resp.json() if resp.content else {}
                msg = data.get("error") or "Validation error"
                return {"success": False, "error": msg, "contacts": [], "skipped_contact_ids": {}}
            if resp.status_code == 429:
                return {"success": False, "error": "Rate limit exceeded. Try again later.", "contacts": [], "skipped_contact_ids": {}}
            if resp.status_code != 200:
                return {"success": False, "error": f"Apollo returned {resp.status_code}", "contacts": [], "skipped_contact_ids": {}}
            data = resp.json() if resp.content else {}
            contacts = data.get("contacts") or []
            skipped = data.get("skipped_contact_ids") or {}
            logger.info(f"Apollo Add to Sequence: added {len(contacts)} contacts, skipped {len(skipped)}")
            return {
                "success": True,
                "contacts": contacts,
                "skipped_contact_ids": skipped,
                "emailer_campaign": data.get("emailer_campaign"),
            }
        except Exception as e:
            logger.exception("Apollo Add Contacts to Sequence request failed")
            return {"success": False, "error": str(e), "contacts": [], "skipped_contact_ids": {}}

    def update_contact_status_in_sequence(
        self,
        emailer_campaign_ids: List[str],
        contact_ids: List[str],
        mode: str,
    ) -> Dict:
        """
        Update contact status in a sequence: mark as finished, remove, or stop.
        mode: 'mark_as_finished' | 'remove' | 'stop'
        Requires master API key.
        """
        if not emailer_campaign_ids or not contact_ids:
            return {"success": False, "error": "emailer_campaign_ids and contact_ids are required", "contacts": []}
        mode = (mode or "").strip().lower()
        if mode not in ("mark_as_finished", "remove", "stop"):
            return {"success": False, "error": "mode must be one of: mark_as_finished, remove, stop", "contacts": []}
        url = f"{self.api_search_base}/emailer_campaigns/remove_or_stop_contact_ids"
        params: List[tuple] = [("mode", mode)]
        for sid in emailer_campaign_ids:
            if sid:
                params.append(("emailer_campaign_ids[]", sid))
        for cid in contact_ids:
            if cid:
                params.append(("contact_ids[]", cid))
        try:
            resp = requests.post(url, headers=self.headers, params=params, timeout=30)
            if resp.status_code == 401:
                return {"success": False, "error": "Invalid API key", "contacts": []}
            if resp.status_code == 403:
                data = resp.json() if resp.content else {}
                msg = data.get("error") or data.get("message") or "Master API key required"
                return {"success": False, "error": msg, "contacts": []}
            if resp.status_code == 429:
                return {"success": False, "error": "Rate limit exceeded. Try again later.", "contacts": []}
            if resp.status_code != 200:
                return {"success": False, "error": f"Apollo returned {resp.status_code}", "contacts": []}
            data = resp.json() if resp.content else {}
            contacts = data.get("contacts") or []
            logger.info(f"Apollo Update Contact Status: mode={mode}, updated {len(contacts)} contacts")
            return {
                "success": True,
                "contacts": contacts,
                "emailer_campaigns": data.get("emailer_campaigns", []),
                "num_contacts": data.get("num_contacts"),
                "contact_statuses": data.get("contact_statuses", {}),
            }
        except Exception as e:
            logger.exception("Apollo Update Contact Status in Sequence request failed")
            return {"success": False, "error": str(e), "contacts": []}

    def bulk_create_contacts(
        self,
        contacts: List[Dict],
        append_label_names: Optional[List[str]] = None,
        run_dedupe: bool = False,
    ) -> Dict:
        """
        Bulk create up to 100 contacts in Apollo. Returns created_contacts and existing_contacts (both with id).
        Each contact dict can have: first_name, last_name, email, title, organization_name, phone,
        linkedin_url, present_raw_address, account_id, organization_id, owner_id, etc.
        """
        if not contacts:
            return {"success": False, "error": "contacts array is required", "created_contacts": [], "existing_contacts": []}
        if len(contacts) > 100:
            return {"success": False, "error": "Maximum 100 contacts per request", "created_contacts": [], "existing_contacts": []}
        url = f"{self.api_search_base}/contacts/bulk_create"
        payload = {"contacts": contacts, "run_dedupe": run_dedupe}
        if append_label_names:
            payload["append_label_names"] = append_label_names
        try:
            resp = requests.post(url, headers=self.headers, json=payload, timeout=60)
            if resp.status_code == 401:
                return {"success": False, "error": "Invalid API key", "created_contacts": [], "existing_contacts": []}
            if resp.status_code == 403:
                data = resp.json() if resp.content else {}
                msg = data.get("message") or data.get("error") or "Access denied"
                return {"success": False, "error": msg, "created_contacts": [], "existing_contacts": []}
            if resp.status_code == 422:
                data = resp.json() if resp.content else {}
                msg = data.get("error") or "Validation error"
                return {"success": False, "error": msg, "created_contacts": [], "existing_contacts": []}
            if resp.status_code == 429:
                return {"success": False, "error": "Rate limit exceeded", "created_contacts": [], "existing_contacts": []}
            if resp.status_code not in (200, 201):
                return {"success": False, "error": f"Apollo returned {resp.status_code}", "created_contacts": [], "existing_contacts": []}
            data = resp.json() if resp.content else {}
            created = data.get("created_contacts") or []
            existing = data.get("existing_contacts") or []
            logger.info(f"Apollo Bulk Create: {len(created)} created, {len(existing)} existing")
            return {"success": True, "created_contacts": created, "existing_contacts": existing}
        except Exception as e:
            logger.exception("Apollo Bulk Create Contacts request failed")
            return {"success": False, "error": str(e), "created_contacts": [], "existing_contacts": []}

    def search_contacts(
        self,
        q_keywords: Optional[str] = None,
        page: int = 1,
        per_page: int = 25,
        sort_by_field: Optional[str] = None,
        sort_ascending: bool = False,
    ) -> Dict:
        """
        Search for contacts in Apollo (team's contacts). Use q_keywords for name, email, company, title.
        Returns contacts (each with id) and pagination.
        """
        url = f"{self.api_search_base}/contacts/search"
        payload = {"page": page, "per_page": min(per_page, 100)}
        if q_keywords and str(q_keywords).strip():
            payload["q_keywords"] = str(q_keywords).strip()
        if sort_by_field:
            payload["sort_by_field"] = sort_by_field
            payload["sort_ascending"] = sort_ascending
        try:
            resp = requests.post(url, headers=self.headers, json=payload, timeout=20)
            if resp.status_code == 401:
                return {"success": False, "error": "Invalid API key", "contacts": [], "pagination": {}}
            if resp.status_code == 403:
                data = resp.json() if resp.content else {}
                msg = data.get("message") or data.get("error") or "Access denied"
                return {"success": False, "error": msg, "contacts": [], "pagination": {}}
            if resp.status_code == 429:
                return {"success": False, "error": "Rate limit exceeded", "contacts": [], "pagination": {}}
            if resp.status_code != 200:
                return {"success": False, "error": f"Apollo returned {resp.status_code}", "contacts": [], "pagination": {}}
            data = resp.json() if resp.content else {}
            contacts = data.get("contacts") or []
            pagination = data.get("pagination") or {}
            logger.info(f"Apollo Search Contacts: {len(contacts)} results")
            return {"success": True, "contacts": contacts, "pagination": pagination}
        except Exception as e:
            logger.exception("Apollo Search Contacts request failed")
            return {"success": False, "error": str(e), "contacts": [], "pagination": {}}

    def get_email_accounts(self) -> Dict:
        """
        Get list of linked email accounts (for Add to Sequence send_email_from_email_account_id).
        Requires master API key. No parameters. Returns email_accounts with id, email, active, etc.
        """
        url = f"{self.api_search_base}/email_accounts"
        try:
            resp = requests.get(url, headers=self.headers, timeout=15)
            if resp.status_code == 401:
                return {"success": False, "error": "Invalid API key", "email_accounts": []}
            if resp.status_code == 403:
                data = resp.json() if resp.content else {}
                msg = data.get("error") or data.get("message") or "Master API key required"
                return {"success": False, "error": msg, "email_accounts": []}
            if resp.status_code == 429:
                return {"success": False, "error": "Rate limit exceeded", "email_accounts": []}
            if resp.status_code != 200:
                return {"success": False, "error": f"Apollo returned {resp.status_code}", "email_accounts": []}
            data = resp.json() if resp.content else {}
            accounts = data.get("email_accounts") or []
            logger.info(f"Apollo Get Email Accounts: {len(accounts)} accounts")
            return {"success": True, "email_accounts": accounts}
        except Exception as e:
            logger.exception("Apollo Get Email Accounts request failed")
            return {"success": False, "error": str(e), "email_accounts": []}

    def get_users(self, page: int = 1, per_page: int = 50) -> Dict:
        """
        Get list of users (teammates) in the Apollo account. Optional for Add to Sequence user_id.
        Requires master API key. GET /users/search with optional page, per_page.
        """
        url = f"{self.api_search_base}/users/search"
        params = {"page": page, "per_page": min(per_page, 100)}
        try:
            resp = requests.get(url, headers=self.headers, params=params, timeout=15)
            if resp.status_code == 401:
                return {"success": False, "error": "Invalid API key", "users": [], "pagination": {}}
            if resp.status_code == 403:
                data = resp.json() if resp.content else {}
                msg = data.get("error") or data.get("message") or "Master API key required"
                return {"success": False, "error": msg, "users": [], "pagination": {}}
            if resp.status_code == 429:
                return {"success": False, "error": "Rate limit exceeded", "users": [], "pagination": {}}
            if resp.status_code != 200:
                return {"success": False, "error": f"Apollo returned {resp.status_code}", "users": [], "pagination": {}}
            data = resp.json() if resp.content else {}
            users = data.get("users") or []
            pagination = data.get("pagination") or {}
            logger.info(f"Apollo Get Users: {len(users)} users")
            return {"success": True, "users": users, "pagination": pagination}
        except Exception as e:
            logger.exception("Apollo Get Users request failed")
            return {"success": False, "error": str(e), "users": [], "pagination": {}}
