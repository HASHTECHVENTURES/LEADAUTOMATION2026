# Business Outreach Automation

A web application that helps you find companies and their key contacts (Founders, HR, etc.) using PIN code and location data from Google Places API, enriched with contact information from Apollo.io.

## Features

- 🔍 Search companies by PIN code and State (India)
- 🏢 Get company details: name, website, phone, address, industry
- 👥 Find key contacts: Founders, HR, Owners with emails and phone numbers
  - **Multi-strategy contact discovery:**
    - Strategy 1: Apollo.io database search (by domain)
    - Strategy 2: Apollo.io search by company name
    - Strategy 3: Web scraping fallback (extracts contacts from company websites)
- 📊 Export results to CSV
- 🎨 Modern, responsive UI
- 🔎 Contact source tracking (Apollo vs Web Scraped)

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Environment Variables

The API keys are already configured in the code. If you need to change them, update `config.py` or create a `.env` file:

```
GOOGLE_PLACES_API_KEY=your_key_here
APOLLO_API_KEY=your_key_here
```

### 3. Run the Application

```bash
python app.py
```

The application will be available at `http://localhost:5001`

## Usage

1. Enter a 6-digit PIN code
2. Select the state from the dropdown
3. (Optional) Enter an industry keyword
4. Click "Search Companies"
5. View results with company details and contacts
6. Export to CSV if needed

## API Endpoints

- `GET /` - Main page
- `POST /api/search` - Search companies by PIN code, state, and industry
- `POST /api/export` - Export search results to CSV format

## Next Steps (Future Enhancements)

- WhatsApp automation integration
- Email automation integration
- Outreach campaign management
- Scheduled searches
- Bulk import/export

## Technologies Used

- Flask (Python web framework)
- Google Places API
- Apollo.io API
- BeautifulSoup4 (Web scraping)
- HTML/CSS/JavaScript (Frontend)

## How Contact Discovery Works

The system uses a **4-strategy approach** to find contacts:

1. **NEW: Apollo.io API Search (FREE)** - Uses the new `/api/v1/mixed_people/api_search` endpoint:
   - **FREE search** (no credits consumed for searching)
   - Finds people by domain, job titles, and seniority
   - Then enriches results to get emails/phones (costs credits only for enrichment)
   - More efficient and cost-effective

2. **Apollo.io Domain Search (Fallback)** - Uses the older endpoint if new one fails:
   - Searches Apollo's database using company website domain
   - Returns contacts with emails/phones directly (uses credits)

3. **Apollo.io Company Name Search** - If domain search fails:
   - Searches by company name as alternative method

4. **Web Scraping Fallback** - If Apollo doesn't have the company:
   - Scrapes the company website to extract:
     - Email addresses from contact pages
     - Phone numbers
     - Names and titles from team/about pages

This ensures maximum contact discovery even when companies aren't in Apollo's database, while optimizing API credit usage.

