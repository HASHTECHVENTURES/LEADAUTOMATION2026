# 3-Level Business Outreach Automation System

## Overview

This system is divided into 3 levels to optimize performance and reduce server load:

### Level 1: Company Search
- **Purpose**: Search for companies using Google Places API
- **Input**: PIN code, State, Industry
- **Output**: Company list saved to Google Sheets
- **Features**: Fast search, Excel export, Google Sheets integration

### Level 2: Contact Enrichment
- **Purpose**: Enrich companies with HR, Founder, Owner contacts
- **Input**: Companies from Google Sheets (Level 1)
- **Output**: Enriched contacts saved to Google Sheets
- **Features**: Apollo.io integration, batch processing (10 companies per batch), processes up to 50 companies

### Level 3: Transfer to Apollo.io
- **Purpose**: Transfer contacts to Apollo.io dashboard for email marketing
- **Input**: Contacts from Google Sheets (Level 2)
- **Output**: Contacts transferred to Apollo.io
- **Features**: Direct API transfer, ready for email campaigns

## Setup Instructions

### 1. Google Sheets Setup

1. **Get your Google Sheet ID**:
   - Open your Google Sheet
   - URL looks like: `https://docs.google.com/spreadsheets/d/SHEET_ID_HERE/edit`
   - Copy the `SHEET_ID_HERE` part

2. **Share Sheet with Service Account**:
   - Click "Share" button in Google Sheet
   - Add email: `sheets-backend@sapient-office-483811-d3.iam.gserviceaccount.com`
   - Give "Editor" access
   - Click "Send"

3. **Set Sheet ID in Config**:
   - Add to `config.py`:
     ```python
     GOOGLE_SHEET_ID = 'your_sheet_id_here'
     ```
   - Or set environment variable:
     ```bash
     export GOOGLE_SHEET_ID=your_sheet_id_here
     ```

### 2. Install Dependencies

```bash
pip3 install -r requirements.txt
```

### 3. Run the Application

```bash
python3 app.py
```

Access at: `http://localhost:5002`

## Usage Flow

1. **Level 1**: 
   - Go to `/level1`
   - Enter PIN code, State, Industry
   - Select number of companies
   - Click "Search Companies"
   - Results saved to Google Sheets automatically

2. **Level 2**:
   - Go to `/level2`
   - Click "Start Processing Companies"
   - System reads from Google Sheets
   - Processes in batches of 10
   - Enriches with Apollo.io contacts
   - Saves back to Google Sheets

3. **Level 3**:
   - Go to `/level3`
   - Click "Transfer Contacts to Apollo.io"
   - System reads contacts from Google Sheets
   - Transfers to Apollo.io dashboard
   - Ready for email marketing!

## API Endpoints

- `GET /` - Main navigation page
- `GET /level1` - Level 1 search page
- `GET /level2` - Level 2 enrichment page
- `GET /level3` - Level 3 transfer page
- `POST /api/level1/search` - Level 1 search API
- `POST /api/level2/process` - Level 2 batch processing API
- `GET /api/level2/status` - Check Level 2 status
- `POST /api/level3/transfer` - Level 3 transfer API
- `GET /api/level3/status` - Check Level 3 status

## Google Sheets Structure

### Level1_Companies Worksheet
- Company Name, Website, Phone, Address, Industry, PIN Code, State, Search Date, Place ID, Business Status

### Level2_Contacts Worksheet
- Company Name, Address, Contact Name, Contact Type, Phone Number, LinkedIn Link, Email, Website, PIN Code, State, Industry, Search Date, Source

## Notes

- Level 1 is fast (Google Places only, no Apollo calls)
- Level 2 processes in batches to work with Vercel's 60-second limit
- Level 3 transfers data to Apollo.io for email marketing
- All data flows through Google Sheets as the central database





