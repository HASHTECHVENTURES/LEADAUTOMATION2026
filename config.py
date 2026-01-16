import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Google Places API
    GOOGLE_PLACES_API_KEY = os.getenv('GOOGLE_PLACES_API_KEY', 'AIzaSyCoswhxLIQDt1LwthoYInHKDnLsMyBbHbM')
    
    # Apollo API (Master Key)
    APOLLO_API_KEY = os.getenv('APOLLO_API_KEY', 'lpLP_qGLdPOXeHgp6yNBKg')
    
    # Flask settings
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    
    # Authentication settings (for login)
    LOGIN_USERNAME = os.getenv('LOGIN_USERNAME', 'admin')
    LOGIN_PASSWORD = os.getenv('LOGIN_PASSWORD', 'admin123')
    
    # Google Sheets settings
    GOOGLE_SHEETS_CREDENTIALS_PATH = os.getenv('GOOGLE_SHEETS_CREDENTIALS_PATH', 'google_sheets_credentials.json')
    GOOGLE_SHEET_ID = os.getenv('GOOGLE_SHEET_ID', '1InHN8G1yLOE5YBiUJiIM58QMhGioqsiNgbO7Sa4To-Y')  # Your Google Sheet ID

    # Supabase settings (recommended backend DB)
    SUPABASE_URL = os.getenv('SUPABASE_URL', 'https://wxlcehpfchasdhitkiyg.supabase.co')
    # Use SERVICE ROLE key on backend (server-side only). Never expose this to frontend.
    SUPABASE_SERVICE_ROLE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Ind4bGNlaHBmY2hhc2RoaXRraXlnIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2ODUzNDAwNywiZXhwIjoyMDg0MTEwMDA3fQ.0k7avOBaGkmr1AYqXMw6yH8q26vaaeDC9l-fAZuSXSw')
    # Optional: if you prefer anon key locally (less permissions)
    SUPABASE_ANON_KEY = os.getenv('SUPABASE_ANON_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Ind4bGNlaHBmY2hhc2RoaXRraXlnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Njg1MzQwMDcsImV4cCI6MjA4NDExMDAwN30.ribA_l7HxZNSSLqvAbsHzNgdVTTWMB_YLtcnV-g7NBo')
    DB_BACKEND = os.getenv('DB_BACKEND', 'supabase')  # Only supabase now (Google Sheets removed)
    
    @classmethod
    def validate(cls):
        """Validate that all required config is present"""
        required = ['GOOGLE_PLACES_API_KEY', 'APOLLO_API_KEY']
        missing = [key for key in required if not getattr(cls, key)]
        if missing:
            raise ValueError(f"Missing required config: {', '.join(missing)}")

