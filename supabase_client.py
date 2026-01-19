"""
Supabase client for database operations
Replaces Google Sheets as the backend database
"""
from supabase import create_client, Client
from typing import List, Dict, Optional
from config import Config
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class SupabaseClient:
    def __init__(self):
        """Initialize Supabase client"""
        self.url = Config.SUPABASE_URL
        # Prefer service role key for backend operations (has full access)
        self.key = Config.SUPABASE_SERVICE_ROLE_KEY or Config.SUPABASE_ANON_KEY
        
        if not self.url:
            raise ValueError("SUPABASE_URL not configured. Please set it in config.py or environment variable.")
        
        if not self.key:
            raise ValueError("SUPABASE_SERVICE_ROLE_KEY or SUPABASE_ANON_KEY not configured. Please set it in config.py or environment variable.")
        
        try:
            self.client: Client = create_client(self.url, self.key)
            if Config.SUPABASE_SERVICE_ROLE_KEY:
                logger.info("✅ Supabase client initialized successfully (using SERVICE_ROLE key)")
            else:
                logger.warning("⚠️  Supabase client initialized with ANON key (limited permissions)")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Supabase client: {str(e)}")
            raise

        # Prefix used to mark user-saved Level 2 batches
        self.saved_batch_prefix = "SAVED::"
    
    def save_level1_results(self, companies: List[Dict], search_params: Dict) -> Dict:
        """
        Save Level 1 company search results to Supabase
        """
        try:
            project_name = search_params.get('project_name', '')
            pin_codes = search_params.get('pin_codes', '')
            industry = search_params.get('industry', '')
            timestamp = search_params.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            
            # Prepare data for insertion
            records = []
            for company in companies:
                record = {
                    'project_name': project_name,
                    'company_name': company.get('company_name', ''),
                    'website': company.get('website', ''),
                    'phone': company.get('phone', ''),
                    'address': company.get('address', ''),
                    'industry': industry,  # User's search industry
                    'place_type': company.get('place_type', ''),  # Google's detected category
                    'pin_code': company.get('pin_code', ''),
                    'pin_codes_searched': pin_codes,
                    'search_date': timestamp,
                    'place_id': company.get('place_id', ''),
                    'business_status': company.get('business_status', ''),
                    'selected_for_level2': False,
                    'created_at': datetime.now().isoformat()
                }
                records.append(record)
            
            # Insert into Supabase (table name: level1_companies)
            if not records:
                logger.warning(f"⚠️  No records to insert for project: {project_name}")
                return {'success': False, 'error': 'No companies to save', 'count': 0}
            
            logger.info(f"🔄 Inserting {len(records)} companies to Supabase for project: '{project_name}'")
            
            # Handle duplicates: Use upsert to update existing records or insert new ones
            # Process in batches to avoid timeout
            batch_size = 50
            total_saved = 0
            error_count = 0
            
            for i in range(0, len(records), batch_size):
                batch = records[i:i + batch_size]
                try:
                    # Use upsert with on_conflict to handle duplicates
                    # This will update existing records or insert new ones
                    response = (
                        self.client.table('level1_companies')
                        .upsert(batch, on_conflict='place_id', ignore_duplicates=False)
                        .execute()
                    )
                    
                    if response.data:
                        total_saved += len(response.data)
                        logger.info(f"✅ Processed batch {i//batch_size + 1}: {len(response.data)} companies")
                    else:
                        # If no data returned but no error, assume success
                        total_saved += len(batch)
                        
                except Exception as batch_error:
                    error_msg = str(batch_error)
                    logger.error(f"❌ Error in batch {i//batch_size + 1}: {error_msg}")
                    
                    # If upsert fails, try individual inserts/updates
                    if 'duplicate key' in error_msg.lower() or '23505' in error_msg:
                        logger.info(f"⚠️  Handling duplicates individually in batch {i//batch_size + 1}...")
                        for record in batch:
                            try:
                                place_id = record.get('place_id')
                                if not place_id:
                                    continue
                                    
                                # Check if exists
                                existing = (
                                    self.client.table('level1_companies')
                                    .select('id')
                                    .eq('place_id', place_id)
                                    .limit(1)
                                    .execute()
                                )
                                
                                if existing.data:
                                    # Update existing record with new project info
                                    (
                                        self.client.table('level1_companies')
                                        .update({
                                            'project_name': project_name,
                                            'industry': industry,
                                            'pin_codes_searched': pin_codes,
                                            'search_date': timestamp,
                                            'updated_at': datetime.now().isoformat()
                                        })
                                        .eq('place_id', place_id)
                                        .execute()
                                    )
                                    total_saved += 1
                                else:
                                    # Insert new record
                                    (
                                        self.client.table('level1_companies')
                                        .insert(record)
                                        .execute()
                                    )
                                    total_saved += 1
                            except Exception as single_error:
                                logger.error(f"❌ Error with individual record: {str(single_error)}")
                                error_count += 1
                    else:
                        error_count += len(batch)
            
            logger.info(f"✅ Saved {total_saved} companies to Supabase for project: '{project_name}' (Errors: {error_count})")
            
            # Verify the save by checking if project exists and count matches
            try:
                verify_response = self.client.table('level1_companies').select('id', count='exact').eq('project_name', project_name).execute()
                actual_count = verify_response.count if hasattr(verify_response, 'count') else len(verify_response.data) if verify_response.data else 0
                
                if actual_count > 0:
                    logger.info(f"✅ Verified: Project '{project_name}' exists in database with {actual_count} companies")
                else:
                    logger.error(f"❌ CRITICAL: Project '{project_name}' NOT found in database after save attempt!")
                    return {'success': False, 'error': f'Companies were not saved to database. Saved count: {total_saved}, Actual count: {actual_count}', 'count': 0}
                
                # If we saved companies but database shows 0, that's a failure
                if total_saved > 0 and actual_count == 0:
                    logger.error(f"❌ CRITICAL: Save reported success but database is empty for project '{project_name}'")
                    return {'success': False, 'error': 'Companies were not saved to database', 'count': 0}
                    
            except Exception as verify_error:
                logger.error(f"❌ Error verifying save: {str(verify_error)}")
                # Don't fail if verification fails, but log it
            
            # Only return success if we actually saved something
            if total_saved == 0 and error_count > 0:
                return {'success': False, 'error': f'Failed to save any companies. {error_count} errors occurred.', 'count': 0}
            
            return {'success': True, 'count': total_saved, 'errors': error_count}
            
        except Exception as e:
            logger.error(f"❌ Error saving Level 1 results to Supabase: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def get_level1_companies(
        self,
        project_name: Optional[str] = None,
        selected_only: bool = False,
        limit: int = 50
    ) -> List[Dict]:
        """
        Get companies from Level 1
        """
        try:
            query = self.client.table('level1_companies').select('*')
            
            # Filter by project_name if provided
            if project_name:
                query = query.eq('project_name', project_name)
            
            # Filter by selected_for_level2 if needed
            if selected_only:
                query = query.eq('selected_for_level2', True)
            
            # Order by search_date descending (newest first)
            query = query.order('search_date', desc=True)
            
            # Limit results
            query = query.limit(limit)
            
            response = query.execute()
            companies = response.data if response.data else []
            
            logger.info(f"✅ Retrieved {len(companies)} companies from Supabase (project_name={project_name}, selected_only={selected_only})")
            return companies
            
        except Exception as e:
            logger.error(f"❌ Error retrieving Level 1 companies from Supabase: {str(e)}")
            return []
    
    def mark_companies_selected(self, companies: List[Dict], project_name: Optional[str] = None) -> Dict:
        """
        Mark companies as selected for Level 2 processing
        """
        try:
            if not companies:
                return {'success': False, 'error': 'No companies provided'}
            
            # Extract place_ids from companies
            place_ids = [c.get('place_id') or c.get('company_name') for c in companies if c.get('place_id') or c.get('company_name')]
            
            if not place_ids:
                return {'success': False, 'error': 'No valid company identifiers found'}
            
            # Update selected_for_level2 to True for matching companies
            # Filter by project_name if provided
            query = self.client.table('level1_companies')
            
            if project_name:
                query = query.eq('project_name', project_name)
            
            # Update all matching place_ids
            updated_count = 0
            for place_id in place_ids:
                try:
                    response = query.eq('place_id', place_id).update({'selected_for_level2': True}).execute()
                    if response.data:
                        updated_count += len(response.data)
                except Exception as e:
                    logger.warning(f"⚠️  Could not update company {place_id}: {str(e)}")
                    continue
            
            logger.info(f"✅ Marked {updated_count} companies as selected for Level 2")
            return {'success': True, 'count': updated_count}
            
        except Exception as e:
            logger.error(f"❌ Error marking companies as selected: {str(e)}")
            return {'success': False, 'error': str(e)}

    def set_level2_selection(self, project_name: str, selected_place_ids: List[str], limit: int = 50) -> Dict:
        """
        Persist Level 2 selection for a project:
        - Set selected_for_level2 = False for all companies in the project (up to limit)
        - Set selected_for_level2 = True for selected_place_ids
        """
        try:
            if not project_name:
                return {'success': False, 'error': 'project_name is required'}
            if not isinstance(selected_place_ids, list):
                return {'success': False, 'error': 'selected_place_ids must be a list'}

            # First, unset all selections for this project (bounded by limit)
            # Note: PostgREST update affects all matching rows; limit applies to select, not update.
            self.client.table('level1_companies').update({'selected_for_level2': False}).eq('project_name', project_name).execute()

            if not selected_place_ids:
                return {'success': True, 'count': 0}

            # Set selected_for_level2 = True for the selected ids
            # Prefer place_id matching; fallback to company_name if a value doesn't look like place_id.
            place_ids: List[str] = []
            company_names: List[str] = []
            for pid in selected_place_ids:
                if not pid:
                    continue
                s = str(pid).strip()
                if s.startswith('ChIJ') and (' ' not in s):
                    place_ids.append(s)
                else:
                    company_names.append(s)

            updated = 0
            if place_ids:
                resp = (
                    self.client.table('level1_companies')
                    .update({'selected_for_level2': True})
                    .eq('project_name', project_name)
                    .in_('place_id', place_ids)
                    .execute()
                )
                if resp.data:
                    updated += len(resp.data)

            if company_names:
                resp = (
                    self.client.table('level1_companies')
                    .update({'selected_for_level2': True})
                    .eq('project_name', project_name)
                    .in_('company_name', company_names)
                    .execute()
                )
                if resp.data:
                    updated += len(resp.data)

            logger.info(f"✅ Saved Level 2 selection for project {project_name}: {updated} selected")
            return {'success': True, 'count': updated}

        except Exception as e:
            logger.error(f"❌ Error setting Level 2 selection: {str(e)}")
            return {'success': False, 'error': str(e)}

    def update_level1_company_metrics(
        self,
        project_name: str,
        place_id: str,
        total_employees: Optional[str] = None,
        active_members: Optional[int] = None,
        active_members_with_email: Optional[int] = None,
    ) -> Dict:
        """
        Best-effort update for company metrics on level1_companies.
        NOTE: If columns don't exist in Supabase yet, this will fail gracefully (we don't break Level 2).
        """
        try:
            if not project_name or not place_id:
                return {'success': False, 'error': 'project_name and place_id are required'}

            payload: Dict = {}
            if total_employees is not None:
                payload['total_employees'] = total_employees
            if active_members is not None:
                payload['active_members'] = int(active_members)
            if active_members_with_email is not None:
                payload['active_members_with_email'] = int(active_members_with_email)

            if not payload:
                return {'success': True, 'updated': 0}

            resp = (
                self.client.table('level1_companies')
                .update(payload)
                .eq('project_name', project_name)
                .eq('place_id', place_id)
                .execute()
            )

            updated = len(resp.data) if resp.data else 0
            return {'success': True, 'updated': updated}

        except Exception as e:
            # Don't fail Level 2 if schema doesn't have these columns yet
            logger.warning(f"⚠️  Could not update company metrics (likely missing columns): {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def get_projects_list(self) -> List[Dict]:
        """
        Get list of all unique project names (for history/resume feature)
        Returns projects with name, date, industry, pin_codes, and company_count
        """
        try:
            # Get all distinct project names with their data
            response = self.client.table('level1_companies').select('project_name, search_date, industry, pin_codes_searched, created_at').execute()
            
            if not response.data:
                logger.info("ℹ️  No projects found in level1_companies table")
                return []
            
            logger.info(f"ℹ️  Found {len(response.data)} company records in Supabase")
            
            # Get unique projects with latest search_date, company count, and other details
            projects_map = {}
            for record in response.data:
                project_name = record.get('project_name', '').strip()
                if not project_name:
                    continue
                    
                search_date = record.get('search_date', '') or record.get('created_at', '')
                industry = record.get('industry', '')
                pin_codes = record.get('pin_codes_searched', '')
                
                if project_name not in projects_map:
                    projects_map[project_name] = {
                        'search_date': search_date,
                        'industry': industry,
                        'pin_codes': pin_codes,
                        'company_count': 1
                    }
                else:
                    # Increment company count
                    projects_map[project_name]['company_count'] += 1
                    # Update metadata if this record is newer
                    if search_date and (not projects_map[project_name].get('search_date') or search_date > projects_map[project_name].get('search_date', '')):
                        projects_map[project_name]['search_date'] = search_date
                        if industry:
                            projects_map[project_name]['industry'] = industry
                        if pin_codes:
                            projects_map[project_name]['pin_codes'] = pin_codes
            
            # Convert to list of dicts
            projects = [{
                'project_name': name,
                'search_date': data.get('search_date', ''),
                'industry': data.get('industry', ''),
                'pin_codes': data.get('pin_codes', ''),
                'company_count': data.get('company_count', 0)
            } for name, data in projects_map.items()]
            
            # Sort by search_date descending (newest first), or by created_at if search_date is missing
            projects.sort(key=lambda x: x.get('search_date', '') or '1970-01-01', reverse=True)
            
            logger.info(f"✅ Returning {len(projects)} unique projects: {[p.get('project_name') for p in projects]}")
            return projects
            
        except Exception as e:
            logger.error(f"❌ Error getting projects list: {str(e)}")
            import traceback
            traceback.print_exc()
            return []

    def delete_level1_companies(self, project_name: str, identifiers: List[str]) -> Dict:
        """
        Delete Level 1 companies from Supabase by identifiers.
        Identifiers may be Google place_id (preferred) or company_name (fallback).
        """
        try:
            if not project_name:
                return {'success': False, 'error': 'project_name is required'}
            if not identifiers:
                return {'success': False, 'error': 'No identifiers provided'}

            # Split identifiers into likely place_ids vs company_names
            place_ids: List[str] = []
            company_names: List[str] = []
            for ident in identifiers:
                if not ident:
                    continue
                s = str(ident).strip()
                # Heuristic: Google place_id often starts with "ChIJ" and has no spaces
                if s.startswith('ChIJ') and (' ' not in s):
                    place_ids.append(s)
                else:
                    company_names.append(s)

            deleted = 0

            if place_ids:
                resp = (
                    self.client.table('level1_companies')
                    .delete()
                    .eq('project_name', project_name)
                    .in_('place_id', place_ids)
                    .execute()
                )
                if resp.data:
                    deleted += len(resp.data)

            if company_names:
                resp = (
                    self.client.table('level1_companies')
                    .delete()
                    .eq('project_name', project_name)
                    .in_('company_name', company_names)
                    .execute()
                )
                if resp.data:
                    deleted += len(resp.data)

            logger.info(f"✅ Deleted {deleted} companies from Supabase (project={project_name})")
            return {'success': True, 'deleted': deleted}

        except Exception as e:
            logger.error(f"❌ Error deleting Level 1 companies: {str(e)}")
            return {'success': False, 'error': str(e)}

    def delete_project(self, project_name: str) -> Dict:
        """
        Delete a whole project from Supabase (Level 1 companies + Level 2 contacts).
        """
        try:
            if not project_name:
                return {'success': False, 'error': 'project_name is required'}

            deleted_level1 = 0
            deleted_level2 = 0

            resp1 = self.client.table('level1_companies').delete().eq('project_name', project_name).execute()
            if resp1.data:
                deleted_level1 = len(resp1.data)

            resp2 = self.client.table('level2_contacts').delete().eq('project_name', project_name).execute()
            if resp2.data:
                deleted_level2 = len(resp2.data)

            logger.info(f"✅ Deleted project {project_name}: level1={deleted_level1}, level2={deleted_level2}")
            return {'success': True, 'deleted_level1': deleted_level1, 'deleted_level2': deleted_level2}

        except Exception as e:
            logger.error(f"❌ Error deleting project: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def delete_batch(self, batch_name: str) -> Dict:
        """
        Delete a batch and all its contacts from Supabase.
        """
        try:
            if not batch_name:
                return {'success': False, 'error': 'batch_name is required'}

            # Delete all contacts for this batch
            resp = self.client.table('level2_contacts').delete().eq('batch_name', batch_name).execute()
            deleted_count = len(resp.data) if resp.data else 0

            logger.info(f"✅ Deleted batch {batch_name}: {deleted_count} contacts removed")
            return {'success': True, 'deleted_contacts': deleted_count}

        except Exception as e:
            logger.error(f"❌ Error deleting batch: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def save_level2_results(self, enriched_companies: List[Dict], project_name: Optional[str] = None, batch_name: Optional[str] = None) -> Dict:
        """
        Save Level 2 enriched contact data to Supabase
        Args:
            enriched_companies: List of companies with contact data
            project_name: Name of the project (from Level 1)
            batch_name: User-defined batch name (e.g., "Mumbai IT Batch 1")
        """
        try:
            if not enriched_companies:
                return {'success': False, 'error': 'No enriched companies provided'}
            
            # Generate default batch_name if not provided - use consistent name to prevent duplicates
            if not batch_name:
                batch_name = f"{project_name}_Main_Batch"
            
            records = []
            for company in enriched_companies:
                people = company.get('people', [])
                company_name = company.get('company_name', '')
                company_address = company.get('address', '')
                company_website = company.get('website', '')
                company_phone = company.get('phone', '')
                pin_code = company.get('pin_code', '')
                industry = company.get('industry', '')
                
                # If project_name not provided, try to get from first company's data
                if not project_name:
                    # Try to get from Supabase by company name
                    existing = self.get_level1_companies(limit=1)
                    if existing:
                        project_name = existing[0].get('project_name', '')
                
                # Create a record for each contact
                for person in people:
                    contact_type = 'Employee'
                    title = person.get('title', '').lower() if person.get('title') else ''
                    
                    if any(kw in title for kw in ['founder', 'owner', 'ceo', 'co-founder']):
                        contact_type = 'Founder/Owner'
                    elif any(kw in title for kw in ['hr', 'human resources', 'recruiter', 'talent']):
                        contact_type = 'HR'
                    
                    record = {
                        'project_name': project_name or 'Unknown',
                        'batch_name': batch_name,
                        'company_name': company_name,
                        'company_address': company_address,
                        'company_website': company_website,
                        'company_phone': company_phone,
                        'company_total_employees': company.get('total_employees', '') or company.get('num_employees', ''),
                        'contact_name': person.get('name', ''),
                        'title': person.get('title', ''),  # Original job title from Apollo.io
                        'contact_type': contact_type,
                        'phone_number': person.get('phone', '') or person.get('phone_number', ''),
                        'linkedin_url': person.get('linkedin_url', '') or person.get('linkedin', ''),
                        'email': person.get('email', ''),
                        'pin_code': pin_code,
                        'industry': industry,
                        'search_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'source': person.get('source', 'apollo')
                    }
                    records.append(record)
            
            if records:
                # Insert into Supabase
                response = self.client.table('level2_contacts').insert(records).execute()
                logger.info(f"✅ Saved {len(records)} contacts to Supabase for Level 2")
                return {'success': True, 'count': len(records)}
            else:
                return {'success': True, 'count': 0, 'message': 'No contacts to save'}
            
        except Exception as e:
            logger.error(f"❌ Error saving Level 2 results to Supabase: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def update_batch_name(self, project_name: str, batch_name: str) -> Dict:
        """
        Update batch_name for all contacts in a project (for most recent processing)
        Args:
            project_name: Project name to update
            batch_name: New batch name to set
        """
        try:
            if not project_name or not batch_name:
                return {'success': False, 'error': 'project_name and batch_name are required'}

            # Mark this as a user-saved batch
            if not batch_name.startswith(self.saved_batch_prefix):
                batch_name = f"{self.saved_batch_prefix}{batch_name}"
            
            # Update all contacts for this project that don't have a batch_name yet
            # OR update the most recently created contacts (within last hour)
            from datetime import datetime, timedelta
            one_hour_ago = (datetime.now() - timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')
            
            response = (
                self.client.table('level2_contacts')
                .update({'batch_name': batch_name})
                .eq('project_name', project_name)
                .gte('created_at', one_hour_ago)  # Only update recent contacts
                .execute()
            )
            
            updated_count = len(response.data) if response.data else 0
            logger.info(f"✅ Updated {updated_count} contacts with batch_name: {batch_name}")
            
            return {'success': True, 'count': updated_count}
            
        except Exception as e:
            logger.error(f"❌ Error updating batch_name in Supabase: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def merge_duplicate_batches(self, project_name: str, target_batch_name: str) -> Dict:
        """
        Merge all batches for a project into a single batch (removes duplicates).
        """
        try:
            if not project_name:
                return {'success': False, 'error': 'project_name is required'}
            
            # Get all contacts for this project
            all_contacts = self.get_contacts_for_level3(project_name=project_name)
            
            if not all_contacts:
                return {'success': False, 'error': 'No contacts found for this project'}
            
            # Update all contacts to use the target batch name
            contact_ids = [c.get('id') for c in all_contacts if c.get('id')]
            
            if not contact_ids:
                return {'success': False, 'error': 'No valid contact IDs found'}
            
            # Update in chunks to avoid query size limits
            updated = 0
            chunk_size = 100
            for i in range(0, len(contact_ids), chunk_size):
                chunk = contact_ids[i:i + chunk_size]
                resp = (
                    self.client.table('level2_contacts')
                    .update({'batch_name': target_batch_name})
                    .in_('id', chunk)
                    .execute()
                )
                if resp.data:
                    updated += len(resp.data)
            
            logger.info(f"✅ Merged {updated} contacts into batch: {target_batch_name}")
            return {'success': True, 'merged_contacts': updated, 'batch_name': target_batch_name}
            
        except Exception as e:
            logger.error(f"❌ Error merging batches: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def get_batches_list(self, project_name: Optional[str] = None) -> List[Dict]:
        """
        Get list of all batches (with metadata) for Level 3.
        Automatically merges duplicate timestamp-based batches into Main_Batch.
        Returns list of dicts with batch_name, project_name, contact_count, created_at
        """
        try:
            query = self.client.table('level2_contacts').select('batch_name, project_name, created_at')
            
            if project_name:
                query = query.eq('project_name', project_name)
            
            response = query.execute()
            contacts = response.data if response.data else []
            
            # Group by batch_name and identify duplicates
            batches_dict = {}
            projects_to_merge = {}
            
            for contact in contacts:
                batch_name = contact.get('batch_name', '')
                if not batch_name:
                    continue
                
                proj_name = contact.get('project_name', '')
                
                # Remove saved batch prefix for display
                display_name = batch_name
                if batch_name.startswith(self.saved_batch_prefix):
                    display_name = batch_name[len(self.saved_batch_prefix):]
                
                # Detect timestamp-based duplicate batches (old format: Project_Batch_YYYYMMDD_HHMMSS)
                if proj_name and '_Batch_' in batch_name and batch_name.count('_') >= 3:
                    # Check if it matches timestamp pattern
                    parts = batch_name.split('_Batch_')
                    if len(parts) == 2 and len(parts[1]) >= 15:  # Timestamp format
                        if proj_name not in projects_to_merge:
                            projects_to_merge[proj_name] = []
                        if batch_name not in projects_to_merge[proj_name]:
                            projects_to_merge[proj_name].append(batch_name)
                
                if batch_name not in batches_dict:
                    batches_dict[batch_name] = {
                        'batch_name': display_name,
                        'project_name': proj_name,
                        'contact_count': 0,
                        'created_at': contact.get('created_at', '')
                    }
                batches_dict[batch_name]['contact_count'] += 1

            # Auto-merge duplicate batches silently
            for proj_name, duplicate_batches in projects_to_merge.items():
                if len(duplicate_batches) > 1:
                    main_batch_name = f"{proj_name}_Main_Batch"
                    logger.info(f"🔄 Auto-merging {len(duplicate_batches)} duplicate batches for project: {proj_name}")
                    
                    # Merge all duplicates into main batch
                    for dup_batch in duplicate_batches:
                        try:
                            resp = (
                                self.client.table('level2_contacts')
                                .update({'batch_name': main_batch_name})
                                .eq('project_name', proj_name)
                                .eq('batch_name', dup_batch)
                                .execute()
                            )
                            if resp.data:
                                logger.info(f"  ✅ Auto-merged {len(resp.data)} contacts from {dup_batch} to {main_batch_name}")
                        except Exception as e:
                            logger.warning(f"  ⚠️  Could not auto-merge batch {dup_batch}: {str(e)}")
            
            # Re-fetch after merging to get accurate counts
            if projects_to_merge:
                response = query.execute()
                contacts = response.data if response.data else []
                batches_dict = {}
                for contact in contacts:
                    batch_name = contact.get('batch_name', '')
                    if not batch_name:
                        continue
                    display_name = batch_name
                    if batch_name.startswith(self.saved_batch_prefix):
                        display_name = batch_name[len(self.saved_batch_prefix):]
                    if batch_name not in batches_dict:
                        batches_dict[batch_name] = {
                            'batch_name': display_name,
                            'project_name': contact.get('project_name', ''),
                            'contact_count': 0,
                            'created_at': contact.get('created_at', '')
                        }
                    batches_dict[batch_name]['contact_count'] += 1
            
            batches = list(batches_dict.values())
            batches.sort(key=lambda x: x.get('created_at', ''), reverse=True)
            
            logger.info(f"✅ Retrieved {len(batches)} batches from Supabase (auto-merged duplicates)")
            return batches
            
        except Exception as e:
            logger.error(f"❌ Error retrieving batches: {str(e)}")
            return []
    
    def get_contacts_for_level3(self, project_name: Optional[str] = None, batch_name: Optional[str] = None) -> List[Dict]:
        """
        Get contacts from Level 2 for Level 3 transfer to Apollo.io
        Args:
            project_name: Filter by project name (optional)
            batch_name: Filter by batch name (recommended for Level 3)
        """
        try:
            query = self.client.table('level2_contacts').select('*')
            
            # Filter by batch_name (preferred) or project_name
            if batch_name:
                # Try exact batch_name first (legacy)
                exact_query = query.eq('batch_name', batch_name)
                response = exact_query.execute()
                contacts = response.data if response.data else []
                if not contacts:
                    # Try saved batch prefix
                    prefixed_name = batch_name
                    if not batch_name.startswith(self.saved_batch_prefix):
                        prefixed_name = f"{self.saved_batch_prefix}{batch_name}"
                    query = self.client.table('level2_contacts').select('*').eq('batch_name', prefixed_name)
                else:
                    query = None
            elif project_name:
                query = query.eq('project_name', project_name)
            
            # Only include contacts with email or phone
            if query is not None:
                response = query.execute()
                contacts = response.data if response.data else []
            
            # Filter to only include contacts with email or phone
            filtered_contacts = [
                c for c in contacts 
                if c.get('email') or c.get('phone_number')
            ]
            
            logger.info(f"✅ Retrieved {len(filtered_contacts)} contacts from Supabase for Level 3")
            return filtered_contacts
            
        except Exception as e:
            logger.error(f"❌ Error retrieving contacts for Level 3: {str(e)}")
            return []

    def get_level2_contacts_by_ids(self, contact_ids: List[int]) -> List[Dict]:
        """Fetch Level 2 contacts by IDs"""
        try:
            if not contact_ids:
                return []
            resp = (
                self.client.table('level2_contacts')
                .select('*')
                .in_('id', contact_ids)
                .execute()
            )
            return resp.data if resp.data else []
        except Exception as e:
            logger.error(f"❌ Error fetching contacts by IDs: {str(e)}")
            return []
    
    def save_progress(self, session_key: str, progress_data: Dict) -> Dict:
        """
        Save or update progress tracking for a session
        Args:
            session_key: Unique identifier for the operation (e.g., project_name)
            progress_data: Dict with keys: stage, message, current, total, companies_found, status, error_message
        """
        try:
            progress_data['session_key'] = session_key
            progress_data['updated_at'] = datetime.now().isoformat()
            
            # Check if progress exists
            existing = (
                self.client.table('progress_tracking')
                .select('id')
                .eq('session_key', session_key)
                .execute()
            )
            
            if existing.data:
                # Update existing
                resp = (
                    self.client.table('progress_tracking')
                    .update(progress_data)
                    .eq('session_key', session_key)
                    .execute()
                )
            else:
                # Insert new
                progress_data['created_at'] = datetime.now().isoformat()
                resp = (
                    self.client.table('progress_tracking')
                    .insert(progress_data)
                    .execute()
                )
            
            return {'success': True, 'data': resp.data[0] if resp.data else None}
        except Exception as e:
            logger.error(f"❌ Error saving progress: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def get_progress(self, session_key: str) -> Optional[Dict]:
        """
        Get current progress for a session
        """
        try:
            resp = (
                self.client.table('progress_tracking')
                .select('*')
                .eq('session_key', session_key)
                .execute()
            )
            return resp.data[0] if resp.data else None
        except Exception as e:
            logger.error(f"❌ Error getting progress: {str(e)}")
            return None
    
    def delete_progress(self, session_key: str) -> Dict:
        """
        Delete progress tracking for a session (cleanup after completion)
        """
        try:
            resp = (
                self.client.table('progress_tracking')
                .delete()
                .eq('session_key', session_key)
                .execute()
            )
            return {'success': True, 'deleted': len(resp.data) if resp.data else 0}
        except Exception as e:
            logger.error(f"❌ Error deleting progress: {str(e)}")
            return {'success': False, 'error': str(e)}

