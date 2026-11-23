# Bounded ClamAV coverage

Home Manager declares two unprivileged jobs using Ubuntu's `/usr/bin/clamscan`.
Neither deletes, moves, quarantines or repairs input. Existing signature updates
continue under freshclam; no resident clamd is enabled. Private reports, SQLite
inventory, queue and extraction scratch stay in encrypted `/vault/.clamav-scan`
(directory 0700, files 0600). The original report/summary also remain in
`policy-migration-20261110` within that directory.

## Daily policy

The timer checks hourly for one daily pass on AC, preserving the old 24-hour
cadence during migration. Roots remain Downloads, Desktop and /vault. Symlinks
and nested mounts are not followed. Fingerprints include device, inode, size,
mtime and ctime; changed-during-scan content is never accepted as clean.

Changed/new files are eligible first. Unchanged files become due for a rolling
recheck after seven days, **subject to budgets**, not a guarantee of full coverage
within seven days. Oldest/unscanned results take priority over already checked
files; recent content and documents are preferred within that backlog. Initial
fingerprint coverage builds in batches instead of inventing historical hashes.
The metadata preview found about 163,000 files, with zero traversal errors, in
about 20 seconds at the 25% CPU cap. Initial/overdue coverage can span multiple days.

Cache exclusions additionally cover node_modules, .direnv, .stack-work,
dist-newstyle and Git objects. Project source and Git configuration/hooks remain
eligible. Excluded dependencies are not certified safe: package vulnerability
checks are separate. There is no blanket document/video/model extension exclusion;
large inputs are explicitly counted as omissions.

## Resource safeguards

Both units use Nice 15, idle I/O, CPUQuota 25%, MemoryHigh 1536 MiB and MemoryMax
2 GiB. A shared nonblocking lock prevents overlapping content scans. Each content
phase is bounded to 45 minutes, metadata inventory to 120 seconds, and the service
to 50 minutes. Loss of AC stops the child and leaves unfinished results incomplete.
Insufficient encrypted scratch space defers work. Symlinks/submounts stay excluded,
container recursion stays at 17, and signatures older than three days cause failure.

| Budget | Daily | Document rescan |
|---|---:|---:|
| File/extracted member | 256 MiB | 512 MiB |
| Outer + decoded container data | 512 MiB | 1024 MiB |
| Processing time per file | 120 seconds | 600 seconds |
| Contained-file count | 10,000 | 20,000 |
| Selected files per run | 20,000 | 4 |
| Selected input bytes | 4096 MiB | At most four 512 MiB inputs |
| Content wall time | 45 minutes | 45 minutes |

CPU/memory guards apply to systemd units; use those for content scans. Direct
advanced CLI runs retain work/engine budgets but do not create a resource cgroup.
A service OOM/kill can leave an unfinished attempt record; inspect unit state
rather than treating that record as success. Reports retain explicit omissions,
processing limits, errors and remaining eligible work. Fourteen reports per new
job type are retained; legacy reports are not deleted by this migration.

## Targeted documents

The second timer checks every six hours on AC. Its private queue initially imports
exactly the 40 PDFs/EPUBs that hit limits in the last legacy report. Smaller
eligible documents go first. Daily document-limit findings also queue the current
fingerprint; queued documents are not duplicated in the ordinary daily job.

Each unchanged document gets at most two attempts per cycle, at least six hours
apart. A remaining problem becomes `needs_review`; excessive size becomes
`blocked_size`, and unavailable/out-of-scope paths remain explicit. No limitless
retry or automatic further limit increase occurs. Engine/database startup failures
defer without consuming a document attempt. Changed files get a fresh bounded
cycle. A later failed daily recheck can requeue a previously resolved document.
A successful rescan resolves only its unchanged fingerprint.

ClamAV limit heuristics are **not malware signatures**, but do mean incomplete
coverage. Pending/unresolved queue entries and the initial baseline are not clean
results. A completed small batch does not establish that the whole queue is clear.

## Commands

```sh
xps-clamav-scan --status       # summaries, attempts/progress and queue counts
xps-clamav-scan --plan         # metadata-only daily preview
xps-clamav-scan --rescan-plan  # preview the next small document batch
systemctl --user start clamav-document-rescan.service
systemctl --user status clamav-document-rescan.service
journalctl --user -u clamav-document-rescan.service --since today
systemctl --user start clamav-scan.service
```

Previews update only private inventory/queue metadata, not source content. Status
works while the scan lock is held. Normal `systemctl --user stop UNIT.service`
stops a scan; completed results remain and disposable extraction scratch is cleaned.
Notifications summarize coverage gaps and queue progress, with critical urgency
for malware findings. Missing/paused Dunst retains a pending notification.

## Tests

Regression tests cover incremental invalidation, periodic eligibility, scope and
symlink exclusions, bounded selection/retries, classification, mutation races,
battery deferral and child termination on budget expiry. A live engine fixture
under CPUQuota=25%/MemoryMax=2G recognized clean content, the inert EICAR antivirus
test and a compressed archive exceeding its test limit. It distinguished the
limit from malware and preserved every fixture input. Only the disposable fixture
directory was removed. Real-document progress is recorded separately; configuration
and fixture success do not claim that all queued documents have cleared.
