# Changes to DB

The following columns are renamed or modified between the first and second versions of the code:

| Table Name | Original Column Name | New Column Name |
| ---------- | -------------------- | --------------- |
| `users`    | `metadata`           | `meta`          |
| `users`    | `created_at`         | `createdAt`     |
| `threads`  | `metadata`           | `meta`          |
| `threads`  | `created_at`         | `createdAt`     |
| `steps`    | `metadata`           | `meta`          |
| `steps`    | `start_time`         | `startTime`     |
| `steps`    | `end_time`           | `endTime`       |
| `elements` | `metadata`           | (Removed)       |

Key changes:
1. The `metadata` column in several tables is renamed to `meta`.
2. Timestamps (`created_at`, `start_time`, and `end_time`) are renamed to PascalCase (`createdAt`, `startTime`, and `endTime`).
3. Some columns are removed (e.g., `metadata` in `elements`).

These changes make the column names consistent and follow a specific naming convention.

# feature update:
db.py 
FORCE_SQLITE = True  # or False

Now includes toggle to turn on or off database auto detect, forcing application to use sqlite.
