# Employee Count Feature Investigation

## Overview
The employee count feature displays the total number of employees for each company and allows filtering companies by employee size ranges.

## How It Works

### 1. Data Source
Employee count is fetched from **Apollo.io API** using the `get_company_total_employees()` method in `apollo_client.py`.

**Location**: `apollo_client.py` lines 181-236

**Process**:
- Searches Apollo.io organizations database by:
  1. Company domain (most accurate)
  2. Company name (fallback)
- Extracts employee count from multiple possible fields:
  - `estimated_num_employees`
  - `num_employees`
  - `employee_count`
  - `employees`
  - `organization_num_employees`
  - `employees_count`
  - `estimated_num_employees_range`
  - `num_employees_range`
  - `employee_range`

### 2. When Employee Count is Fetched

**Level 2 Processing** (`app.py` lines 800-834):
- When processing companies for contact enrichment
- If employee range filter is selected AND company doesn't have employee data
- Fetches employee count for companies missing this data
- Updates the database for future use

**Level 2 Contact Enrichment** (`app.py` lines 902-903):
- When enriching individual companies with contacts
- Fetches employee count as part of company metrics

### 3. Data Storage

**Database Fields**:
- `level1_companies.total_employees` - Stores employee count for Level 1 companies
- `level2_contacts.company_total_employees` - Stores employee count in contact records

**Location**: `supabase_schema.sql` lines 41, 82, 94

### 4. Display in UI

**Level 2 Page** (`templates/level2.html`):

1. **Total Employees Stat** (line 1023):
   - Shows sum of all unique company employee counts
   - Calculated from contacts data
   - Format: `totalEmployees.toLocaleString()` (e.g., "1,660 employees")

2. **Per-Company Display** (lines 1739-1740):
   - Shows employee count next to company name
   - Format: `• {count} employees` (e.g., "• 710 employees")
   - Only displays if count > 0

3. **Employee Count Parsing** (lines 1674-1705):
   - Handles multiple formats:
     - Numbers: Direct use
     - Strings with ranges: "50-100" → takes first number (50)
     - Strings with "+": "500+" → takes number (500)
     - Strings with commas: "1,000" → removes commas
   - Sanity check: Max 10,000,000 employees

### 5. Filtering by Employee Range

**Filter Function** (`app.py` lines 52-145):
- `filter_companies_by_employee_range()` filters companies by selected ranges
- Supports multiple range selection
- Range options:
  - 1-10
  - 10-50
  - 50-100
  - 100-250
  - 250-500
  - 500-1000
  - 1000-5000
  - 5000+

**Range Matching Logic**:
- Parses employee count string (handles ranges, "+", commas)
- Checks if count falls within any selected range
- Companies without employee data are skipped when filtering

**UI Controls** (`templates/level2.html` lines 945-982):
- Checkbox-based multi-select
- "All Company Sizes" option (default)
- Individual range checkboxes

## Data Flow

```
1. User selects companies in Level 1
   ↓
2. User goes to Level 2 and selects employee range filter
   ↓
3. System checks which companies have employee data
   ↓
4. For companies without data:
   - Calls Apollo.io API (get_company_total_employees)
   - Extracts employee count from response
   - Updates database
   ↓
5. Filter companies by selected employee ranges
   ↓
6. Display filtered companies with employee counts
   ↓
7. Calculate and display total employees stat
```

## Current Implementation Details

### Strengths
✅ Fetches employee data on-demand (only when needed)
✅ Caches employee data in database for future use
✅ Handles multiple data formats from Apollo.io
✅ Supports filtering by multiple employee ranges
✅ Gracefully handles missing data
✅ Displays employee count per company and total

### Potential Issues

1. **API Rate Limits**: 
   - Fetches employee count one-by-one for each company
   - Could hit Apollo.io rate limits with many companies
   - **Location**: `app.py` line 807-832 (sequential fetching)

2. **Data Format Inconsistency**:
   - Apollo.io may return different formats (number, string, range)
   - Parsing logic handles this but may miss edge cases
   - **Location**: `apollo_client.py` lines 147-179

3. **Missing Data Handling**:
   - Companies without employee data are skipped in filtering
   - No retry mechanism if Apollo.io API fails
   - **Location**: `app.py` lines 828-832

4. **Display Logic**:
   - Employee count shown per company in contact list
   - Total employees calculated from unique companies
   - May show incorrect totals if same company appears multiple times
   - **Location**: `templates/level2.html` lines 1670-1736

## Recommendations

### 1. Batch API Calls
- Fetch employee counts in batches to reduce API calls
- Use Apollo.io batch endpoints if available

### 2. Caching Strategy
- Cache employee counts more aggressively
- Check cache before making API calls

### 3. Error Handling
- Add retry logic for failed API calls
- Show user-friendly messages when data unavailable

### 4. Data Validation
- Validate employee count data before storing
- Handle edge cases in parsing logic

### 5. Performance
- Consider parallel API calls (with rate limit protection)
- Pre-fetch employee data during Level 1 search

## Files Involved

1. **`apollo_client.py`** (lines 147-236)
   - Employee count extraction and API calls

2. **`app.py`** (lines 52-145, 800-860, 902-903)
   - Filtering logic and employee data fetching

3. **`templates/level2.html`** (lines 945-982, 1023-1024, 1670-1740)
   - UI display and calculation

4. **`supabase_client.py`** (lines 615-629, 869)
   - Database storage and retrieval

5. **`supabase_schema.sql`** (lines 41, 82, 94)
   - Database schema definitions

## Testing

To test the employee count feature:

1. **Test Data Fetching**:
   ```python
   from apollo_client import ApolloClient
   client = ApolloClient()
   count = client.get_company_total_employees("Beekay Steel Industries Limited", "beekaysteel.com")
   print(count)  # Should return employee count
   ```

2. **Test Filtering**:
   - Select companies in Level 1
   - Go to Level 2
   - Select employee range filter (e.g., "500-1000")
   - Verify only companies in that range are shown

3. **Test Display**:
   - Check that employee counts appear next to company names
   - Verify total employees stat is calculated correctly
   - Test with companies that have no employee data

## Example Output

Based on the image provided:
- **Beekay Steel Industries Limited**: 710 employees
- **Electrosteel Steels Limited**: 950 employees

These counts are fetched from Apollo.io and displayed next to the company name in the format: `• {count} employees`
