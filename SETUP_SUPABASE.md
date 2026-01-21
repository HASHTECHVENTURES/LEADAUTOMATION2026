# Supabase Setup Guide

## 1. Create Database Tables

1. Go to your Supabase dashboard: https://wxlcehpfchasdhitkiyg.supabase.co
2. Navigate to **SQL Editor**
3. Copy and paste the contents of `supabase_schema.sql`
4. Click **Run** to create the tables

## 2. Get Your Service Role Key

**IMPORTANT**: For backend operations, you need the **Service Role Key** (not the publishable key).

1. In Supabase dashboard, go to **Settings** → **API**
2. Find **service_role** key (keep this secret!)
3. Add it to your `.env` file or `config.py`:

```bash
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key_here
```

Or update `config.py` directly:

```python
SUPABASE_SERVICE_ROLE_KEY = 'your_service_role_key_here'
```

## 3. Configure Backend

The app is already configured to use Supabase. Make sure:

1. `DB_BACKEND=supabase` in your `.env` or `config.py`
2. `SUPABASE_URL` is set (already configured)
3. `SUPABASE_SERVICE_ROLE_KEY` is set (get from Supabase dashboard)

## 4. Test the Connection

Run the app and check the console. You should see:
```
✅ Supabase client initialized successfully
✅ Using Supabase as backend database
```

## 5. Migration from Google Sheets

If you have existing data in Google Sheets:
- The app will continue using Google Sheets if Supabase is not configured
- To migrate data, you'll need to export from Google Sheets and import to Supabase
- Or keep both systems running temporarily

## Security Notes

- **Never expose** the Service Role Key to the frontend
- The Service Role Key has full database access
- Use Row Level Security (RLS) policies in Supabase for production




