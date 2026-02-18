# Level 2 & Level 3 Complete Investigation Report
**Date:** 2026-02-18  
**Purpose:** Full analysis of data flow, filtering logic, and issues

---

## 🔍 EXECUTIVE SUMMARY

### Current Problems Identified:
1. **"Employee" showing everywhere in Level 3** - contacts display "Employee" instead of actual job titles
2. **Designation filter not working in Level 3** - shows all contacts regardless of designation entered in Level 2
3. **Data inconsistency** - Level 2 shows 62 contacts, Level 3 shows 63 contacts
4. **Complex filtering logic** - filtering happens in multiple places (backend, frontend, database)

---

## 📊 LEVEL 2 - COMPLETE DATA FLOW

### Step 1: User Input (Frontend)
**File:** `templates/level2.html` (lines 2135-2140)
- User enters designation in `designationInput` field (e.g., "CEO, DIRECTOR")
- Stored in `userDesignation` variable
- Sent to backend via POST `/api/level2/process`

### Step 2: Backend Processing
**File:** `app.py` (lines 1122-1465)

**2.1 Initial Setup:**
- Receives `designation` parameter from frontend
- Gets selected companies from Supabase
- Filters by employee range (if specified)

**2.2 Company Processing Loop:**
- For each company (lines 1280-1360):
  - Parses designation and expands variations (lines 1293-1321)
    - "Director" → ["Director", "Directors", "Managing Director", etc.]
  - Searches Apollo with expanded titles
  - **CRITICAL:** Searches ALL contacts matching titles, then filters later

**2.3 Apollo Search:**
**File:** `apollo_client.py` (lines 751-830)
- Strategy 1: NEW api_search endpoint (FREE)
- Strategy 2: OLD domain search (fallback)
- Strategy 3: Company name search (if no website)
- **Returns:** ALL contacts matching the titles (not filtered yet)

**2.4 Saving to Database:**
**File:** `supabase_client.py` (lines 819-898)
- Saves ALL contacts returned from Apollo to `level2_contacts` table
- **Fields saved:**
  - `title`: Actual job title from Apollo (e.g., "CEO", "Director")
  - `contact_type`: Categorized type ("Founder/Owner", "HR", "Employee", "Executive")
- **Batch name:** `{project_name}_Main_Batch`

**ISSUE FOUND:** All contacts are saved, regardless of designation filter!

### Step 3: Frontend Display
**File:** `templates/level2.html` (lines 2264-2282)

**3.1 Fetching Contacts:**
- After processing completes, fetches contacts via GET `/api/level2/contacts`
- Passes `designation` parameter: `?designation=CEO,DIRECTOR`
- Backend filters contacts before returning

**3.2 Backend Filtering:**
**File:** `app.py` (lines 1812-1850)
- Calls `get_contacts_for_level3()` with designation
- Returns filtered contacts

**3.3 Frontend Filtering:**
**File:** `templates/level2.html` (lines 1720-1747)
- **DOUBLE FILTERING:** Frontend also filters contacts again!
- Uses `userDesignation` to filter displayed contacts
- This is redundant - backend already filtered

**ISSUE FOUND:** Double filtering happening (backend + frontend)

---

## 📊 LEVEL 3 - COMPLETE DATA FLOW

### Step 1: Batch Selection
**File:** `templates/level3.html` (lines 631-670)
- User selects batch from dropdown
- Calls GET `/api/level3/contacts?batch_name={batch_name}`
- **NO DESIGNATION PARAMETER PASSED!**

### Step 2: Backend Retrieval
**File:** `app.py` (lines 2091-2114)

**2.1 API Endpoint:**
- Receives `batch_name` parameter
- Optionally receives `designation` parameter (but Level 3 doesn't pass it!)
- Calls `get_contacts_for_level3(batch_name=batch_name, designation=None)`

**2.2 Database Query:**
**File:** `supabase_client.py` (lines 1080-1150)
- Queries `level2_contacts` table by `batch_name`
- Gets ALL contacts in that batch
- **If no designation provided:** Returns ALL contacts (line 1124)
- **If designation provided:** Filters by title matching

**ISSUE FOUND:** Level 3 doesn't pass designation, so it gets ALL contacts!

### Step 3: Title Display
**File:** `app.py` (line 2110)
- Returns: `'title': c.get('title', '') or c.get('contact_type', '')`
- **FIXED:** Now uses title first, contact_type as fallback

**File:** `templates/level3.html` (line 663)
- Displays: `c.title || c.contact_type || 'No Title'`
- **FIXED:** Now uses title first

---

## 🔴 CRITICAL ISSUES IDENTIFIED

### Issue 1: Designation Filter Not Persisted
**Problem:**
- User enters "CEO, DIRECTOR" in Level 2
- Contacts are saved to database WITHOUT filtering
- ALL contacts saved (including Employees, HR, etc.)
- Level 3 loads batch → Gets ALL contacts (no filter applied)

**Root Cause:**
- Designation is used for Apollo search (finds matching contacts)
- But ALL returned contacts are saved to database
- Designation is NOT stored with the batch
- Level 3 doesn't know what designation was used

**Impact:**
- Wastes Apollo credits (searches for specific titles but saves all)
- Level 3 shows wrong contacts
- User sees "Employee" contacts they didn't want

### Issue 2: Double Filtering
**Problem:**
- Backend filters contacts when fetching for Level 2 display
- Frontend filters again before displaying
- Redundant filtering logic

**Root Cause:**
- Backend: `get_contacts_for_level3()` filters by designation
- Frontend: `renderContacts()` filters again by `userDesignation`

**Impact:**
- Unnecessary complexity
- Potential inconsistencies if filters differ

### Issue 3: Title vs Contact Type Confusion
**Problem:**
- `title` field: Actual job title from Apollo ("CEO", "Director", "HR Manager")
- `contact_type` field: Categorized type ("Founder/Owner", "HR", "Employee")
- Code sometimes uses `contact_type` instead of `title` for display

**Root Cause:**
- `contact_type` defaults to "Employee" if title doesn't match keywords
- Some code paths prioritize `contact_type` over `title`

**Impact:**
- Shows "Employee" instead of actual job titles
- Confusing for users

### Issue 4: No Designation Storage
**Problem:**
- Designation entered in Level 2 is not stored anywhere
- Cannot be retrieved in Level 3
- Each level needs to re-apply filter

**Root Cause:**
- No `designation` column in `level2_contacts` table
- No `designation` stored with batch metadata
- Designation only exists in frontend variable `userDesignation`

**Impact:**
- Level 3 cannot filter by original designation
- Must rely on database filtering (which doesn't work if no designation passed)

---

## 📋 DATA FLOW DIAGRAM

```
LEVEL 2 PROCESSING:
┌─────────────────────────────────────────────────────────┐
│ User enters "CEO, DIRECTOR"                            │
│ ↓                                                       │
│ POST /api/level2/process {designation: "CEO, DIRECTOR"}│
│ ↓                                                       │
│ Backend expands: ["CEO", "Director", "Directors", ...] │
│ ↓                                                       │
│ Apollo search with expanded titles                     │
│ ↓                                                       │
│ Returns ALL contacts matching titles                   │
│ ↓                                                       │
│ SAVE TO DATABASE (ALL contacts, no filter!)            │
│ - title: "CEO" or "Director" or "Employee"            │
│ - contact_type: "Founder/Owner" or "Employee"        │
│ ↓                                                       │
│ GET /api/level2/contacts?designation=CEO,DIRECTOR     │
│ ↓                                                       │
│ Backend filters by designation                         │
│ ↓                                                       │
│ Frontend filters again (redundant!)                    │
│ ↓                                                       │
│ Display filtered contacts                              │
└─────────────────────────────────────────────────────────┘

LEVEL 3 DISPLAY:
┌─────────────────────────────────────────────────────────┐
│ User selects batch                                      │
│ ↓                                                       │
│ GET /api/level3/contacts?batch_name={batch}           │
│ (NO designation parameter!)                           │
│ ↓                                                       │
│ Backend: get_contacts_for_level3(batch_name,           │
│          designation=None)                            │
│ ↓                                                       │
│ Returns ALL contacts in batch (no filter!)            │
│ ↓                                                       │
│ Frontend displays ALL contacts                         │
│ Shows "Employee" if title is empty                     │
└─────────────────────────────────────────────────────────┘
```

---

## 🎯 ROOT CAUSE ANALYSIS

### Why "Employee" Shows Everywhere:

1. **During Save (supabase_client.py line 859):**
   - Default `contact_type = 'Employee'`
   - Only changes if title matches specific keywords
   - Many contacts get saved with `contact_type = 'Employee'`

2. **During Display (level3.html line 663):**
   - Uses `c.title || c.contact_type`
   - If `title` is empty or missing → shows `contact_type` ("Employee")
   - **FIXED:** Now uses title first

3. **During Filtering (supabase_client.py line 1128):**
   - Old code: `title = (c.get('title', '') or c.get('contact_type', '')).lower()`
   - This prioritizes contact_type if title is empty
   - **FIXED:** Now checks title first

### Why Designation Filter Doesn't Work in Level 3:

1. **Designation Not Passed:**
   - Level 3 frontend doesn't pass designation parameter
   - Backend receives `designation=None`
   - Returns ALL contacts (line 1124)

2. **Designation Not Stored:**
   - No way to know what designation was used in Level 2
   - Cannot filter by original designation

3. **Batch Contains All Contacts:**
   - Batch saved with ALL contacts (not filtered)
   - Level 3 loads batch → gets all contacts

---

## 💡 PROPOSED SOLUTIONS (For Planning)

### Solution 1: Filter at Save Time (Recommended)
**Approach:** Filter contacts BEFORE saving to database

**Changes Needed:**
1. In `app.py` line 1431, filter contacts by designation BEFORE saving
2. Only save contacts matching user's designation
3. This ensures database only contains relevant contacts

**Pros:**
- Simple: One filter point
- Efficient: No redundant filtering
- Level 3 automatically gets filtered contacts

**Cons:**
- If user changes designation, need to re-process
- Cannot "unfilter" later

### Solution 2: Store Designation with Batch
**Approach:** Save designation as metadata with batch

**Changes Needed:**
1. Add `designation` column to `level2_contacts` table
2. Store designation when saving contacts
3. Level 3 can filter by stored designation

**Pros:**
- Flexible: Can filter differently later
- Historical record of what was searched

**Cons:**
- Database schema change required
- More complex queries

### Solution 3: Pass Designation to Level 3
**Approach:** Level 3 receives designation from Level 2

**Changes Needed:**
1. Store `userDesignation` in localStorage or URL parameter
2. Level 3 reads designation and passes to backend
3. Backend filters by designation

**Pros:**
- No database changes
- Works with existing batches

**Cons:**
- Requires frontend coordination
- Lost if user refreshes page

### Solution 4: Remove Double Filtering
**Approach:** Filter only in backend OR frontend, not both

**Recommended:** Filter only in backend
- Frontend just displays what backend returns
- Simpler, more consistent

---

## 📝 RECOMMENDED APPROACH

### Phase 1: Fix Immediate Issues
1. ✅ Fix title display (use title first, not contact_type)
2. ✅ Fix filtering logic (check title first)
3. ⚠️ Remove double filtering (choose one place)

### Phase 2: Fix Designation Persistence
**Option A (Simplest):** Filter at save time
- Filter contacts before saving to database
- Only save contacts matching designation
- Level 3 automatically gets filtered contacts

**Option B (More Flexible):** Store designation with batch
- Add designation column to database
- Store designation when saving
- Level 3 can filter by stored designation

### Phase 3: Simplify Architecture
1. Single source of truth for filtering (backend only)
2. Frontend just displays what backend returns
3. Remove redundant filtering logic

---

## 🔍 CODE LOCATIONS SUMMARY

### Level 2 Processing:
- **Entry:** `app.py` line 1122 (`/api/level2/process`)
- **Apollo Search:** `apollo_client.py` line 751 (`search_people_by_company`)
- **Save:** `supabase_client.py` line 819 (`save_level2_results`)
- **Fetch:** `app.py` line 1812 (`/api/level2/contacts`)
- **Filter:** `supabase_client.py` line 1080 (`get_contacts_for_level3`)

### Level 3 Display:
- **Entry:** `app.py` line 2091 (`/api/level3/contacts`)
- **Fetch:** `supabase_client.py` line 1080 (`get_contacts_for_level3`)
- **Display:** `templates/level3.html` line 631 (`loadBatch`)

### Key Data Fields:
- **title:** Actual job title from Apollo (e.g., "CEO", "Director")
- **contact_type:** Categorized type ("Founder/Owner", "HR", "Employee", "Executive")
- **batch_name:** Batch identifier (e.g., "Kerala IT_Main_Batch")
- **designation:** User's input (NOT STORED CURRENTLY)

---

## ⚠️ CURRENT STATE SUMMARY

### What Works:
- ✅ Level 2 processes companies correctly
- ✅ Apollo search finds contacts with correct titles
- ✅ Contacts saved to database with title field populated
- ✅ Level 2 display filters by designation correctly

### What Doesn't Work:
- ❌ Level 3 shows ALL contacts (not filtered by designation)
- ❌ Level 3 shows "Employee" instead of actual titles (partially fixed)
- ❌ Designation not persisted between Level 2 and Level 3
- ❌ Double filtering causing complexity

### Data Inconsistencies:
- Level 2 shows 62 contacts (filtered)
- Level 3 shows 63 contacts (unfiltered)
- Difference: Level 3 includes contacts that don't match designation

---

## 🎯 NEXT STEPS RECOMMENDATION

1. **Decide on filtering approach:**
   - Option A: Filter at save time (simpler)
   - Option B: Store designation and filter at read time (more flexible)

2. **Remove double filtering:**
   - Choose backend OR frontend filtering
   - Remove redundant filter logic

3. **Fix title display:**
   - Ensure all code paths use `title` first
   - Only use `contact_type` as fallback if title is empty

4. **Test thoroughly:**
   - Test with different designations
   - Verify Level 2 → Level 3 data consistency
   - Check Apollo credit usage

---

## 🔬 DETAILED CODE ANALYSIS

### Level 2: Where Filtering Should Happen

**Current Flow:**
1. User enters "CEO, DIRECTOR"
2. Backend expands to ["CEO", "Director", "Directors", ...]
3. Apollo searches with these titles
4. Apollo returns contacts (some match, some don't)
5. **ALL contacts saved to database** ← PROBLEM HERE
6. Later, when fetching for display, filter by designation ← REDUNDANT

**What Should Happen:**
1. User enters "CEO, DIRECTOR"
2. Backend expands titles
3. Apollo searches with these titles
4. Apollo returns contacts
5. **Filter contacts by designation BEFORE saving** ← FIX HERE
6. Only save matching contacts to database
7. Level 3 automatically gets filtered contacts

### Level 3: Why It Shows Wrong Data

**Current Flow:**
1. User selects batch "Kerala IT_Main_Batch"
2. Frontend calls: `/api/level3/contacts?batch_name=Kerala IT_Main_Batch`
3. Backend calls: `get_contacts_for_level3(batch_name="...", designation=None)`
4. Database query: `SELECT * FROM level2_contacts WHERE batch_name = '...'`
5. Returns ALL contacts in batch (no filter)
6. Frontend displays all contacts

**What Should Happen:**
1. User selects batch
2. Frontend calls with designation: `/api/level3/contacts?batch_name=...&designation=CEO,DIRECTOR`
3. Backend filters by designation
4. Returns only matching contacts
5. Frontend displays filtered contacts

**OR (Better Approach):**
1. Filter at save time (Solution 1)
2. Batch only contains filtered contacts
3. Level 3 automatically shows correct contacts

---

## 📊 DATA STRUCTURE ANALYSIS

### Database Schema (`level2_contacts` table):
```sql
- id: Primary key
- project_name: "Kerala IT"
- batch_name: "Kerala IT_Main_Batch"
- company_name: "STPI Kochi"
- contact_name: "Ajay Shrivastava"
- title: "Employee" ← ACTUAL TITLE FROM APOLLO (should be "CEO" or "Director")
- contact_type: "Employee" ← CATEGORIZED TYPE (for internal use)
- email: "ajay.shrivastava@stpi.in"
- phone_number: NULL
```

### Current Data Issues:
1. **title field:** Contains actual job title from Apollo
   - Should be: "CEO", "Director", "HR Manager", etc.
   - Sometimes empty or "Employee" (if Apollo doesn't provide title)

2. **contact_type field:** Categorized type
   - "Founder/Owner" - if title contains founder/owner/ceo
   - "HR" - if title contains hr/human resources
   - "Executive" - if title contains director/manager/vp
   - "Employee" - default (everything else)

3. **Problem:** Code sometimes uses `contact_type` for display instead of `title`

---

## 🎯 SPECIFIC CODE ISSUES

### Issue A: Filtering Happens Too Late
**Location:** `app.py` line 1431
```python
# Current: Saves ALL contacts
save_result = get_supabase_client().save_level2_results(
    enriched_companies,  # Contains ALL contacts from Apollo
    project_name=project_name,
    batch_name=default_batch_name
)
```

**Problem:** `enriched_companies` contains ALL contacts returned by Apollo, not filtered by designation.

**Fix Needed:** Filter `enriched_companies` before saving:
```python
# Filter contacts by designation before saving
if designation and designation.strip():
    user_titles = [t.strip().lower() for t in designation.split(',')]
    for company in enriched_companies:
        company['people'] = [
            p for p in company.get('people', [])
            if any(user_title in (p.get('title', '') or '').lower() 
                   for user_title in user_titles)
        ]
```

### Issue B: Level 3 Doesn't Know Designation
**Location:** `templates/level3.html` line 633
```javascript
// Current: No designation parameter
const res = await fetch(`/api/level3/contacts?batch_name=${encodeURIComponent(batchName)}`);
```

**Problem:** Level 3 doesn't pass designation, so backend can't filter.

**Fix Options:**
1. Store designation in localStorage when leaving Level 2
2. Store designation in URL parameter
3. Store designation in database (better long-term solution)

### Issue C: Double Filtering
**Location:** 
- Backend: `supabase_client.py` line 1126-1145
- Frontend: `templates/level2.html` line 1735-1743

**Problem:** Both backend and frontend filter contacts.

**Fix:** Remove frontend filtering, rely on backend only.

---

## 💡 RECOMMENDED SOLUTION ARCHITECTURE

### Option 1: Filter at Save Time (Simplest)
```
User enters "CEO, DIRECTOR"
    ↓
Apollo search with titles
    ↓
Filter contacts by designation BEFORE saving
    ↓
Save ONLY matching contacts to database
    ↓
Level 3 loads batch → Gets filtered contacts automatically
```

**Pros:**
- Simple: One filter point
- Efficient: Database only contains relevant data
- Level 3 works automatically

**Cons:**
- Cannot change filter later without re-processing
- If user wants different filter, need new batch

### Option 2: Store Designation, Filter at Read Time
```
User enters "CEO, DIRECTOR"
    ↓
Apollo search with titles
    ↓
Save ALL contacts + store designation with batch
    ↓
Level 3 loads batch → Filters by stored designation
```

**Pros:**
- Flexible: Can filter differently later
- Historical record

**Cons:**
- More complex: Need to store designation
- Database contains more data

### Option 3: Hybrid Approach (Recommended)
```
User enters "CEO, DIRECTOR"
    ↓
Apollo search with titles
    ↓
Filter contacts by designation BEFORE saving
    ↓
Save filtered contacts + store designation as metadata
    ↓
Level 3 loads batch → Gets filtered contacts
    ↓
If user wants different filter → Can re-filter from database
```

**Pros:**
- Best of both worlds
- Database contains filtered data (efficient)
- Can still re-filter if needed (flexible)

**Cons:**
- Most complex implementation

---

## 📋 IMPLEMENTATION CHECKLIST

### Phase 1: Fix Immediate Display Issues
- [x] Fix title display priority (title first, contact_type fallback)
- [x] Fix filtering logic (check title first)
- [ ] Remove double filtering (choose one place)

### Phase 2: Fix Designation Persistence
- [ ] Decide on approach (Filter at save vs Store designation)
- [ ] Implement chosen approach
- [ ] Test with different designations

### Phase 3: Simplify Architecture
- [ ] Remove redundant filtering
- [ ] Single source of truth for filtering
- [ ] Clean up code

### Phase 4: Testing
- [ ] Test Level 2 → Level 3 flow
- [ ] Verify designation filtering works
- [ ] Check Apollo credit usage
- [ ] Verify title display is correct

---

## 🔍 ADDITIONAL FINDINGS

### Apollo Search Behavior:
- Apollo's `api_search` endpoint searches by titles
- Returns contacts matching titles OR similar titles
- May return contacts that don't exactly match (due to `include_similar_titles: True`)
- This is why we get more contacts than expected

### Contact Type Categorization:
- Currently categorizes contacts into: Founder/Owner, HR, Executive, Employee
- This categorization is for internal use only
- Should NOT be used for display or filtering
- Only `title` field should be used for display

### Batch Naming:
- Default batch name: `{project_name}_Main_Batch`
- User can save batches with custom names
- Saved batches get prefix: `SAVED::{batch_name}`
- Batch name doesn't include designation info

---

**End of Investigation Report**
