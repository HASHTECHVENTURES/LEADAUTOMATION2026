# Employee Count - Bug Fixes

## Issues Found

### 1. ❌ WRONG: Using `active_members` as fallback
**Location**: `templates/level2.html` line 1723

**Problem**: 
```javascript
const employees = c.total_employees || c.active_members || '';
```

`active_members` = number of contacts found (e.g., 2 contacts)
`total_employees` = company size (e.g., 710 employees)

**Impact**: Could show "2 employees" instead of "710 employees" if `total_employees` is missing.

**Fix**: Removed `active_members` fallback - only use `total_employees`.

---

### 2. ❌ INCONSISTENT: Range parsing differs between backend and frontend

**Backend** (`app.py` line 98):
- "50-100" → midpoint = 75

**Frontend** (`level2.html` line 1689):
- "50-100" → first number = 50

**Impact**: 
- Backend filters using 75
- Frontend displays using 50
- Same company could show different values

**Fix**: Frontend now uses midpoint (consistent with backend).

---

## What Was Fixed

✅ Removed incorrect `active_members` fallback
✅ Made range parsing consistent (both use midpoint)
✅ Added comments explaining why

## Result

- Employee counts now display correctly
- Consistent parsing across backend and frontend
- No more confusion between contact count and company size
