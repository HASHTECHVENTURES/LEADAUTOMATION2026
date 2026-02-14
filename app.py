from flask import Flask, render_template, request, jsonify, Response, stream_with_context, session, redirect, url_for
from functools import wraps
from google_places_client import GooglePlacesClient
from apollo_client import ApolloClient
from supabase_client import SupabaseClient
from config import Config
import json
import time
import threading
from datetime import datetime
import os
import logging
import requests

# Setup logger
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

app = Flask(__name__, static_folder='static', static_url_path='/static')
app.config.from_object(Config)
app.secret_key = Config.SECRET_KEY

# Production settings for Vercel/serverless
app.config['SESSION_COOKIE_SECURE'] = os.getenv('FLASK_ENV') == 'production'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = 86400  # 24 hours

# Initialize clients
google_client = GooglePlacesClient()
apollo_client = ApolloClient()

# Initialize Supabase client (ONLY database - Google Sheets removed)
# Initialize lazily to avoid Vercel cold start issues
supabase_client = None

def get_supabase_client():
    """Lazy initialization of Supabase client"""
    global supabase_client
    if supabase_client is None:
        try:
            supabase_client = SupabaseClient()
            print("✅ Using Supabase as backend database")
        except Exception as e:
            print(f"❌ Supabase client not initialized: {str(e)}")
            print("❌ Please check your Supabase configuration in config.py")
            print("❌ Make sure SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are set")
            print("❌ Also ensure you've run the SQL schema in Supabase (see supabase_schema.sql)")
            raise  # Re-raise for actual usage
    return supabase_client

def filter_companies_by_employee_range(companies, employee_ranges):
    """
    Filter companies by employee range(s).
    employee_ranges: List of ranges like ["50-100", "100-250"] or single string for backward compatibility
    """
    # Ensure employee_ranges is always a list to prevent "'int' object is not iterable" error
    try:
        if employee_ranges is None:
            employee_ranges = []
        elif isinstance(employee_ranges, (int, float)):
            # If it's a number, treat as no filter (empty list)
            employee_ranges = []
        elif isinstance(employee_ranges, str):
            # Handle backward compatibility (single string)
            employee_ranges = [employee_ranges] if employee_ranges and employee_ranges.lower() != 'all' else []
        elif isinstance(employee_ranges, tuple):
            # Convert tuple to list
            employee_ranges = list(employee_ranges)
        elif not isinstance(employee_ranges, list):
            # If it's any other type that's not a list, convert to empty list
            employee_ranges = []
    except Exception as e:
        # If anything goes wrong during validation, default to empty list (no filter)
        print(f"⚠️  Error validating employee_ranges: {e}, defaulting to no filter")
        employee_ranges = []
    
    if not employee_ranges or len(employee_ranges) == 0:
        return companies
    
    filtered = []
    
    for company in companies:
        total_employees_str = company.get('total_employees', '') or ''
        if not total_employees_str:
            # If company doesn't have employee count, skip it when filtering
            continue
        
        # Try to extract numeric value from employee string (e.g., "50-100" -> 75, "500+" -> 500)
        employee_count = None
        try:
            # Clean the string first
            cleaned = total_employees_str.strip().replace(',', '').replace(' ', '')
            
            # Validate: reject if contains non-numeric characters (except - and +)
            if not cleaned or not all(c.isdigit() or c in ['-', '+'] for c in cleaned):
                continue
            
            # Handle ranges like "50-100" -> take midpoint
            if '-' in cleaned:
                parts = cleaned.split('-')
                if len(parts) == 2:
                    low = int(parts[0])
                    high = int(parts[1])
                    # Validate range is reasonable
                    if low > 0 and high > low and high <= 1000000:
                        employee_count = (low + high) // 2
            # Handle "500+" or "5000+"
            elif '+' in cleaned:
                num = int(cleaned.replace('+', ''))
                # Validate number is reasonable
                if num > 0 and num <= 1000000:
                    employee_count = num
            # Handle single number
            else:
                num = int(cleaned)
                # Validate number is reasonable
                if num > 0 and num <= 1000000:
                    employee_count = num
        except (ValueError, AttributeError):
            # If we can't parse, skip this company when filtering
            continue
        
        if employee_count is None:
            continue
        
        # Check if company matches ANY of the selected ranges
        matches = False
        # Extra safety: ensure employee_ranges is iterable before looping
        try:
            iter(employee_ranges)
        except TypeError:
            # If not iterable, skip this company (safety fallback)
            continue
        
        for employee_range in employee_ranges:
            if employee_range == "1-10":
                matches = 1 <= employee_count <= 10
            elif employee_range == "10-50":
                matches = 10 <= employee_count <= 50
            elif employee_range == "50-100":
                matches = 50 <= employee_count <= 100
            elif employee_range == "100-250":
                matches = 100 <= employee_count <= 250
            elif employee_range == "250-500":
                matches = 250 <= employee_count <= 500
            elif employee_range == "500-1000":
                matches = 500 <= employee_count <= 1000
            elif employee_range == "1000-5000":
                matches = 1000 <= employee_count <= 5000
            elif employee_range == "5000+":
                matches = employee_count >= 5000
            
            if matches:
                break  # Company matches at least one range, no need to check others
        
        if matches:
            filtered.append(company)
    
    return filtered

# Try to initialize on startup (but don't crash the app if it fails)
try:
    supabase_client = SupabaseClient()
    print("✅ Using Supabase as backend database")
except Exception as e:
    print(f"⚠️  Supabase client initialization deferred: {str(e)}")
    # Will be initialized on first use via get_supabase_client()

# Progress tracking is now handled by Supabase (see get_supabase_client().py)
# This keeps progress persistent across serverless invocations

# Indian states list
INDIAN_STATES = [
    'Andhra Pradesh', 'Arunachal Pradesh', 'Assam', 'Bihar', 'Chhattisgarh',
    'Goa', 'Gujarat', 'Haryana', 'Himachal Pradesh', 'Jharkhand',
    'Karnataka', 'Kerala', 'Madhya Pradesh', 'Maharashtra', 'Manipur',
    'Meghalaya', 'Mizoram', 'Nagaland', 'Odisha', 'Punjab',
    'Rajasthan', 'Sikkim', 'Tamil Nadu', 'Telangana', 'Tripura',
    'Uttar Pradesh', 'Uttarakhand', 'West Bengal',
    'Andaman and Nicobar Islands', 'Chandigarh', 'Dadra and Nagar Haveli',
    'Daman and Diu', 'Delhi', 'Jammu and Kashmir', 'Ladakh', 'Lakshadweep', 'Puducherry'
]

# Authentication decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session or not session['logged_in']:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Login route
@app.route('/login')
def login():
    """Login page"""
    if session.get('logged_in'):
        return redirect(url_for('index'))
    return render_template('login.html')

# Login API endpoint
@app.route('/api/login', methods=['POST'])
def api_login():
    """Handle login authentication"""
    try:
        data = request.json
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        # Check credentials
        if username == Config.LOGIN_USERNAME and password == Config.LOGIN_PASSWORD:
            session.permanent = True
            session['logged_in'] = True
            session['username'] = username
            return jsonify({'success': True, 'message': 'Login successful'}), 200
        else:
            return jsonify({'success': False, 'error': 'Invalid username or password'}), 401
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# Logout route
@app.route('/logout')
def logout():
    """Handle logout"""
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    """Main page - shows navigation to 3 levels"""
    return render_template('index.html', states=INDIAN_STATES)

@app.route('/level1')
@login_required
def level1():
    """Level 1: Company Search (Location Search)"""
    # Cache-bust static assets so browser always loads latest JS/CSS after updates
    try:
        js_path = os.path.join(app.root_path, 'static', 'js', 'main.js')
        css_path = os.path.join(app.root_path, 'static', 'css', 'style.css')
        static_version = str(int(max(os.path.getmtime(js_path), os.path.getmtime(css_path))))
    except Exception:
        static_version = str(int(time.time()))

    return render_template('level1.html', static_version=static_version)

@app.route('/level2')
@login_required
def level2():
    """Level 2: Contact Enrichment (Contact Database)"""
    return render_template('level2.html')

@app.route('/level3')
@login_required
def level3():
    """Level 3: Transfer to Outreach Platform"""
    return render_template('level3.html')

@app.route('/api/level1/search', methods=['POST'])
def level1_search():
    """Level 1: Search companies using location search, save to database"""
    try:
        data = request.json
        project_name = data.get('project_name', '').strip()
        pin_codes_input = data.get('pin_code', '').strip()
        industry = data.get('industry', '').strip()
        
        # Validate project name
        if not project_name:
            return jsonify({'error': 'Project name is required'}), 400
        
        # Validate project name format (alphanumeric, spaces, hyphens, underscores)
        if not all(c.isalnum() or c in (' ', '-', '_') for c in project_name):
            return jsonify({'error': 'Project name can only contain letters, numbers, spaces, hyphens, and underscores'}), 400
        
        if len(project_name) < 3:
            return jsonify({'error': 'Project name must be at least 3 characters'}), 400
        
        if len(project_name) > 100:
            return jsonify({'error': 'Project name must be less than 100 characters'}), 400
        
        # Parse multiple PIN codes (comma-separated)
        # Parse and auto-complete PIN codes
        all_pins = [p.strip() for p in pin_codes_input.split(',') if p.strip()]
        
        # Separate into valid (6 digits), incomplete (numeric but < 6 digits), and invalid
        valid_pins = []
        incomplete_pins = []
        invalid_pins = []
        
        for pin in all_pins:
            if pin.isdigit() and len(pin) == 6:
                valid_pins.append(pin)
            elif pin.isdigit() and len(pin) < 6:
                incomplete_pins.append(pin)
            else:
                invalid_pins.append(pin)
        
        # Auto-complete incomplete PIN codes using prefix from first valid PIN
        if valid_pins and incomplete_pins:
            first_valid = valid_pins[0]
            for incomplete in incomplete_pins:
                digits_needed = 6 - len(incomplete)
                if digits_needed > 0:
                    prefix = first_valid[:digits_needed]
                    completed = prefix + incomplete.zfill(len(incomplete))
                    if len(completed) == 6 and completed.isdigit():
                        valid_pins.append(completed)
                        print(f"✅ Auto-completed '{incomplete}' to '{completed}' using prefix from '{first_valid}'")
        
        pin_codes = valid_pins
        
        # Safely get max_companies with error handling
        try:
            max_companies = int(data.get('max_companies', 20))
        except (ValueError, TypeError):
            max_companies = 20  # Default to 20 if conversion fails
        
        if not pin_codes:
            error_msg = 'No valid PIN codes found. '
            if incomplete_pins:
                error_msg += f'Incomplete: {", ".join(incomplete_pins)} (need at least one full 6-digit PIN to auto-complete). '
            if invalid_pins:
                error_msg += f'Invalid: {", ".join(invalid_pins)}. '
            error_msg += 'Please enter at least one valid 6-digit PIN code.'
            return jsonify({'error': error_msg}), 400
        
        # Validate max_companies (limit to reasonable range)
        if max_companies < 1 or max_companies > 100:
            max_companies = 20  # Default to 20 if invalid
        
        print(f"🔍 Search request: PINs={pin_codes}, Industry={industry}, MaxCompanies={max_companies}")
        
        def generate():
            try:
                # Use project_name as the session identifier
                session_key = project_name
                
                # Initialize progress in Supabase
                initial_progress = {
                    'stage': 'searching_places',
                    'message': 'Searching locations...',
                    'current': 0,
                    'total': 0,
                    'companies_found': 0,
                    'status': 'in_progress'
                }
                try:
                    get_supabase_client().save_progress(session_key, initial_progress)
                except Exception as e:
                    print(f"⚠️  Could not save progress to Supabase: {str(e)}")
                
                yield f"data: {json.dumps({'type': 'progress', 'data': initial_progress})}\n\n"
                
                # Step 1: Search locations for all PIN codes
                all_companies = []
                total_pin_codes = len(pin_codes)
                # Request more companies per PIN to account for duplicates (request 1.5x to ensure we get enough unique results)
                companies_per_pin = max(1, int((max_companies * 1.5) // total_pin_codes))  # Request extra to account for duplicates
                search_errors = []  # Track errors for better user feedback
                
                for idx, pin_code in enumerate(pin_codes, 1):
                    # Progress for PIN-level search (so the UI doesn't look "stuck")
                    yield f"data: {json.dumps({'type': 'progress', 'data': {'stage': 'searching_places', 'message': f'Searching PIN {idx}/{total_pin_codes}: {pin_code}...', 'current': idx, 'total': total_pin_codes, 'companies_found': len(all_companies)}})}\n\n"
                    
                    print(f"🔍 Calling location search API: PIN={pin_code} ({idx}/{total_pin_codes}), Industry={industry}, MaxResults={companies_per_pin}")
                    
                    # Search locations for this PIN code
                    try:
                        print(f"🔍 [DEBUG] About to call search_by_pin_and_industry for PIN {pin_code}")
                        logger.info(f"🔍 [DEBUG] Calling Google Places API for PIN {pin_code}, Industry: {industry}")
                        
                        companies = google_client.search_by_pin_and_industry(
                            pin_code=pin_code,
                            industry=industry,
                            max_results=companies_per_pin
                        )
                        
                        print(f"🔍 [DEBUG] search_by_pin_and_industry returned {len(companies)} companies for PIN {pin_code}")
                        logger.info(f"🔍 [DEBUG] Google Places API returned {len(companies)} companies for PIN {pin_code}")
                        
                        # Add PIN code to each company for tracking
                        for company in companies:
                            company['pin_code'] = pin_code
                        
                        all_companies.extend(companies)
                        print(f"✅ Found {len(companies)} companies for PIN {pin_code}")
                        logger.info(f"✅ Successfully found {len(companies)} companies for PIN {pin_code}")

                        # Emit a progress update after each PIN finishes so "Companies Found" updates live
                        yield f"data: {json.dumps({'type': 'progress', 'data': {'stage': 'searching_places', 'message': f'Finished PIN {idx}/{total_pin_codes}: {pin_code}. Found {len(companies)} companies (Total: {len(all_companies)}).', 'current': idx, 'total': total_pin_codes, 'companies_found': len(all_companies)}})}\n\n"
                        
                    except Exception as e:
                        error_msg = str(e)
                        print(f"❌ Error searching PIN {pin_code}: {error_msg}")
                        logger.error(f"❌ Error searching PIN {pin_code}: {error_msg}")
                        # Log full traceback for debugging
                        import traceback
                        logger.error(f"Traceback: {traceback.format_exc()}")
                        # Track error for user feedback
                        if 'OVER_QUERY_LIMIT' in error_msg or 'quota' in error_msg.lower():
                            search_errors.append(f"PIN {pin_code}: API quota exceeded")
                        elif 'network' in error_msg.lower() or 'connection' in error_msg.lower():
                            search_errors.append(f"PIN {pin_code}: Network error")
                        else:
                            search_errors.append(f"PIN {pin_code}: {error_msg[:50]}")
                        # Continue to next PIN code but track errors
                        continue
                
                # Deduplicate companies by place_id (Google's unique identifier)
                # This prevents the same company from appearing multiple times when searching multiple PIN codes
                seen_place_ids = set()
                deduplicated_companies = []
                for company in all_companies:
                    place_id = company.get('place_id')
                    if place_id and place_id not in seen_place_ids:
                        seen_place_ids.add(place_id)
                        deduplicated_companies.append(company)
                    elif not place_id:
                        # If no place_id, use company_name + address as fallback identifier
                        company_key = f"{company.get('company_name', '')}_{company.get('address', '')}"
                        if company_key not in seen_place_ids:
                            seen_place_ids.add(company_key)
                            deduplicated_companies.append(company)
                
                print(f"🔍 Deduplication: {len(all_companies)} companies → {len(deduplicated_companies)} unique companies")
                logger.info(f"🔍 Deduplication: {len(all_companies)} companies → {len(deduplicated_companies)} unique companies")
                
                # Show all unique companies up to max_companies limit
                # This ensures users see all unique results, not cut off due to duplicates
                companies = deduplicated_companies[:max_companies]  # Limit to max_companies total
                companies_count = len(companies) if companies else 0
                
                # Log if we have more unique companies than the limit
                if len(deduplicated_companies) > max_companies:
                    print(f"⚠️  Found {len(deduplicated_companies)} unique companies, but limiting to {max_companies} as requested")
                    logger.info(f"⚠️  Found {len(deduplicated_companies)} unique companies, but limiting to {max_companies} as requested")
                print(f"✅ Location search returned {companies_count} companies total from {total_pin_codes} PIN code(s)")
                logger.info(f"✅ Location search completed: {companies_count} companies found for project '{project_name}'")
                
                if not companies or companies_count == 0:
                    pin_codes_str = ', '.join(pin_codes)
                    
                    # Provide better error message based on what happened
                    if search_errors:
                        error_details = '; '.join(search_errors)
                        error_msg = f'No companies found for PIN code(s): {pin_codes_str}. Errors: {error_details}. This may be due to API quota limits or network issues. Please try again in a few minutes or check your Google Places API quota.'
                    else:
                        error_msg = f'No companies found for PIN code(s): {pin_codes_str}. Please try different PIN codes or check if they are correct. You may also want to try a broader industry term.'
                    
                    print(f"⚠️  {error_msg}")
                    logger.warning(f"⚠️  No companies found for project '{project_name}' with PIN codes: {pin_codes_str}. Errors: {search_errors}")
                    yield f"data: {json.dumps({'type': 'complete', 'data': {'companies': [], 'message': error_msg, 'total_companies': 0, 'errors': search_errors}})}\n\n"
                    return
                
                # Log company details for debugging
                logger.info(f"📋 Companies to save: {companies_count}")
                if companies:
                    logger.info(f"📋 First company sample: {companies[0].get('company_name', 'Unknown')} (place_id: {companies[0].get('place_id', 'None')})")
                
                # Update progress in Supabase
                saving_progress = {
                    'stage': 'saving',
                    'message': f'Found {len(companies)} companies. Saving to database...',
                    'current': 0,
                    'total': len(companies),
                    'companies_found': len(companies),
                    'status': 'in_progress'
                }
                try:
                    get_supabase_client().save_progress(session_key, saving_progress)
                except Exception as e:
                    print(f"⚠️  Could not save progress to Supabase: {str(e)}")
                yield f"data: {json.dumps({'type': 'progress', 'data': saving_progress})}\n\n"
                
                # Save to Supabase database
                try:
                    search_params = {
                        'project_name': project_name,  # User-defined project name
                        'pin_codes': ','.join(pin_codes),  # Store all PIN codes as comma-separated
                        'industry': industry,
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }
                    
                    logger.info(f"💾 Starting save operation for project '{project_name}' with {len(companies)} companies")
                    save_result = get_supabase_client().save_level1_results(companies, search_params)
                    
                    logger.info(f"💾 Save result: {save_result}")
                    
                    if save_result.get('success'):
                        saved_count = save_result.get('count', 0)
                        print(f"✅ Saved {saved_count} companies to Supabase for project: '{project_name}'")
                        logger.info(f"✅ Saved {saved_count} companies to Supabase for project: '{project_name}'")
                        
                        # Double-check: if count is 0, that's a problem
                        if saved_count == 0:
                            error_msg = f"No companies were saved to database for project '{project_name}'. Save result: {save_result}"
                            print(f"❌ {error_msg}")
                            logger.error(f"❌ {error_msg}")
                            
                            # Try to verify what's in the database
                            try:
                                verify = get_supabase_client().client.table('level1_companies').select('id', count='exact').eq('project_name', project_name).execute()
                                db_count = verify.count if hasattr(verify, 'count') else (len(verify.data) if verify.data else 0)
                                logger.error(f"❌ Database verification: Found {db_count} companies for project '{project_name}'")
                            except Exception as verify_err:
                                logger.error(f"❌ Could not verify database: {verify_err}")
                            
                            raise Exception(error_msg)
                    else:
                        error_msg = save_result.get('error', 'Unknown error')
                        print(f"❌ Error saving to Supabase: {error_msg}")
                        logger.error(f"❌ Error saving to Supabase for project '{project_name}': {error_msg}")
                        logger.error(f"❌ Full save_result: {save_result}")
                        raise Exception(f"Failed to save to Supabase: {error_msg}")
                except Exception as e:
                    error_msg = str(e)
                    print(f"❌ Error saving to Supabase: {error_msg}")
                    logger.error(f"❌ CRITICAL: Save failed during search: {error_msg}")
                    import traceback
                    traceback.print_exc()
                    
                    # Send error to frontend so user knows save failed
                    yield f"data: {json.dumps({'type': 'error', 'data': {'error': f'Failed to save companies to database: {error_msg}. Companies were found but could not be saved.'}})}\n\n"
                    
                    # Still send companies so user can see them, but mark as not saved
                    yield f"data: {json.dumps({'type': 'complete', 'data': {'companies': companies, 'message': f'Found {len(companies)} companies but SAVE FAILED: {error_msg}. Please try saving again.', 'total_companies': len(companies), 'save_failed': True}})}\n\n"
                    return
                
                # Send incremental company updates
                try:
                    for idx, company in enumerate(companies, 1):
                        # Update progress in Supabase periodically (every 5 companies to reduce DB calls)
                        if idx % 5 == 0 or idx == len(companies):
                            try:
                                update_progress = {
                                    'current': idx,
                                    'message': f'Processed {company.get("company_name", "")}... ({idx}/{len(companies)})',
                                    'status': 'in_progress'
                                }
                                get_supabase_client().save_progress(session_key, update_progress)
                            except Exception as progress_err:
                                # Don't fail if progress update fails
                                logger.warning(f"⚠️  Could not update progress: {progress_err}")
                        
                        try:
                            yield f"data: {json.dumps({'type': 'company_update', 'data': company, 'progress': {'current': idx, 'total': len(companies), 'companies_found': len(companies)}})}\n\n"
                        except (BrokenPipeError, ConnectionResetError, GeneratorExit):
                            # Client disconnected
                            return
                except (BrokenPipeError, ConnectionResetError, GeneratorExit):
                    # Client disconnected during company updates
                    return
                
                # Final result - mark as completed in Supabase
                completed_progress = {
                    'stage': 'completed',
                    'message': f'Found {len(companies)} companies and saved to database.',
                    'current': len(companies),
                    'total': len(companies),
                    'companies_found': len(companies),
                    'status': 'completed'
                }
                
                # Verify save was successful before marking as completed
                try:
                    verify = get_supabase_client().client.table('level1_companies').select('id', count='exact').eq('project_name', project_name).execute()
                    actual_count = verify.count if hasattr(verify, 'count') else (len(verify.data) if verify.data else 0)
                    if actual_count == 0:
                        logger.error(f"❌ CRITICAL: Save reported success but database is empty for '{project_name}'")
                        yield f"data: {json.dumps({'type': 'error', 'data': {'error': 'Companies were not saved to database. Please try saving again.'}})}\n\n"
                        yield f"data: {json.dumps({'type': 'complete', 'data': {'companies': companies, 'message': f'Found {len(companies)} companies but SAVE FAILED. Please click Save button to retry.', 'total_companies': len(companies), 'save_failed': True}})}\n\n"
                        return
                except Exception as verify_err:
                    logger.warning(f"⚠️  Could not verify save: {verify_err}")
                get_supabase_client().save_progress(session_key, completed_progress)
                
                result = {
                    'companies': companies,
                    'total_companies': len(companies),
                    'message': f'Found {len(companies)} companies and saved to database. Proceed to Level 2 for contact enrichment.'
                }
                
                yield f"data: {json.dumps({'type': 'complete', 'data': result})}\n\n"
                
            except (BrokenPipeError, ConnectionResetError, GeneratorExit):
                # Client closed the connection (common with streaming responses). Not an app error.
                print(f"ℹ️  Client disconnected during streaming for project: {project_name}")
                return
            except Exception as e:
                error_msg = str(e)
                logger.error(f"❌ Error in Level 1 search stream: {error_msg}")
                import traceback
                traceback.print_exc()
                
                # Clean error message - remove Python internals
                clean_error = error_msg
                if 'logger' in clean_error.lower() or 'NameError' in clean_error:
                    clean_error = "An internal error occurred. Please try again or contact support."
                if 'Traceback' in clean_error or 'File "' in clean_error:
                    clean_error = "An error occurred during processing. Please try again."
                
                try:
                    yield f"data: {json.dumps({'type': 'error', 'data': {'error': clean_error}})}\n\n"
                    # Send a final complete message to close the stream
                    yield f"data: {json.dumps({'type': 'complete', 'data': {'companies': [], 'message': clean_error, 'total_companies': 0, 'save_failed': True}})}\n\n"
                except (BrokenPipeError, ConnectionResetError, GeneratorExit):
                    return
                except Exception as send_err:
                    logger.error(f"❌ Could not send error to client: {send_err}")
                    return
            finally:
                # Always ensure stream is properly closed
                try:
                    # Send a final message to ensure stream completes
                    # This prevents ERR_INCOMPLETE_CHUNKED_ENCODING
                    pass
                except:
                    pass
                # Clean up progress from Supabase after a delay (keep for 1 hour for recovery)
                # For immediate cleanup, uncomment the line below:
                # get_supabase_client().delete_progress(session_key)
        
        # Wrap generator to ensure it always completes
        def safe_generate():
            try:
                for chunk in generate():
                    yield chunk
            except (BrokenPipeError, ConnectionResetError, GeneratorExit):
                # Client disconnected - this is normal
                pass
            except Exception as e:
                logger.error(f"❌ Generator error: {e}")
                # Send final error message
                try:
                    yield f"data: {json.dumps({'type': 'error', 'data': {'error': 'An error occurred during streaming'}})}\n\n"
                except:
                    pass
        
        return Response(stream_with_context(safe_generate()), mimetype='text/event-stream', headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'  # Disable buffering for nginx
        })
        
    except Exception as e:
        print(f"Error in search: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/search/sync', methods=['POST'])
def search_sync():
    """Legacy synchronous endpoint (kept for compatibility)"""
    try:
        data = request.json
        pin_codes_input = data.get('pin_code', '').strip()
        industry = data.get('industry', '').strip()
        
        # Parse multiple PIN codes (comma-separated) and auto-complete incomplete ones
        all_pins = [p.strip() for p in pin_codes_input.split(',') if p.strip()]
        
        # Separate into valid (6 digits), incomplete (numeric but < 6 digits), and invalid
        valid_pins = []
        incomplete_pins = []
        invalid_pins = []
        
        for pin in all_pins:
            if pin.isdigit() and len(pin) == 6:
                valid_pins.append(pin)
            elif pin.isdigit() and len(pin) < 6:
                incomplete_pins.append(pin)
            else:
                invalid_pins.append(pin)
        
        # Auto-complete incomplete PIN codes using prefix from first valid PIN
        if valid_pins and incomplete_pins:
            first_valid = valid_pins[0]
            for incomplete in incomplete_pins:
                # Calculate how many digits we need from the prefix
                digits_needed = 6 - len(incomplete)
                if digits_needed > 0 and digits_needed <= 6:
                    prefix = first_valid[:digits_needed]
                    completed = prefix + incomplete
                    if len(completed) == 6 and completed.isdigit():
                        valid_pins.append(completed)
                        print(f"✅ Auto-completed '{incomplete}' to '{completed}' using prefix from '{first_valid}'")
        
        # Final list of PIN codes to use
        pin_codes = valid_pins
        
        if not pin_codes:
            error_msg = 'No valid PIN codes found. '
            if incomplete_pins:
                error_msg += f'Incomplete: {", ".join(incomplete_pins)} (need at least one full 6-digit PIN to auto-complete). '
            if invalid_pins:
                error_msg += f'Invalid: {", ".join(invalid_pins)}. '
            error_msg += 'Please enter at least one valid 6-digit PIN code.'
            return jsonify({'error': error_msg}), 400
        
        # Search all PIN codes
        all_companies = []
        # Request more companies per PIN to account for duplicates (request 1.5x to ensure we get enough unique results)
        max_companies_sync = 20
        companies_per_pin = max(1, int((max_companies_sync * 1.5) // len(pin_codes)))  # Request extra to account for duplicates
        
        for pin_code in pin_codes:
            companies = google_client.search_by_pin_and_industry(
                pin_code=pin_code,
                industry=industry,
                max_results=companies_per_pin
            )
            all_companies.extend(companies)
        
        # Deduplicate companies by place_id (Google's unique identifier)
        # This prevents the same company from appearing multiple times when searching multiple PIN codes
        seen_place_ids = set()
        deduplicated_companies = []
        for company in all_companies:
            place_id = company.get('place_id')
            if place_id and place_id not in seen_place_ids:
                seen_place_ids.add(place_id)
                deduplicated_companies.append(company)
            elif not place_id:
                # If no place_id, use company_name + address as fallback identifier
                company_key = f"{company.get('company_name', '')}_{company.get('address', '')}"
                if company_key not in seen_place_ids:
                    seen_place_ids.add(company_key)
                    deduplicated_companies.append(company)
        
        print(f"🔍 Deduplication: {len(all_companies)} companies → {len(deduplicated_companies)} unique companies")
        
        companies = deduplicated_companies[:20]  # Limit to 20 total
        
        if not companies:
            return jsonify({
                'companies': [],
                'message': 'No companies found for the given location'
            }), 200
        
        enriched_companies = apollo_client.enrich_company_data(companies)
        
        result = {
            'companies': enriched_companies,
            'total_companies': len(enriched_companies),
            'total_contacts': sum(len(c.get('people', [])) for c in enriched_companies)
        }
        
        return jsonify(result), 200
        
    except Exception as e:
        print(f"Error in search: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/level2/process', methods=['POST'])
def level2_process():
    """Level 2: Process companies from Supabase with contact database to get contacts"""
    try:
        data = request.json
        batch_size = int(data.get('batch_size', 10))  # Process 10 companies per batch
        batch_number = int(data.get('batch_number', 1))
        project_name = data.get('project_name')
        designation = data.get('designation', '').strip()  # Custom designation/titles
        
        # Accept multiple employee ranges (new) or single range (backward compatibility)
        employee_ranges = data.get('employee_ranges', [])  # Accept array
        
        # Ensure employee_ranges is always a list to prevent "'int' object is not iterable" error
        if employee_ranges is None:
            employee_ranges = []
        elif isinstance(employee_ranges, (int, float)):
            # If it's a number, treat as no filter (empty list)
            employee_ranges = []
        elif isinstance(employee_ranges, str):
            # If it's a string, convert to list
            employee_ranges = [employee_ranges] if employee_ranges and employee_ranges.lower() != 'all' else []
        elif isinstance(employee_ranges, tuple):
            # Convert tuple to list
            employee_ranges = list(employee_ranges)
        elif not isinstance(employee_ranges, list):
            # If it's any other type that's not a list, convert to empty list
            employee_ranges = []
        
        # Backward compatibility: also check for old 'employee_range' parameter
        if not employee_ranges and data.get('employee_range'):
            employee_range_str = data.get('employee_range', '').strip()
            employee_ranges = [employee_range_str] if employee_range_str and employee_range_str.lower() != 'all' else []
        
        if not project_name:
            return jsonify({'error': 'project_name is required'}), 400
        
        # Validate Apollo API key before processing (save credits)
        print("🔍 Validating Apollo.io API key...")
        try:
            health_url = "https://api.apollo.io/v1/auth/health"
            health_response = requests.get(health_url, headers=apollo_client.headers, timeout=5)
            if health_response.status_code != 200:
                error_msg = f"Apollo.io API key validation failed (status {health_response.status_code}). Check your API key in config.py"
                print(f"❌ {error_msg}")
                return jsonify({'error': error_msg}), 401
            print("✅ Apollo.io API key is valid")
        except Exception as e:
            error_msg = f"Apollo.io API connection error: {str(e)}. Check your internet connection and API key."
            print(f"❌ {error_msg}")
            return jsonify({'error': error_msg}), 500
        
        # Get ONLY selected companies from Supabase for the active project
        companies = get_supabase_client().get_level1_companies(project_name=project_name, selected_only=True, limit=50)
        
        if not companies:
            return jsonify({'error': 'No companies selected for Level 2. Please select companies first.'}), 400
        
        # Filter companies by employee range(s) if specified
        if employee_ranges and len(employee_ranges) > 0:
            print(f"  🔍 Filtering companies by employee ranges: {employee_ranges}")
            print(f"  📊 Starting with {len(companies)} companies")
            # First, fetch employee counts for companies that don't have them yet
            # IMPORTANT: Only fetch if NOT in database (saves API credits!)
            companies_without_employee_data = [c for c in companies if not c.get('total_employees')]
            if companies_without_employee_data:
                print(f"  📊 Fetching employee counts for {len(companies_without_employee_data)} companies (saving API credits by skipping {len(companies) - len(companies_without_employee_data)} companies that already have data)...")
                fetched_count = 0
                for company in companies_without_employee_data:
                    company_name = company.get('company_name', '')
                    website = company.get('website', '')
                    if company_name:
                        try:
                            total_employees = apollo_client.get_company_total_employees(company_name, website) or ''
                            if total_employees:
                                # Validate employee count before using it
                                # Check if it's a reasonable number (not corrupted data)
                                try:
                                    # Try to parse and validate
                                    cleaned = str(total_employees).replace(',', '').replace(' ', '').strip()
                                    # If it's a simple number, check it's reasonable
                                    if cleaned.isdigit():
                                        num = int(cleaned)
                                        if num <= 0 or num > 1000000:  # Reject unreasonable numbers
                                            print(f"    ⚠️  {company_name}: Rejected invalid employee count: {total_employees}")
                                            total_employees = ''
                                except:
                                    pass  # If validation fails, still use the original value
                                
                                if total_employees:
                                    company['total_employees'] = total_employees
                                    fetched_count += 1
                                    print(f"    ✅ {company_name}: {total_employees} employees")
                                    # Update in database for future use
                                    if company.get('place_id'):
                                        try:
                                            get_supabase_client().update_level1_company_metrics(
                                                project_name=project_name,
                                                place_id=company['place_id'],
                                                total_employees=total_employees
                                            )
                                        except:
                                            pass  # Best effort - don't fail if update fails
                            else:
                                print(f"    ⚠️  {company_name}: No employee data available in Apollo")
                        except Exception as e:
                            print(f"    ⚠️  Could not fetch employee count for {company_name}: {str(e)}")
                            import traceback
                            traceback.print_exc()
                
                print(f"  📊 Fetched employee data for {fetched_count} out of {len(companies_without_employee_data)} companies")
            
            # Now filter by employee ranges
            companies_before_filter_list = companies.copy()  # Save the actual list, not just the length
            companies_before_filter_count = len(companies)
            companies = filter_companies_by_employee_range(companies, employee_ranges)
            companies_after_filter = len(companies)
            print(f"  📊 After filtering: {companies_after_filter} companies (filtered out {companies_before_filter_count - companies_after_filter})")
            
            if not companies:
                # Check if any companies had employee data
                companies_with_data = [c for c in companies_before_filter_list if c.get('total_employees')]
                # Ensure employee_ranges is a list before joining (extra safety check)
                if not isinstance(employee_ranges, (list, tuple)):
                    employee_ranges = []
                ranges_str = ', '.join(str(r) for r in employee_ranges) if employee_ranges else ''
                if not companies_with_data:
                    error_msg = f'No companies have employee data available. Employee range filter(s) "{ranges_str}" require employee data, but none of the {companies_before_filter_count} companies have this information in Apollo.io. Please select "All Company Sizes" to process all companies regardless of employee count.'
                else:
                    error_msg = f'No companies found matching employee range(s): {ranges_str}. {companies_before_filter_count - companies_after_filter} companies were filtered out. Try selecting "All Company Sizes" or different employee ranges.'
                
                return jsonify({
                    'message': error_msg,
                    'completed': True,
                    'processed': 0,
                    'total_companies': 0,
                    'error': f'Employee range filter removed all companies'
                }), 200
        
        # Calculate batch range
        start_idx = (batch_number - 1) * batch_size
        end_idx = start_idx + batch_size
        batch_companies = companies[start_idx:end_idx]
        
        if not batch_companies:
            return jsonify({'message': 'All companies processed', 'completed': True}), 200
        
        # Process batch with Enrichment Service (get contacts with emails only - phone numbers revealed in Apollo.io dashboard)
        enriched_companies = []
        current_company_name = ''  # Track the last company being processed
        
        import concurrent.futures
        
        def process_single_company(company):
            """Process a single company - get contacts with emails only (phone numbers revealed in Apollo.io dashboard)"""
            company_name = company.get('company_name', '')
            website = company.get('website', '')
            place_id = company.get('place_id', '')
            
            print(f"  📊 Processing company: {company_name}")
            
            # Parse designation into titles list if provided
            titles = None
            if designation and designation.strip():
                titles = [t.strip() for t in designation.split(',') if t.strip()]
                print(f"  🔍 Using custom designations: {titles}")
            else:
                print(f"  🔍 No designation specified, using default titles")
            
            # Get contacts from Enrichment Service (emails only - phone numbers revealed in Apollo.io dashboard)
            try:
                people = apollo_client.search_people_by_company(company_name, website, titles=titles)
                print(f"  ✅ Found {len(people) if people else 0} contacts for {company_name}")
            except Exception as e:
                print(f"  ❌ Error searching contacts for {company_name}: {str(e)}")
                import traceback
                traceback.print_exc()
                people = []
            
            # Company metrics - USE EXISTING DATA FIRST to save API credits!
            # Only fetch from API if we don't already have it (from database or filtering step)
            total_employees = company.get('total_employees', '') or ''
            # Only make API call if we don't have employee data (saves credits!)
            if not total_employees:
                total_employees = apollo_client.get_company_total_employees(company_name, website) or ''
                # If we got it from API, update the company object for future use
                if total_employees:
                    company['total_employees'] = total_employees
            active_members = len(people or [])
            active_members_with_email = sum(1 for p in (people or []) if p.get('email'))
            
            return {
                'company_name': company_name,
                'address': company.get('address', ''),
                'website': website,
                'phone': company.get('phone', ''),
                'pin_code': company.get('pin_code', ''),
                'industry': company.get('industry', ''),
                'total_employees': total_employees,
                'active_members': active_members,
                'active_members_with_email': active_members_with_email,
                'people': people,
                'place_id': place_id
            }
        
        # Process companies in parallel (but limit to avoid rate limits)
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            future_to_company = {executor.submit(process_single_company, company): company for company in batch_companies}
            
            for idx, future in enumerate(concurrent.futures.as_completed(future_to_company), start_idx + 1):
                company = future_to_company[future]
                try:
                    enriched_company = future.result()
                    enriched_companies.append(enriched_company)
                    current_company_name = enriched_company['company_name']
                    print(f"  ✅ Completed company {idx}/{len(companies)}: {current_company_name}")
                except Exception as e:
                    print(f"  ❌ Error processing company {company.get('company_name')}: {str(e)}")
                    # Add empty result to continue
                    enriched_companies.append({
                        'company_name': company.get('company_name', ''),
                        'address': company.get('address', ''),
                        'website': company.get('website', ''),
                        'phone': company.get('phone', ''),
                        'pin_code': company.get('pin_code', ''),
                        'industry': company.get('industry', ''),
                        'total_employees': '',
                        'active_members': 0,
                        'active_members_with_email': 0,
                        'people': [],
                        'place_id': company.get('place_id', '')
                    })
        
        # Update metrics and add founders/hr lists for each enriched company
        for enriched_company in enriched_companies:
            place_id = enriched_company.get('place_id', '')
            people = enriched_company.get('people', [])
            
            # Best-effort persist metrics back to Supabase (level1_companies)
            if place_id:
                try:
                    get_supabase_client().update_level1_company_metrics(
                        project_name=project_name,
                        place_id=place_id,
                        total_employees=enriched_company.get('total_employees', ''),
                        active_members=enriched_company.get('active_members', 0),
                        active_members_with_email=enriched_company.get('active_members_with_email', 0),
                    )
                except Exception as e:
                    print(f"  ⚠️  Could not update metrics for {enriched_company.get('company_name')}: {str(e)}")
            
            # Add founders and HR lists
            enriched_company['founders'] = [p for p in people if p.get('title') and any(keyword.lower() in p.get('title', '').lower() 
                                                           for keyword in ['founder', 'owner', 'ceo', 'co-founder', 'founder/owner'])]
            enriched_company['hr_contacts'] = [p for p in people if p.get('title') and any(keyword.lower() in p.get('title', '').lower() 
                                                              for keyword in ['hr', 'human resources', 'recruiter', 'talent', 'human resource'])]
        
        # Use a consistent batch name for this project session (reuse existing or create new)
        # This prevents duplicate batches when processing in multiple batches
        default_batch_name = f"{project_name}_Main_Batch"
        
        # Save to Supabase with consistent batch name
        save_result = get_supabase_client().save_level2_results(
            enriched_companies, 
            project_name=project_name,
            batch_name=default_batch_name
        )
        
        total_contacts = sum(len(c.get('people', [])) for c in enriched_companies)
        
        # Phone numbers are not requested to save credits
        # Users should reveal phone numbers in Apollo.io dashboard when needed
        print(f"  ✅ Contacts saved with emails. Phone numbers can be revealed in Apollo.io dashboard when needed.")
        
        # Get the last processed company name for progress display
        if enriched_companies:
            current_company_name = enriched_companies[-1].get('company_name', '')
        else:
            current_company_name = ''
        
        print(f"  ✅ Batch {batch_number} complete: {len(batch_companies)} companies, {total_contacts} contacts found")
        if designation:
            print(f"  🔍 Designation filter used: {designation}")
        if employee_ranges:
            print(f"  👥 Employee range filter(s) used: {employee_ranges}")
        
        # If no contacts found, provide helpful message
        if total_contacts == 0:
            print(f"  ⚠️  No contacts found. This could be because:")
            if designation:
                print(f"     - Designation filter '{designation}' is too specific")
            if employee_ranges:
                print(f"     - Employee range filter(s) '{employee_ranges}' filtered out companies")
            print(f"     - Companies don't have contacts matching the criteria")
        
        return jsonify({
            'success': True,
            'batch_number': batch_number,
            'batch_size': len(batch_companies),
            'total_companies': len(companies),
            'processed': start_idx + len(batch_companies),
            'remaining': len(companies) - (start_idx + len(batch_companies)),
            'completed': end_idx >= len(companies),
            'contacts_found': total_contacts,
            'current_company': current_company_name,  # For progress display
            'designation_used': designation if designation else None,
            'employee_ranges_used': employee_ranges if employee_ranges else None
        }), 200
        
    except Exception as e:
        print(f"Error in Level 2 processing: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/level1/save', methods=['POST'])
def level1_save_manual():
    """Manual save endpoint - saves companies that were found but not saved"""
    try:
        data = request.json
        project_name = data.get('project_name', '').strip()
        companies = data.get('companies', [])
        pin_codes = data.get('pin_codes', '')
        industry = data.get('industry', '')
        
        if not project_name:
            return jsonify({'success': False, 'error': 'Project name is required'}), 400
        
        if not companies:
            return jsonify({'success': False, 'error': 'No companies to save'}), 400
        
        logger.info(f"💾 Manual save requested for project '{project_name}' with {len(companies)} companies")
        
        search_params = {
            'project_name': project_name,
            'pin_codes': pin_codes or '',
            'industry': industry or '',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        save_result = get_supabase_client().save_level1_results(companies, search_params)
        
        if save_result.get('success'):
            saved_count = save_result.get('count', 0)
            logger.info(f"✅ Manual save successful: {saved_count} companies saved for project '{project_name}'")
            return jsonify({
                'success': True,
                'count': saved_count,
                'message': f'Successfully saved {saved_count} companies to database'
            }), 200
        else:
            error_msg = save_result.get('error', 'Unknown error')
            logger.error(f"❌ Manual save failed for project '{project_name}': {error_msg}")
            return jsonify({
                'success': False,
                'error': error_msg
            }), 500
            
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Error in manual save: {error_msg}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': error_msg}), 500

@app.route('/api/level1/projects', methods=['GET'])
def get_projects_list():
    """Get list of all projects (for history/resume feature) - from Supabase"""
    try:
        client = get_supabase_client()
        projects = client.get_projects_list()
        print(f"✅ API: Returning {len(projects)} projects: {[p.get('project_name') for p in projects]}")
        return jsonify({'projects': projects}), 200
    except Exception as e:
        print(f"❌ Error getting projects list: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'projects': [], 'error': str(e)}), 200

@app.route('/api/level1/project-data', methods=['GET'])
def get_project_data():
    """Get project data including companies, PIN codes, and industry for a specific project"""
    try:
        project_name = request.args.get('project_name')
        if not project_name:
            return jsonify({'error': 'project_name is required'}), 400
        
        # Get project details from projects list
        projects = get_supabase_client().get_projects_list()
        project_info = next((p for p in projects if p.get('project_name') == project_name), None)
        
        if not project_info:
            return jsonify({'error': 'Project not found'}), 404
        
        # Get companies for this project
        companies = get_supabase_client().get_level1_companies(project_name=project_name, selected_only=False, limit=100)
        
        # Format companies for frontend
        formatted_companies = []
        for company in companies:
            formatted_companies.append({
                'company_name': company.get('company_name', ''),
                'website': company.get('website', ''),
                'phone': company.get('phone', ''),
                'address': company.get('address', ''),
                'pin_code': company.get('pin_code', ''),
                'industry': company.get('industry', ''),
                'place_type': company.get('place_type', ''),
                'place_id': company.get('place_id', ''),
                'business_status': company.get('business_status', ''),
                'selected_for_level2': company.get('selected_for_level2', False)
            })
        
        return jsonify({
            'project_name': project_name,
            'pin_codes': project_info.get('pin_codes', ''),
            'industry': project_info.get('industry', ''),
            'search_date': project_info.get('search_date', ''),
            'companies': formatted_companies,
            'total_companies': len(formatted_companies)
        }), 200
        
    except Exception as e:
        print(f"Error getting project data: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/level1/delete-companies', methods=['POST'])
def delete_level1_companies():
    """Delete selected Level 1 companies from Supabase (per project)."""
    try:
        data = request.json or {}
        project_name = (data.get('project_name') or '').strip()
        identifiers = data.get('identifiers', [])

        if not project_name:
            return jsonify({'error': 'project_name is required'}), 400
        if not isinstance(identifiers, list) or len(identifiers) == 0:
            return jsonify({'error': 'identifiers must be a non-empty list'}), 400

        result = get_supabase_client().delete_level1_companies(project_name=project_name, identifiers=identifiers)
        if not result.get('success'):
            return jsonify({'error': result.get('error', 'Failed to delete companies')}), 500

        return jsonify(result), 200

    except Exception as e:
        print(f"Error deleting Level 1 companies: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/level1/delete-project', methods=['POST'])
def delete_level1_project():
    """Delete an entire project from Supabase (Level 1 companies + Level 2 contacts)."""
    try:
        data = request.json or {}
        project_name = (data.get('project_name') or '').strip()

        if not project_name:
            return jsonify({'error': 'project_name is required'}), 400

        result = get_supabase_client().delete_project(project_name=project_name)
        if not result.get('success'):
            return jsonify({'error': result.get('error', 'Failed to delete project')}), 500

        return jsonify(result), 200

    except Exception as e:
        print(f"Error deleting project: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/level1/check-project', methods=['POST'])
def check_project_exists():
    """Check if project name already exists"""
    try:
        data = request.json
        project_name = data.get('project_name', '').strip()
        
        if not project_name:
            return jsonify({'exists': False}), 200
        
        # Check in Supabase
        companies = get_supabase_client().get_level1_companies(project_name=project_name, limit=1)
        exists = len(companies) > 0
        
        return jsonify({'exists': exists}), 200
    except Exception as e:
        print(f"Error checking project: {str(e)}")
        return jsonify({'exists': False}), 200

@app.route('/api/level1/select-for-level2', methods=['POST'])
def select_companies_for_level2():
    """Mark selected companies for Level 2 processing"""
    try:
        data = request.json
        companies = data.get('companies', [])
        project_name = data.get('project_name', '').strip()
        
        if not companies:
            return jsonify({'error': 'No companies provided'}), 400
        
        if not project_name:
            return jsonify({'error': 'Project name is required'}), 400
        
        # Mark companies as selected in Supabase (with project_name for filtering)
        result = get_supabase_client().mark_companies_selected(companies, project_name=project_name)
        
        if result.get('success'):
            return jsonify({
                'status': 'success',
                'message': f'Successfully marked {len(companies)} companies for Level 2',
                'count': len(companies),
                'project_name': project_name
            }), 200
        else:
            return jsonify({'error': result.get('error', 'Failed to mark companies')}), 500
            
    except Exception as e:
        print(f"Error marking companies for Level 2: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/level2/companies', methods=['GET'])
def get_level2_companies():
    """Level 2: Get companies from Supabase for enrichment"""
    try:
        project_name = request.args.get('project_name')
        limit = int(request.args.get('limit', 50))

        if not project_name:
            return jsonify({'error': 'project_name is required'}), 400

        # Pull companies for that project
        all_companies = get_supabase_client().get_level1_companies(project_name=project_name, selected_only=False, limit=limit)
        if not all_companies:
            return jsonify({'companies': [], 'project_name': project_name, 'mode': 'all'}), 200

        selected = [c for c in all_companies if c.get('selected_for_level2', False)]
        mode = 'selected' if len(selected) > 0 else 'all'

        def to_ui(c):
            place_id = c.get('place_id') or c.get('company_name')
            is_selected = c.get('selected_for_level2', False)
            default_selected = is_selected if mode == 'selected' else True
            return {
                'place_id': place_id,
                'company_name': c.get('company_name', ''),
                'website': c.get('website', ''),
                'phone': c.get('phone', ''),
                'address': c.get('address', ''),
                'pin_code': c.get('pin_code', ''),
                'industry': c.get('industry', ''),
                'total_employees': c.get('total_employees', ''),
                'active_members': c.get('active_members', 0),
                'active_members_with_email': c.get('active_members_with_email', 0),
                'selected': is_selected,
                'default_selected': default_selected,
            }

        companies = [to_ui(c) for c in all_companies]
        return jsonify({
            'companies': companies,
            'project_name': project_name,
            'mode': mode,
            'total_companies_all': len(all_companies),
            'total_companies_selected': len(selected),
        }), 200
    except Exception as e:
        print(f"Error getting Level 1 companies for Level 2: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/level2/selection', methods=['POST'])
def set_level2_selection():
    """Level 2: Persist the user's selection (after removing companies) to Supabase"""
    try:
        data = request.json or {}
        project_name = data.get('project_name')
        selected_place_ids = data.get('selected_place_ids', [])

        if not project_name:
            return jsonify({'error': 'project_name is required'}), 400

        if not isinstance(selected_place_ids, list):
            return jsonify({'error': 'selected_place_ids must be a list'}), 400

        # Persist selection (sets selected_for_level2 true/false for this project)
        result = get_supabase_client().set_level2_selection(project_name=project_name, selected_place_ids=selected_place_ids)
        
        if not result.get('success'):
            return jsonify({'error': result.get('error', 'Failed to save selection')}), 500

        return jsonify(result), 200
    except Exception as e:
        print(f"Error setting Level 2 selection: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/level2/history', methods=['GET'])
def get_search_history():
    """Get search history from Supabase (same as projects list)"""
    try:
        projects = get_supabase_client().get_projects_list()
        # Convert to history format for compatibility
        history = [{
            'project_name': p.get('project_name', ''),
            'search_date': p.get('search_date', ''),
            'industry': p.get('industry', ''),
            'pin_codes': p.get('pin_codes', '')
        } for p in projects]
        return jsonify({'history': history}), 200
    except Exception as e:
        print(f"Error getting search history: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/level2/status', methods=['GET'])
def level2_status():
    """Get status of companies in Supabase for Level 2"""
    try:
        project_name = request.args.get('project_name')
        
        if not project_name:
            return jsonify({'error': 'project_name is required'}), 400
        
        all_companies = get_supabase_client().get_level1_companies(project_name=project_name, selected_only=False, limit=50)
        selected = [c for c in all_companies if c.get('selected_for_level2', False)]
        selected_count = len(selected)
        total_count = len(all_companies)
        active_count = selected_count if selected_count > 0 else total_count

        # Attach project metadata so UI can confirm we are not mixing Industry/PINs
        session_meta = {}
        try:
            projects = get_supabase_client().get_projects_list()
            for p in projects:
                if p.get('project_name') == project_name:
                    session_meta = {
                        'pin_codes': p.get('pin_codes', ''),
                        'industry': p.get('industry', ''),
                        'search_date': p.get('search_date', ''),
                    }
                    break
        except Exception:
            session_meta = {}

        return jsonify({
            'total_companies': active_count,
            'total_companies_all': total_count,
            'total_companies_selected': selected_count,
            'mode': 'selected' if selected_count > 0 else 'all',
            'project_name': project_name,
            'session': session_meta,
            'ready_for_processing': active_count > 0
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/level2/contacts', methods=['GET'])
def level2_contacts():
    """Get Level 2 contacts for a project"""
    try:
        project_name = request.args.get('project_name')
        batch_name = request.args.get('batch_name')  # Optional: filter by specific batch
        
        if not project_name and not batch_name:
            return jsonify({'error': 'project_name or batch_name is required'}), 400
        
        # Get contacts from Supabase
        if batch_name:
            contacts = get_supabase_client().get_contacts_for_level3(batch_name=batch_name)
        else:
            contacts = get_supabase_client().get_contacts_for_level3(project_name=project_name)
        
        # Map phone_number to phone for frontend compatibility
        formatted_contacts = []
        for contact in contacts:
            formatted_contact = dict(contact)
            # Ensure phone field is available (map from phone_number if needed)
            phone_value = formatted_contact.get('phone') or formatted_contact.get('phone_number') or ''
            formatted_contact['phone'] = phone_value
            formatted_contact['phone_number'] = phone_value  # Keep both for compatibility
            # Also ensure contact_name maps to name
            if not formatted_contact.get('name') and formatted_contact.get('contact_name'):
                formatted_contact['name'] = formatted_contact['contact_name']
            formatted_contacts.append(formatted_contact)
        
        return jsonify({
            'success': True,
            'contacts': formatted_contacts,
            'count': len(formatted_contacts)
        }), 200
    except Exception as e:
        print(f"Error getting Level 2 contacts: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/level2/enrich-phones', methods=['POST'])
def enrich_phones_parallel():
    """
    DEPRECATED: Phone numbers are no longer enriched via API to save credits.
    Phone numbers should be revealed in Apollo.io dashboard when needed.
    This endpoint returns empty results with a message.
    """
    # Phone numbers are not requested via API to save credits
    # Users should reveal phone numbers in Apollo.io dashboard when needed
    return jsonify({
        'success': True,
        'phones': {},
        'message': 'Phone numbers are not enriched via API to save credits. Please reveal phone numbers in Apollo.io dashboard when needed.',
        'note': 'This saves ~2-3 credits per contact. Reveal phone numbers in Apollo.io dashboard for contacts you want to call.'
    }), 200

@app.route('/api/level2/save-batch', methods=['POST'])
def level2_save_batch():
    """Save Level 2 batch with batch_name"""
    try:
        data = request.json or {}
        project_name = data.get('project_name')
        batch_name = data.get('batch_name')
        
        if not project_name:
            return jsonify({'error': 'project_name is required'}), 400
        if not batch_name:
            return jsonify({'error': 'batch_name is required'}), 400
        
        # Update all contacts for this project to use the batch_name
        # This is a simple implementation - in production you might want more sophisticated logic
        result = get_supabase_client().update_batch_name(project_name, batch_name)
        
        return jsonify({
            'success': True,
            'message': f'Batch "{batch_name}" saved successfully',
            'batch_name': batch_name
        }), 200
    except Exception as e:
        print(f"Error saving batch: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/level2/batches', methods=['GET'])
def level2_batches():
    """Get list of all Level 2 batches"""
    try:
        project_name = request.args.get('project_name')  # Optional: filter by project
        
        # Get batches from Supabase
        batches = get_supabase_client().get_batches_list(project_name=project_name)
        
        return jsonify({
            'success': True,
            'batches': batches,
            'count': len(batches)
        }), 200
    except Exception as e:
        print(f"Error getting batches: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/level2/delete-batch', methods=['POST'])
def level2_delete_batch():
    """Delete a batch and all its contacts"""
    try:
        data = request.json or {}
        batch_name = data.get('batch_name', '').strip()
        
        if not batch_name:
            return jsonify({'error': 'batch_name is required'}), 400
        
        result = get_supabase_client().delete_batch(batch_name)
        
        if not result.get('success'):
            return jsonify({'error': result.get('error', 'Failed to delete batch')}), 500
        
        return jsonify({
            'success': True,
            'message': f'Batch "{batch_name}" deleted successfully',
            'deleted_contacts': result.get('deleted_contacts', 0)
        }), 200
    except Exception as e:
        print(f"Error deleting batch: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/level2/merge-batches', methods=['POST'])
def level2_merge_batches():
    """Merge all batches for a project into one batch"""
    try:
        data = request.json or {}
        project_name = data.get('project_name', '').strip()
        target_batch_name = data.get('target_batch_name', '').strip()
        
        if not project_name:
            return jsonify({'error': 'project_name is required'}), 400
        
        # Use project name as default batch name if not provided
        if not target_batch_name:
            target_batch_name = f"{project_name}_Main_Batch"
        
        result = get_supabase_client().merge_duplicate_batches(project_name, target_batch_name)
        
        if not result.get('success'):
            return jsonify({'error': result.get('error', 'Failed to merge batches')}), 500
        
        return jsonify({
            'success': True,
            'message': f'Merged {result.get("merged_contacts", 0)} contacts into "{target_batch_name}"',
            'merged_contacts': result.get('merged_contacts', 0),
            'batch_name': target_batch_name
        }), 200
    except Exception as e:
        print(f"Error merging batches: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/level2/delete-duplicate-batches', methods=['POST'])
def level2_delete_duplicate_batches():
    """Delete all duplicate batches for a project, keeping only the main one"""
    try:
        data = request.json or {}
        project_name = data.get('project_name', '').strip()
        
        if not project_name:
            return jsonify({'error': 'project_name is required'}), 400
        
        # Get all batches for this project
        batches = get_supabase_client().get_batches_list(project_name=project_name)
        
        if len(batches) <= 1:
            return jsonify({
                'success': True,
                'message': 'No duplicate batches to delete',
                'deleted': 0
            }), 200
        
        # Keep the batch with most contacts, delete others
        batches.sort(key=lambda x: x.get('contact_count', 0), reverse=True)
        main_batch = batches[0]
        duplicate_batches = batches[1:]
        
        deleted_count = 0
        deleted_contacts = 0
        
        for batch in duplicate_batches:
            result = get_supabase_client().delete_batch(batch.get('batch_name'))
            if result.get('success'):
                deleted_count += 1
                deleted_contacts += result.get('deleted_contacts', 0)
        
        return jsonify({
            'success': True,
            'message': f'Deleted {deleted_count} duplicate batches',
            'deleted_batches': deleted_count,
            'deleted_contacts': deleted_contacts,
            'kept_batch': main_batch.get('batch_name')
        }), 200
    except Exception as e:
        print(f"Error deleting duplicate batches: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/level3/transfer', methods=['POST'])
def level3_transfer():
    """Level 3: Transfer contacts from Supabase to Outreach Platform"""
    try:
        data = request.json or {}
        batch_name = data.get('batch_name')
        project_name = data.get('project_name')  # Optional fallback
        
        if not batch_name and not project_name:
            return jsonify({'error': 'batch_name or project_name is required'}), 400
        
        # Get contacts from Supabase (prefer batch_name)
        if batch_name:
            contacts = get_supabase_client().get_contacts_for_level3(batch_name=batch_name)
        else:
            contacts = get_supabase_client().get_contacts_for_level3(project_name=project_name)
        
        if not contacts:
            return jsonify({'error': 'No contacts found in Supabase. Please run Level 2 first.'}), 400
        
        # NOTE: Deprecated bulk transfer path – use /api/level3/transfer-one for per-contact progress.
        return jsonify({
            'success': False,
            'error': 'Use /api/level3/transfer-one for per-contact transfer with progress.'
        }), 400
        
    except Exception as e:
        print(f"Error in Level 3 transfer: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/level3/status', methods=['GET'])
def level3_status():
    """Get status of contacts in Supabase for Level 3"""
    try:
        project_name = request.args.get('project_name')
        
        if not project_name:
            return jsonify({'error': 'project_name is required'}), 400
        
        contacts = get_supabase_client().get_contacts_for_level3(project_name=project_name)
        return jsonify({
            'total_contacts': len(contacts),
            'ready_for_transfer': len(contacts) > 0
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/level3/create-list', methods=['POST'])
def level3_create_list():
    """Create a list in Outreach Platform and return list_id"""
    try:
        data = request.json or {}
        list_name = data.get('list_name', '').strip()
        if not list_name:
            return jsonify({'error': 'list_name is required'}), 400

        result = apollo_client.create_contact_list(list_name)
        if result.get('success'):
            return jsonify({'success': True, 'list_id': result.get('list_id')}), 200
        return jsonify({'error': result.get('error', 'Failed to create list')}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/level3/contacts', methods=['GET'])
def level3_contacts():
    """Return contact list for a batch (for preview and transfer)"""
    try:
        batch_name = request.args.get('batch_name')
        if not batch_name:
            return jsonify({'error': 'batch_name is required'}), 400

        contacts = get_supabase_client().get_contacts_for_level3(batch_name=batch_name)
        # Minimal fields for preview/progress
        minimal = []
        for c in contacts:
            minimal.append({
                'id': c.get('id'),
                'name': c.get('contact_name', '') or c.get('name', ''),
                'email': c.get('email', ''),
                'company_name': c.get('company_name', ''),
                'title': c.get('contact_type', '') or c.get('title', '')
            })
        return jsonify({'success': True, 'contacts': minimal, 'count': len(minimal)}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/level3/transfer-one', methods=['POST'])
def level3_transfer_one():
    """Transfer a single contact to Outreach Platform with dedupe + list add"""
    try:
        data = request.json or {}
        contact_id = data.get('contact_id')
        list_id = data.get('list_id')
        if not contact_id:
            return jsonify({'error': 'contact_id is required'}), 400

        # Fetch contact from Supabase
        contacts = get_supabase_client().get_level2_contacts_by_ids([contact_id])
        if not contacts:
            return jsonify({'error': 'Contact not found'}), 404
        contact = contacts[0]

        contact_name = contact.get('contact_name', '') or contact.get('name', '')
        name_parts = contact_name.split() if contact_name else []
        contact_data = {
            'first_name': name_parts[0] if len(name_parts) > 0 else '',
            'last_name': ' '.join(name_parts[1:]) if len(name_parts) > 1 else '',
            'email': contact.get('email', ''),
            'phone': contact.get('phone_number', ''),
            'linkedin_url': contact.get('linkedin_url', ''),
            'organization_name': contact.get('company_name', ''),
            'title': contact.get('contact_type', '') or contact.get('title', '')
        }

        # Create contact in Outreach Platform
        # Note: Duplicate check removed to save credits (~1 credit per contact)
        # Apollo.io handles duplicates automatically, and users can filter by name/email in dashboard
        result = apollo_client.create_contact(contact_data)
        if not result.get('success'):
            return jsonify({
                'success': False,
                'status': 'failed',
                'reason': result.get('error', 'Outreach Platform error'),
                'contact': contact_name
            }), 200

        # Add to list if list_id provided
        if list_id:
            add_result = apollo_client.add_contact_to_list(list_id, result.get('contact_id'))
            if not add_result.get('success'):
                return jsonify({
                    'success': True,
                    'status': 'warning',
                    'reason': add_result.get('error', 'List add failed'),
                    'contact': contact_name
                }), 200

        return jsonify({
            'success': True,
            'status': 'transferred',
            'contact': contact_name
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/level2/delete-companies', methods=['POST'])
def level2_delete_companies():
    """Delete unselected companies from Level 1"""
    try:
        data = request.json
        project_name = data.get('project_name')
        place_ids = data.get('place_ids', [])
        
        if not project_name:
            return jsonify({'error': 'project_name is required'}), 400
        
        if not place_ids:
            return jsonify({'error': 'No place_ids provided'}), 400
        
        # Delete companies using supabase_client
        result = get_supabase_client().delete_level1_companies(project_name=project_name, identifiers=place_ids)
        
        if result.get('success'):
            deleted_count = result.get('deleted', 0)
            return jsonify({
                'success': True,
                'message': f'Successfully deleted {deleted_count} companies',
                'deleted': deleted_count
            }), 200
        else:
            return jsonify({'error': result.get('error', 'Failed to delete companies')}), 500
            
    except Exception as e:
        print(f"Error deleting companies: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/export', methods=['POST'])
def export():
    """Export Level 1 company data to Excel file (Places API only - no contacts)"""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
        from flask import send_file
        import io
        
        data = request.json
        companies = data.get('companies', [])
        project_name = data.get('project_name', 'companies')
        
        if not companies:
            return jsonify({'error': 'No companies to export'}), 400
        
        # Create Excel workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Companies"
        
        # Headers
        headers = ['Company Name', 'Website', 'Phone', 'Address', 'Industry', 'PIN Code', 'Place ID', 'Place Type']
        ws.append(headers)
        
        # Style header row
        header_fill = PatternFill(start_color="667eea", end_color="667eea", fill_type="solid")
        header_font = Font(bold=True, color="FFFFFF")
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
        
        # Add data rows
        for company in companies:
            ws.append([
                company.get('company_name', ''),
                company.get('website', ''),
                company.get('phone', ''),
                company.get('address', ''),
                company.get('industry', ''),
                company.get('pin_code', ''),
                company.get('place_id', ''),
                company.get('place_type', '')
            ])
        
        # Auto-adjust column widths
        for column in ws.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)
            ws.column_dimensions[column_letter].width = adjusted_width
        
        # Save to BytesIO
        excel_file = io.BytesIO()
        wb.save(excel_file)
        excel_file.seek(0)
        
        # Generate filename
        safe_project_name = "".join(c for c in project_name if c.isalnum() or c in (' ', '-', '_')).strip()[:50]
        filename = f"{safe_project_name}_companies.xlsx" if safe_project_name else "companies.xlsx"
        
        return send_file(
            excel_file,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        print(f"Error exporting to Excel: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/export-contacts', methods=['POST'])
def export_contacts():
    """Export Level 3 contacts data to Excel file"""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
        from flask import send_file
        import io
        
        data = request.json
        contacts = data.get('contacts', [])
        batch_name = data.get('batch_name', 'contacts')
        
        if not contacts:
            return jsonify({'error': 'No contacts to export'}), 400
        
        # Create Excel workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Contacts"
        
        # Headers
        headers = ['Name', 'Title', 'Company Name', 'Email', 'Phone', 'LinkedIn URL', 'Company Website', 'Company Address']
        ws.append(headers)
        
        # Style header row
        header_fill = PatternFill(start_color="10b981", end_color="10b981", fill_type="solid")
        header_font = Font(bold=True, color="FFFFFF")
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
        
        # Add data rows
        for contact in contacts:
            ws.append([
                contact.get('name') or contact.get('contact_name', ''),
                contact.get('title') or contact.get('contact_type', ''),
                contact.get('company_name', ''),
                contact.get('email', ''),
                contact.get('phone', ''),
                contact.get('linkedin_url', ''),
                contact.get('company_website', ''),
                contact.get('company_address', '')
            ])
        
        # Auto-adjust column widths
        for column in ws.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)
            ws.column_dimensions[column_letter].width = adjusted_width
        
        # Save to BytesIO
        excel_file = io.BytesIO()
        wb.save(excel_file)
        excel_file.seek(0)
        
        # Generate filename
        safe_batch_name = "".join(c for c in batch_name if c.isalnum() or c in (' ', '-', '_')).strip()[:50]
        filename = f"{safe_batch_name}_contacts.xlsx" if safe_batch_name else "contacts.xlsx"
        
        return send_file(
            excel_file,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        print(f"Error exporting contacts to Excel: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/apollo/webhook', methods=['POST'])
def apollo_webhook():
    """
    Webhook endpoint to receive phone numbers from Enrichment Service
    Service sends phone numbers via webhook after enrichment request
    """
    try:
        data = request.json or {}
        
        # Enrichment service webhook payload structure
        person = data.get('person', {}) or data.get('data', {}).get('person', {})
        if not person:
            print("⚠️  Enrichment webhook: No person data in payload")
            return jsonify({'success': False, 'error': 'No person data'}), 400
        
        person_id = person.get('id') or data.get('person_id')
        email = person.get('email', '')
        phone_numbers = person.get('phone_numbers', [])
        
        print(f"📞 Enrichment webhook received for person_id: {person_id}, email: {email}")
        print(f"📞 Phone numbers: {phone_numbers}")
        
        # Extract phone number
        phone = ''
        if phone_numbers and len(phone_numbers) > 0:
            phone_obj = phone_numbers[0]
            phone = (
                phone_obj.get('raw_number', '') or
                phone_obj.get('sanitized_number', '') or
                phone_obj.get('number', '') or
                phone_obj.get('phone', '')
            )
        
        if phone:
            print(f"✅ Extracted phone from webhook: {phone}")
            # Update contact in database with phone number
            # Match by email (most reliable)
            if email:
                try:
                    # Update contacts with this email in level2_contacts table
                    supabase = get_supabase_client()
                    # Update all contacts with matching email
                    result = supabase.client.table('level2_contacts').update({
                        'phone_number': phone
                    }).eq('email', email).execute()
                    
                    if result.data:
                        print(f"✅ Updated {len(result.data)} contact(s) with phone number: {phone}")
                    else:
                        print(f"⚠️  No contacts found with email: {email}")
                except Exception as e:
                    print(f"⚠️  Could not update contact with phone: {str(e)}")
        else:
            print(f"⚠️  No phone number in webhook payload")
        
        return jsonify({'success': True, 'phone': phone}), 200
        
    except Exception as e:
        print(f"❌ Error processing enrichment webhook: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

# Vercel serverless handler (required for Vercel Python runtime)
# Vercel expects the app to be directly callable
# The @vercel/python builder automatically wraps Flask apps
# Updated: 2026-01-24 - Multiple employee range selection feature added

if __name__ == '__main__':
    Config.validate()
    port = int(os.getenv('PORT', 5002))
    app.run(debug=False, host='0.0.0.0', port=port)

