"""
Quick script to check what's in Supabase
"""
from supabase_client import SupabaseClient
from config import Config
import json

def check_supabase():
    try:
        print("🔍 Checking Supabase database...\n")
        
        # Initialize client
        client = SupabaseClient()
        
        # Check all projects
        print("=" * 60)
        print("1. ALL PROJECTS IN DATABASE:")
        print("=" * 60)
        projects = client.get_projects_list()
        print(f"Found {len(projects)} projects:\n")
        for p in projects:
            print(f"  • {p.get('project_name')} ({p.get('company_count', 0)} companies)")
            print(f"    Industry: {p.get('industry', 'N/A')}")
            print(f"    PIN Codes: {p.get('pin_codes', 'N/A')}")
            print(f"    Date: {p.get('search_date', 'N/A')}\n")
        
        # Check for "haryana" specifically (case insensitive)
        print("=" * 60)
        print("2. SEARCHING FOR 'HARYANA' PROJECT (case insensitive):")
        print("=" * 60)
        from supabase import create_client
        supabase = create_client(Config.SUPABASE_URL, Config.SUPABASE_SERVICE_ROLE_KEY)
        
        # Search for haryana in project names
        response = supabase.table('level1_companies').select('project_name, company_name, created_at').execute()
        
        haryana_projects = {}
        for record in response.data:
            project_name = record.get('project_name', '').lower()
            if 'haryana' in project_name:
                if project_name not in haryana_projects:
                    haryana_projects[project_name] = []
                haryana_projects[project_name].append(record)
        
        if haryana_projects:
            print(f"Found {len(haryana_projects)} Haryana project(s):\n")
            for proj_name, records in haryana_projects.items():
                print(f"  • Project: '{proj_name}' ({len(records)} companies)")
                print(f"    First company: {records[0].get('company_name', 'N/A')}")
                print(f"    Created: {records[0].get('created_at', 'N/A')}\n")
        else:
            print("❌ No projects with 'haryana' in the name found\n")
        
        # Check all unique project names
        print("=" * 60)
        print("3. ALL UNIQUE PROJECT NAMES IN DATABASE:")
        print("=" * 60)
        all_projects = {}
        for record in response.data:
            proj_name = record.get('project_name', '').strip()
            if proj_name:
                if proj_name not in all_projects:
                    all_projects[proj_name] = 0
                all_projects[proj_name] += 1
        
        print(f"Found {len(all_projects)} unique project names:\n")
        for proj_name, count in sorted(all_projects.items()):
            print(f"  • '{proj_name}' ({count} companies)")
        
        # Check total records
        print("\n" + "=" * 60)
        print(f"4. TOTAL RECORDS IN level1_companies: {len(response.data)}")
        print("=" * 60)
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    check_supabase()



