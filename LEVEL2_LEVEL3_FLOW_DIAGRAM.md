# Level 2 & Level 3 Data Flow Diagram

## 🔴 CURRENT FLOW (PROBLEMATIC)

```
┌─────────────────────────────────────────────────────────────────┐
│ LEVEL 2: PROCESSING                                             │
└─────────────────────────────────────────────────────────────────┘

User Input: "CEO, DIRECTOR"
    │
    ▼
Frontend: userDesignation = "CEO, DIRECTOR"
    │
    ▼
POST /api/level2/process
{
  designation: "CEO, DIRECTOR",
  project_name: "Kerala IT"
}
    │
    ▼
Backend: Parse & Expand Designation
"CEO, DIRECTOR" → ["CEO", "Director", "Directors", "Managing Director", ...]
    │
    ▼
For Each Company:
    │
    ├─► Apollo Search with expanded titles
    │   Returns: [CEO contacts, Director contacts, Employee contacts, HR contacts]
    │   ⚠️ PROBLEM: Returns ALL contacts matching titles (may include extras)
    │
    └─► Save ALL contacts to database
        │
        ├─► title: "CEO" or "Director" or "Employee" (from Apollo)
        ├─► contact_type: "Founder/Owner" or "Employee" (categorized)
        └─► batch_name: "Kerala IT_Main_Batch"
    
    ⚠️ CRITICAL ISSUE: ALL contacts saved, not filtered by designation!

    ▼
After Processing Complete:
    │
    ▼
GET /api/level2/contacts?designation=CEO,DIRECTOR
    │
    ▼
Backend: get_contacts_for_level3(designation="CEO, DIRECTOR")
    │
    ├─► Query database: SELECT * WHERE project_name = "Kerala IT"
    ├─► Filter by designation (check title field)
    └─► Return filtered contacts (e.g., 62 contacts)
    
    ▼
Frontend: renderContacts()
    │
    ├─► Filter AGAIN by userDesignation (redundant!)
    └─► Display: 62 contacts
        ⚠️ DOUBLE FILTERING!


┌─────────────────────────────────────────────────────────────────┐
│ LEVEL 3: DISPLAY                                                │
└─────────────────────────────────────────────────────────────────┘

User Selects Batch: "Kerala IT_Main_Batch"
    │
    ▼
GET /api/level3/contacts?batch_name=Kerala IT_Main_Batch
    │
    ⚠️ NO DESIGNATION PARAMETER!
    │
    ▼
Backend: get_contacts_for_level3(batch_name="...", designation=None)
    │
    ├─► Query database: SELECT * WHERE batch_name = "Kerala IT_Main_Batch"
    ├─► Gets ALL contacts in batch (no filter!)
    └─► Returns: 63 contacts (includes Employees, HR, etc.)
    
    ▼
Frontend: Display ALL contacts
    │
    ├─► Shows "Employee" if title is empty (uses contact_type)
    └─► Shows all contacts regardless of designation
        ⚠️ WRONG DATA DISPLAYED!


┌─────────────────────────────────────────────────────────────────┐
│ PROBLEMS SUMMARY                                                 │
└─────────────────────────────────────────────────────────────────┘

1. ❌ ALL contacts saved to database (not filtered)
2. ❌ Designation not stored with batch
3. ❌ Level 3 doesn't pass designation
4. ❌ Level 3 shows ALL contacts (not filtered)
5. ❌ Shows "Employee" instead of actual titles
6. ❌ Double filtering in Level 2 (redundant)
7. ❌ Data inconsistency (62 vs 63 contacts)
```

---

## ✅ PROPOSED FLOW (SOLUTION)

### Option A: Filter at Save Time (Simplest)

```
┌─────────────────────────────────────────────────────────────────┐
│ LEVEL 2: PROCESSING (FIXED)                                     │
└─────────────────────────────────────────────────────────────────┘

User Input: "CEO, DIRECTOR"
    │
    ▼
POST /api/level2/process {designation: "CEO, DIRECTOR"}
    │
    ▼
Backend: Parse & Expand Designation
    │
    ▼
For Each Company:
    │
    ├─► Apollo Search with expanded titles
    │   Returns: [CEO contacts, Director contacts, Employee contacts]
    │
    └─► FILTER contacts by designation BEFORE saving
        │
        ├─► Keep only contacts matching "CEO" or "Director"
        └─► Discard "Employee" contacts that don't match
            ✅ FIX: Only matching contacts saved!
    
    ▼
Save FILTERED contacts to database
    │
    ├─► title: "CEO" or "Director" (actual titles)
    ├─► contact_type: "Founder/Owner" or "Executive"
    └─► batch_name: "Kerala IT_Main_Batch"
    
    ✅ Database only contains relevant contacts!

    ▼
GET /api/level2/contacts?designation=CEO,DIRECTOR
    │
    ▼
Backend: Returns filtered contacts (already filtered at save time)
    │
    ▼
Frontend: Display contacts (no filtering needed)
    │
    └─► Display: 62 contacts (correct!)


┌─────────────────────────────────────────────────────────────────┐
│ LEVEL 3: DISPLAY (FIXED)                                        │
└─────────────────────────────────────────────────────────────────┘

User Selects Batch: "Kerala IT_Main_Batch"
    │
    ▼
GET /api/level3/contacts?batch_name=Kerala IT_Main_Batch
    │
    ▼
Backend: get_contacts_for_level3(batch_name="...")
    │
    ├─► Query database: SELECT * WHERE batch_name = "..."
    └─► Returns: 62 contacts (already filtered at save time!)
        ✅ CORRECT DATA!
    
    ▼
Frontend: Display contacts
    │
    ├─► Shows actual titles: "CEO", "Director"
    └─► Shows correct count: 62 contacts
        ✅ CORRECT DISPLAY!
```

---

### Option B: Store Designation, Filter at Read Time

```
┌─────────────────────────────────────────────────────────────────┐
│ LEVEL 2: PROCESSING (ALTERNATIVE)                               │
└─────────────────────────────────────────────────────────────────┘

User Input: "CEO, DIRECTOR"
    │
    ▼
Process companies (same as before)
    │
    ▼
Save ALL contacts + Store designation metadata
    │
    ├─► Save contacts to database
    ├─► Store designation in batch metadata OR
    └─► Add designation column to level2_contacts table
        ✅ Designation stored for later use!


┌─────────────────────────────────────────────────────────────────┐
│ LEVEL 3: DISPLAY (ALTERNATIVE)                                  │
└─────────────────────────────────────────────────────────────────┘

User Selects Batch: "Kerala IT_Main_Batch"
    │
    ▼
GET /api/level3/contacts?batch_name=Kerala IT_Main_Batch
    │
    ▼
Backend: get_contacts_for_level3(batch_name="...")
    │
    ├─► Get stored designation from batch metadata
    ├─► Query database: SELECT * WHERE batch_name = "..."
    ├─► Filter by stored designation
    └─► Return filtered contacts
        ✅ Uses stored designation!
```

---

## 🎯 RECOMMENDED SOLUTION

### **Option A: Filter at Save Time** (Recommended)

**Why:**
- Simplest implementation
- Database only contains relevant data
- Level 3 automatically works correctly
- No need to pass designation between levels
- More efficient (less data in database)

**Implementation:**
1. Filter contacts in `app.py` before calling `save_level2_results()`
2. Only save contacts matching user's designation
3. Level 3 automatically gets filtered contacts

**Code Change Location:**
- `app.py` line 1431: Filter `enriched_companies` before saving

---

## 📊 COMPARISON TABLE

| Aspect | Current | Option A (Filter at Save) | Option B (Store Designation) |
|--------|---------|---------------------------|------------------------------|
| **Complexity** | High (double filtering) | Low (single filter point) | Medium (store + filter) |
| **Database Size** | Large (all contacts) | Small (filtered only) | Large (all contacts) |
| **Level 3 Filtering** | Manual (doesn't work) | Automatic | Automatic |
| **Flexibility** | Low | Low (need re-process) | High (can re-filter) |
| **Implementation** | Complex | Simple | Medium |
| **Apollo Credits** | Wasted (saves all) | Efficient (saves filtered) | Wasted (saves all) |

---

## 🔧 SPECIFIC CODE CHANGES NEEDED

### Change 1: Filter Before Save (Option A)
**File:** `app.py` line 1431
**Before:**
```python
save_result = get_supabase_client().save_level2_results(
    enriched_companies,  # Contains ALL contacts
    project_name=project_name,
    batch_name=default_batch_name
)
```

**After:**
```python
# Filter contacts by designation BEFORE saving
if designation and designation.strip():
    user_titles = [t.strip().lower() for t in designation.split(',') if t.strip()]
    for company in enriched_companies:
        filtered_people = []
        for person in company.get('people', []):
            person_title = (person.get('title', '') or '').lower()
            if any(user_title in person_title for user_title in user_titles):
                filtered_people.append(person)
        company['people'] = filtered_people

save_result = get_supabase_client().save_level2_results(
    enriched_companies,  # Now contains ONLY filtered contacts
    project_name=project_name,
    batch_name=default_batch_name
)
```

### Change 2: Remove Frontend Filtering (Simplify)
**File:** `templates/level2.html` line 1735
**Before:**
```javascript
const filtered = contacts.filter(c => {
    // Frontend filtering (redundant!)
    if (filterTitles.length > 0) {
        const matchesFilter = filterTitles.some(...);
        if (!matchesFilter) return false;
    }
    // ...
});
```

**After:**
```javascript
// Backend already filtered, just display what we got
const filtered = contacts;  // No filtering needed
```

### Change 3: Ensure Title Display (Already Fixed)
**File:** `app.py` line 2110
**Status:** ✅ Fixed - Uses title first

**File:** `templates/level3.html` line 663
**Status:** ✅ Fixed - Uses title first

---

## ✅ VERIFICATION CHECKLIST

After implementing fixes, verify:

- [ ] Level 2: Only contacts matching designation are saved
- [ ] Level 2: Display shows correct count
- [ ] Level 3: Shows same contacts as Level 2
- [ ] Level 3: Shows actual job titles (not "Employee")
- [ ] Level 3: Contact count matches Level 2
- [ ] No double filtering
- [ ] Apollo credits used efficiently

---

**End of Flow Diagram**
