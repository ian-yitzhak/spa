
## Data safety (hard rule)

Never delete data — database rows, files, accounts, server state — unless the user asked for that exact deletion. If a task looks like it needs one, stop and ask, naming what would be removed and how many rows.

Before an approved delete:
1. `systemctl start beautyflow-backup.service` on the VPS and confirm the new dump exists in `/var/backups/<product>/`.
2. Delete with the narrowest filter possible (one vendor, one id).
3. Print before/after counts for every other vendor to prove nothing else moved.

The VPS is shared with afritherapy, wananchimart and buytickets. Backups keep 30 days; after that a deletion is permanent.

## Branches (POS)

Every vendor has a `pos.Branch` ("Main branch"); POS is billed per branch (`Branch.pos_expires_at`,
`Vendor.pos_expires_at` mirrors the furthest one). Orders, expenses, tables, stock (`BranchStock`)
and staff all carry a branch. `pos/branching.py` decides which branch a request is in:
staff are locked to theirs, the owner picks one or "All". Nothing is filtered for a vendor with a
single branch, so single-outlet businesses behave exactly as before.

The feature is gated: the Branches page needs `Vendor.branches_enabled` (per vendor) or
`SiteSettings.branches_open` (everyone). Only beautyflow has it on for now.
