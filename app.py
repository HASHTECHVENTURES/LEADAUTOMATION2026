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
    """Level 1: Company Search (Google Places only)"""
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
    """Level 2: Contact Enrichment (Apollo.io)"""
    return render_template('level2.html')

@app.route('/level3')
@login_required
def level3():
    """Level 3: Transfer to Apollo.io Dashboard"""
    return render_template('level3.html')

@app.route('/api/level1/search', methods=['POST'])
def level1_search():
    """Level 1: Search companies using Google Places only, save to database"""
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
                    'message': 'Searching Google Places...',
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
                
                # Step 1: Search Google Places for all PIN codes
                all_companies = []
                total_pin_codes = len(pin_codes)
                companies_per_pin = max(1, max_companies // total_pin_codes)  # Distribute companies across PIN codes
                
                for idx, pin_code in enumerate(pin_codes, 1):
                    # Progress for PIN-level search (so the UI doesn't look "stuck")
                    yield f"data: {json.dumps({'type': 'progress', 'data': {'stage': 'searching_places', 'message': f'Searching PIN {idx}/{total_pin_codes}: {pin_code}...', 'current': idx, 'total': total_pin_codes, 'companies_found': len(all_companies)}})}\n\n"
                    
                    print(f"🔍 Calling Google Places API: PIN={pin_code} ({idx}/{total_pin_codes}), Industry={industry}, MaxResults={companies_per_pin}")
                    
                    # Search Google Places for this PIN code
                    try:
                        companies = google_client.search_by_pin_and_industry(
                            pin_code=pin_code,
                            industry=industry,
                            max_results=companies_per_pin
                        )
                        
                        # Add PIN code to each company for tracking
                        for company in companies:
                            company['pin_code'] = pin_code
                        
                        all_companies.extend(companies)
                        print(f"✅ Found {len(companies)} companies for PIN {pin_code}")

                        # Emit a progress update after each PIN finishes so "Companies Found" updates live
                        yield f"data: {json.dumps({'type': 'progress', 'data': {'stage': 'searching_places', 'message': f'Finished PIN {idx}/{total_pin_codes}: {pin_code}. Found {len(companies)} companies (Total: {len(all_companies)}).', 'current': idx, 'total': total_pin_codes, 'companies_found': len(all_companies)}})}\n\n"
                        
                    except Exception as e:
                        print(f"❌ Error searching PIN {pin_code}: {str(e)}")
                        continue
                
                companies = all_companies[:max_companies]  # Limit to max_companies total
                print(f"✅ Google Places returned {len(companies) if companies else 0} companies total from {total_pin_codes} PIN code(s)")
                
                if not companies:
                    pin_codes_str = ', '.join(pin_codes)
                    error_msg = f'No companies found for PIN code(s): {pin_codes_str}. Please try different PIN codes or check if they are correct.'
                    print(f"⚠️  {error_msg}")
                    yield f"data: {json.dumps({'type': 'complete', 'data': {'companies': [], 'message': error_msg, 'total_companies': 0}})}\n\n"
                    return
                
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
                    
                    save_result = get_supabase_client().save_level1_results(companies, search_params)
                    if save_result.get('success'):
                        print(f"✅ Saved {save_result.get('count')} companies to Supabase for project: '{project_name}'")
                        logger.info(f"✅ Saved {save_result.get('count')} companies to Supabase for project: '{project_name}'")
                    else:
                        error_msg = save_result.get('error', 'Unknown error')
                        print(f"❌ Error saving to Supabase: {error_msg}")
                        logger.error(f"❌ Error saving to Supabase for project '{project_name}': {error_msg}")
                        raise Exception(f"Failed to save to Supabase: {error_msg}")
                except Exception as e:
                    print(f"❌ Error saving to Supabase: {str(e)}")
                    import traceback
                    traceback.print_exc()
                
                # Send incremental company updates
                for idx, company in enumerate(companies, 1):
                    # Update progress in Supabase periodically (every 5 companies to reduce DB calls)
                    if idx % 5 == 0 or idx == len(companies):
                        update_progress = {
                            'current': idx,
                            'message': f'Processed {company.get("company_name", "")}... ({idx}/{len(companies)})',
                            'status': 'in_progress'
                        }
                        get_supabase_client().save_progress(session_key, update_progress)
                    
                    yield f"data: {json.dumps({'type': 'company_update', 'data': company, 'progress': {'current': idx, 'total': len(companies), 'companies_found': len(companies)}})}\n\n"
                
                # Final result - mark as completed in Supabase
                completed_progress = {
                    'stage': 'completed',
                    'message': f'Found {len(companies)} companies and saved to database.',
                    'current': len(companies),
                    'total': len(companies),
                    'companies_found': len(companies),
                    'status': 'completed'
                }
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
                print(f"Error in search stream: {error_msg}")
                try:
                    yield f"data: {json.dumps({'type': 'error', 'data': {'error': error_msg}})}\n\n"
                except (BrokenPipeError, ConnectionResetError, GeneratorExit):
                    return
            finally:
                # Clean up progress from Supabase after a delay (keep for 1 hour for recovery)
                # For immediate cleanup, uncomment the line below:
                # get_supabase_client().delete_progress(session_key)
                pass
        
        return Response(stream_with_context(generate()), mimetype='text/event-stream')
        
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
        companies_per_pin = max(1, 20 // len(pin_codes))  # Distribute 20 companies across PIN codes
        
        for pin_code in pin_codes:
            companies = google_client.search_by_pin_and_industry(
                pin_code=pin_code,
                industry=industry,
                max_results=companies_per_pin
            )
            all_companies.extend(companies)
        
        companies = all_companies[:20]  # Limit to 20 total
        
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
    """Level 2: Process companies from Supabase with Apollo.io to get contacts"""
    try:
        data = request.json
        batch_size = int(data.get('batch_size', 10))  # Process 10 companies per batch
        batch_number = int(data.get('batch_number', 1))
        project_name = data.get('project_name')
        
        if not project_name:
            return jsonify({'error': 'project_name is required'}), 400
        
        # Get ONLY selected companies from Supabase for the active project
        companies = get_supabase_client().get_level1_companies(project_name=project_name, selected_only=True, limit=50)
        
        if not companies:
            return jsonify({'error': 'No companies selected for Level 2. Please select companies first.'}), 400
        
        # Calculate batch range
        start_idx = (batch_number - 1) * batch_size
        end_idx = start_idx + batch_size
        batch_companies = companies[start_idx:end_idx]
        
        if not batch_companies:
            return jsonify({'message': 'All companies processed', 'completed': True}), 200
        
        # Process batch with Apollo.io
        enriched_companies = []
        current_company_name = ''  # Track the last company being processed
        for idx, company in enumerate(batch_companies):
            company_name = company.get('company_name', '')
            current_company_name = company_name  # Store for response
            website = company.get('website', '')
            place_id = company.get('place_id', '')
            print(f"  📊 Processing company {start_idx + idx + 1}/{len(companies)}: {company_name}")
            
            # Search for contacts using Apollo.io
            people = apollo_client.search_people_by_company(company_name, website)

            # Company metrics
            total_employees = apollo_client.get_company_total_employees(company_name, website) or ''
            active_members = len(people or [])
            active_members_with_email = sum(1 for p in (people or []) if p.get('email'))

            # Best-effort persist metrics back to Supabase (level1_companies)
            if place_id:
                get_supabase_client().update_level1_company_metrics(
                    project_name=project_name,
                    place_id=place_id,
                    total_employees=total_employees,
                    active_members=active_members,
                    active_members_with_email=active_members_with_email,
                )
            
            # Build enriched company object
            enriched_company = {
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
                'founders': [p for p in people if p.get('title') and any(keyword.lower() in p.get('title', '').lower() 
                                                           for keyword in ['founder', 'owner', 'ceo', 'co-founder', 'founder/owner'])],
                'hr_contacts': [p for p in people if p.get('title') and any(keyword.lower() in p.get('title', '').lower() 
                                                              for keyword in ['hr', 'human resources', 'recruiter', 'talent', 'human resource'])]
            }
            enriched_companies.append(enriched_company)
        
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
        print(f"  ✅ Batch {batch_number} complete: {len(batch_companies)} companies, {total_contacts} contacts found")
        
        return jsonify({
            'success': True,
            'batch_number': batch_number,
            'batch_size': len(batch_companies),
            'total_companies': len(companies),
            'processed': start_idx + len(batch_companies),
            'remaining': len(companies) - (start_idx + len(batch_companies)),
            'completed': end_idx >= len(companies),
            'contacts_found': total_contacts,
            'current_company': current_company_name  # For progress display
        }), 200
        
    except Exception as e:
        print(f"Error in Level 2 processing: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

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
    Enrich phone numbers for multiple contacts in parallel (lazy loading)
    Accepts list of contact IDs or emails and returns phone numbers
    """
    try:
        data = request.json or {}
        contact_ids = data.get('contact_ids', [])
        contact_emails = data.get('contact_emails', [])
        
        if not contact_ids and not contact_emails:
            return jsonify({'error': 'contact_ids or contact_emails required'}), 400
        
        # Get contacts from database
        supabase = get_supabase_client()
        contacts = []
        
        if contact_ids:
            contacts = supabase.get_level2_contacts_by_ids(contact_ids)
        elif contact_emails:
            # Get contacts by email
            try:
                response = supabase.client.table('level2_contacts').select('*').in_('email', contact_emails).execute()
                contacts = response.data if response.data else []
            except Exception as e:
                print(f"Error fetching contacts by email: {str(e)}")
                contacts = []
        
        if not contacts:
            return jsonify({'success': True, 'phones': {}}), 200
        
        # Extract Apollo person IDs from contacts (if available)
        # Or use email/name to search Apollo
        phone_results = {}
        
        # Use threading to make parallel requests
        import concurrent.futures
        import threading
        
        def enrich_single_contact(contact):
            """Enrich a single contact's phone number"""
            contact_id = contact.get('id')
            email = contact.get('email', '')
            name = contact.get('contact_name', '') or contact.get('name', '')
            
            if not email:
                return contact_id, None
            
            try:
                # Try to find person in Apollo by email
                # This is a simplified version - you might need to adjust based on Apollo API
                person_id = None
                
                # If we have Apollo person ID stored, use it
                # Otherwise, search by email
                if person_id:
                    enriched = apollo_client.enrich_single_person(person_id)
                    if enriched and enriched.get('phone'):
                        return contact_id, enriched.get('phone')
                
                # Alternative: Use webhook approach (already implemented)
                # Phone will come via webhook
                return contact_id, None
                
            except Exception as e:
                print(f"Error enriching contact {contact_id}: {str(e)}")
                return contact_id, None
        
        # Make parallel requests (limit to 10 at a time to avoid rate limits)
        phone_results = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_contact = {executor.submit(enrich_single_contact, contact): contact for contact in contacts[:20]}
            
            for future in concurrent.futures.as_completed(future_to_contact):
                contact_id, phone = future.result()
                if phone:
                    phone_results[contact_id] = phone
        
        return jsonify({
            'success': True,
            'phones': phone_results,
            'count': len(phone_results)
        }), 200
        
    except Exception as e:
        print(f"Error enriching phones in parallel: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

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
    """Level 3: Transfer contacts from Supabase to Apollo.io dashboard"""
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
    """Create a list in Apollo.io and return list_id"""
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
    """Transfer a single contact to Apollo with dedupe + list add"""
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

        # Duplicate check
        dup = apollo_client.find_contact_by_email(contact_data.get('email', ''))
        if dup.get('exists'):
            return jsonify({
                'success': True,
                'status': 'skipped',
                'reason': 'Duplicate email in Apollo',
                'contact': contact_name
            }), 200

        # Create contact in Apollo
        result = apollo_client.create_contact(contact_data)
        if not result.get('success'):
            return jsonify({
                'success': False,
                'status': 'failed',
                'reason': result.get('error', 'Apollo error'),
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
    """Export Level 1 company data to Excel file (Google Places only - no contacts)"""
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
    Webhook endpoint to receive phone numbers from Apollo.io
    Apollo sends phone numbers via webhook after enrichment request
    """
    try:
        data = request.json or {}
        
        # Apollo webhook payload structure
        person = data.get('person', {}) or data.get('data', {}).get('person', {})
        if not person:
            print("⚠️  Apollo webhook: No person data in payload")
            return jsonify({'success': False, 'error': 'No person data'}), 400
        
        person_id = person.get('id') or data.get('person_id')
        email = person.get('email', '')
        phone_numbers = person.get('phone_numbers', [])
        
        print(f"📞 Apollo webhook received for person_id: {person_id}, email: {email}")
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
        print(f"❌ Error processing Apollo webhook: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

# Vercel serverless handler (required for Vercel Python runtime)
# Vercel expects the app to be directly callable
# The @vercel/python builder automatically wraps Flask apps

if __name__ == '__main__':
    Config.validate()
    port = int(os.getenv('PORT', 5002))
    app.run(debug=False, host='0.0.0.0', port=port)

