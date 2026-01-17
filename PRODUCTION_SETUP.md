# Production Setup Guide - Enterprise Ready

## 🚨 CRITICAL: This is for PRODUCTION, not demo!

This setup includes all safeguards to prevent failures during demos and real-world usage.

## Step 1: Run Base Schema First

1. Go to Supabase Dashboard → SQL Editor
2. Run `supabase_schema.sql` FIRST (if not already done)
3. Wait for it to complete

## Step 2: Run Production Schema

1. Still in SQL Editor
2. Copy and paste `supabase_schema_production.sql`
3. Click **Run**
4. Wait for completion (may take 1-2 minutes)

## Step 3: Verify Setup

Run this in SQL Editor to verify everything is working:

```sql
-- Health check
SELECT * FROM health_check();

-- Check data integrity
SELECT * FROM check_data_integrity();

-- View table sizes
SELECT * FROM table_sizes;

-- Check index usage
SELECT * FROM index_usage_stats LIMIT 10;
```

## Step 4: Set Up Auto-Refresh (IMPORTANT!)

### Option A: Supabase Cron Job (Recommended)

1. Go to Supabase Dashboard → Database → Cron Jobs
2. Create new cron job:
   - **Name**: `refresh_stats_daily`
   - **Schedule**: `0 2 * * *` (2 AM daily)
   - **SQL**: 
   ```sql
   SELECT refresh_project_stats_safe();
   ```

3. Create cleanup cron job:
   - **Name**: `cleanup_old_progress`
   - **Schedule**: `0 3 * * *` (3 AM daily)
   - **SQL**:
   ```sql
   SELECT cleanup_old_progress_safe();
   ```

### Option B: Manual Refresh

Run this daily:
```sql
SELECT refresh_project_stats_safe();
```

## What's Protected Now

### ✅ Data Validation
- Empty project/company names are rejected
- Invalid email formats are rejected
- Text field length limits prevent abuse
- Place ID format validation

### ✅ Performance
- All critical queries are indexed
- Materialized views for instant stats
- Full-text search for fast lookups
- Query limits to prevent abuse

### ✅ Error Handling
- All functions have try-catch blocks
- Functions return safe defaults on error
- No crashes from bad data

### ✅ Monitoring
- Health check endpoint
- Data integrity checks
- Performance monitoring views
- Index usage tracking

### ✅ Maintenance
- Automatic cleanup of old records
- Safe refresh functions
- Data integrity validation

## Production Checklist

Before going live, verify:

- [ ] Base schema (`supabase_schema.sql`) is applied
- [ ] Production schema (`supabase_schema_production.sql`) is applied
- [ ] Health check returns `"status": "healthy"`
- [ ] Data integrity check shows no critical issues
- [ ] Cron jobs are set up for auto-refresh
- [ ] All indexes are created (check `index_usage_stats`)
- [ ] Materialized views are populated (check `project_stats`)

## Monitoring in Production

### Daily Checks

```sql
-- Health check
SELECT * FROM health_check();

-- Check for slow queries (if pg_stat_statements enabled)
SELECT * FROM slow_queries LIMIT 10;

-- Check table sizes (watch for bloat)
SELECT * FROM table_sizes;
```

### Weekly Checks

```sql
-- Data integrity
SELECT * FROM check_data_integrity();

-- Index usage (identify unused indexes)
SELECT * FROM index_usage_stats 
WHERE index_scans = 0 
ORDER BY index_size DESC;
```

## Troubleshooting

### Issue: Functions not found
**Solution**: Make sure you ran `supabase_schema_production.sql` completely

### Issue: Materialized views empty
**Solution**: Run `REFRESH MATERIALIZED VIEW project_stats;`

### Issue: Slow queries
**Solution**: 
1. Check `index_usage_stats` to see if indexes are being used
2. Run `EXPLAIN ANALYZE` on slow queries
3. Check `table_sizes` for bloat

### Issue: Health check fails
**Solution**: Check Supabase dashboard for connection issues

## Performance Expectations

With this setup, you should see:

- **Project list**: < 50ms
- **Company search**: < 100ms
- **Batch stats**: < 20ms (from materialized view)
- **Health check**: < 10ms

## Security Notes

- All functions use `SECURITY DEFINER` for controlled access
- Permissions are granted to `authenticated` role only
- Service role key should NEVER be exposed to frontend
- Use Row Level Security (RLS) for multi-tenant scenarios

## Backup Strategy

Supabase automatically backs up your database, but for extra safety:

1. **Daily backups**: Supabase Pro plan includes point-in-time recovery
2. **Manual exports**: Use Supabase dashboard → Database → Backups
3. **Export data**: Use `pg_dump` for full database export

## Support

If you encounter issues:

1. Check Supabase dashboard logs
2. Run health check: `SELECT * FROM health_check();`
3. Check data integrity: `SELECT * FROM check_data_integrity();`
4. Review `index_usage_stats` for performance issues

---

**Remember**: This is production-grade. Your boss will be happy! 🚀

