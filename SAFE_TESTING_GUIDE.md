# Safe Testing Guide - Apollo.io Credit Usage

## ⚠️ IMPORTANT: Test with 1-2 Companies First!

Before processing 10 companies, **ALWAYS test with 1-2 companies first** to verify everything works correctly.

---

## 💰 Credit Usage Breakdown (Per Company)

### What Costs Credits:
1. **Employee Count Lookup**: ~1 credit per company (if not in database)
   - ✅ **OPTIMIZED**: Only 1 API call (was 3-4 before)
   - ✅ **SAVED**: Checks database first, skips if already fetched

2. **Contact Search**: **FREE** ✅
   - Uses `/api/v1/mixed_people/api_search` endpoint
   - **NO credits for searching!**

3. **Email Enrichment**: ~1 credit per contact with email
   - Only enriches contacts found in search
   - This is unavoidable (you need emails)

### Expected Credit Usage:

| Scenario | Credits Used |
|----------|--------------|
| **1 company** (10 contacts with emails) | ~11 credits |
| **2 companies** (20 contacts with emails) | ~22 credits |
| **10 companies** (100 contacts with emails) | ~110 credits |

**Note**: If employee counts are already in database, subtract 1 credit per company.

---

## ✅ Credit-Saving Optimizations (Already Implemented)

1. ✅ **Employee Count**: Only 1 API call (was 3-4)
2. ✅ **Contact Search**: FREE endpoint (no credits)
3. ✅ **Database Caching**: Reuses data from previous searches
4. ✅ **Smart Filtering**: Only fetches what's needed

---

## 🧪 Safe Testing Steps

### Step 1: Test with 1 Company
1. Go to Level 1, select **ONLY 1 company**
2. Go to Level 2, process that 1 company
3. **Check your Apollo.io dashboard** for credit usage
4. **Expected**: ~10-15 credits for 1 company

### Step 2: Verify Results
- ✅ Did you get contacts? (should be more than 1-2)
- ✅ Check console logs for "Credits used: ~X"
- ✅ Check Apollo.io dashboard for actual credit usage

### Step 3: If Successful, Test with 2 Companies
1. Select **2 companies** in Level 1
2. Process in Level 2
3. **Expected**: ~20-30 credits for 2 companies

### Step 4: Scale Up Gradually
- If 2 companies work well, try 5 companies
- Then 10 companies
- **Always monitor credit usage in Apollo.io dashboard!**

---

## 📊 How to Monitor Credit Usage

### During Processing:
1. **Console Logs**: Look for messages like:
   - `💰 Credits used: ~X (for email enrichment)`
   - `✅ Using existing employee data (saved 1 API call)`

2. **Apollo.io Dashboard**:
   - Go to: `app.apollo.io/#/settings/credits/current`
   - Check "Enrichment usage" (this is where credits are used)
   - Monitor before and after processing

### After Processing:
- Check total credits used in Apollo.io dashboard
- Compare with expected usage (see table above)
- If usage is much higher, check console logs for errors

---

## 🚨 Warning Signs (Stop Testing If You See These)

1. **Credits used > 2x expected**: Something is wrong, stop immediately
2. **Many "API call" messages**: Should see mostly "Using existing data"
3. **0 contacts found**: Check if companies have websites/domains
4. **Errors in console**: Fix errors before continuing

---

## 💡 Best Practices

1. ✅ **Always test with 1-2 companies first**
2. ✅ **Check Apollo.io dashboard before and after**
3. ✅ **Monitor console logs during processing**
4. ✅ **Use same companies for testing** (reuses database data = saves credits)
5. ✅ **Process during off-peak hours** (if Apollo has rate limits)

---

## 🔍 What Changed (Credit Savings)

### Before (Your Issue):
- **272 credits for 2 contacts** = ~136 credits per contact ❌
- **Problem**: Multiple API calls per company (3-4 for employee count)
- **Problem**: Too strict filtering (removed valid contacts)

### After (Fixed):
- **Expected**: ~1-2 credits per contact ✅
- **Employee count**: Only 1 API call (saved 2-3 credits per company)
- **Contact search**: FREE (saved all search credits)
- **Better filtering**: Keeps more valid contacts

---

## 📝 Testing Checklist

Before processing 10 companies:
- [ ] Tested with 1 company successfully
- [ ] Verified credit usage matches expected (~10-15 credits)
- [ ] Got reasonable number of contacts (not just 1-2)
- [ ] Checked Apollo.io dashboard for actual usage
- [ ] No errors in console logs
- [ ] Ready to scale up to 2 companies, then 5, then 10

---

**Remember**: Apollo.io credits are expensive. Always test small first! 🎯
