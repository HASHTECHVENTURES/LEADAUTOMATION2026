# Apollo Industry Field – Trial

We can send **industry** when pushing contacts from Level 3 to Apollo so you can filter by industry in Apollo **People**.

## How it works

- Each contact we save has an **industry** (e.g. "IT Sector") from the Level 1 search.
- When you transfer a contact to Apollo (Level 3), we send that industry into a **custom contact field** in Apollo (Apollo has no built-in “industry” on the contact).
- You must create that custom field in Apollo and give us its ID.

## Trial steps

### 1. Create a custom field in Apollo

1. In **Apollo** go to **Settings** → **Custom fields** (or **Fields**).
2. Create a new **Contact** field:
   - **Name:** e.g. `Industry` or `Campaign Industry`
   - **Type:** Single-line text (or picklist if you prefer fixed values).
3. Save. Note: we will need this field’s **ID** in the next step.

### 2. Get the custom field ID

**Option A – From our script (easiest)**

Run in the project folder:

```bash
cd LEADAUTOMATION2026
python3 -c "
from apollo_client import ApolloClient
c = ApolloClient()
fields = c.get_contact_custom_fields()
for f in fields:
    print(f\"  {f['name']!r}  id = {f['id']}\")
if not fields:
    print('No contact custom fields (or API key cannot list them).')
"
```

Find the line for your **Industry** (or **Campaign Industry**) field and copy the `id`.

**Option B – From Apollo**

If Apollo’s UI or API docs show the field ID when you create or edit the field, you can copy it from there.

### 3. Set the ID in the app

Set this environment variable (or add it in `.env`):

```bash
APOLLO_INDUSTRY_CUSTOM_FIELD_ID=<paste_the_id_here>
```

Example:

```bash
APOLLO_INDUSTRY_CUSTOM_FIELD_ID=60c39ed82bd02f01154c470a
```

Restart the app (e.g. restart the Flask server) so it picks up the new value.

### 4. Test

1. In Level 3, transfer one or a few contacts to Apollo.
2. In Apollo, open **People** and open the contact.
3. Check that the **Industry** (or **Campaign Industry**) custom field is filled with the same industry as in our app (e.g. "IT Sector").
4. If Apollo lets you filter People by that custom field, filter by that industry and confirm the transferred contacts appear.

## If you don’t set the ID

- If `APOLLO_INDUSTRY_CUSTOM_FIELD_ID` is **not** set, we still transfer contacts to Apollo as before; we just don’t send industry. No errors, no change in behaviour except industry not being set.

## Summary

| Step | Action |
|------|--------|
| 1 | Create a Contact custom field “Industry” (or similar) in Apollo. |
| 2 | Get its ID (script above or Apollo UI/docs). |
| 3 | Set `APOLLO_INDUSTRY_CUSTOM_FIELD_ID=<id>` and restart the app. |
| 4 | Transfer contacts from Level 3 and check in Apollo that the Industry field is set and filterable. |
