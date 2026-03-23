"""
Generate incident_ops_agent_demo.csv — 200 enriched ServiceNow-style tickets
for the Multi-Agent Collaboration Workspace demo.

Fields:
  ticket_id, category, priority, status, summary, issue, resolution,
  assignment_group, source, created_at, resolved_at,
  sla_target_hours, actual_resolution_hours, sla_breached

Planted anomalies:
  - Identity spike in week 3 (Jan 13–19)
  - Network outage cluster in week 6 (Feb 3–9)

Usage:
  python scripts/agents/generate_incident_ops_demo.py
  # -> outputs scripts/agents/incident_ops_agent_demo.csv
"""
from __future__ import annotations

import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

random.seed(42)

CATEGORIES = ["network", "identity", "device", "application", "security", "database"]

PRIORITIES = ["P1", "P2", "P3", "P4"]

SLA_TARGETS = {"P1": 4, "P2": 8, "P3": 24, "P4": 72}

ASSIGNMENT_GROUPS = [
    "Network-Ops", "IAM-Team", "Desktop-Support", "App-Support",
    "Security-Ops", "DBA-Team", "Cloud-Infra", "Service-Desk",
]

SUMMARIES = {
    "network": [
        "VPN connection dropping intermittently",
        "Site-to-site tunnel flapping",
        "Network latency spike on corporate LAN",
        "Firewall blocking internal traffic",
        "DNS resolution failure for internal hosts",
        "Switch port showing CRC errors",
        "BGP route advertisement issue",
        "Load balancer health check failures",
    ],
    "identity": [
        "User locked out after MFA failure loop",
        "SSO redirect loop on claims portal",
        "LDAP sync not reflecting group changes",
        "Password reset not working for contractor accounts",
        "AD account disabled despite active status",
        "Federation metadata stale — causing auth failures",
        "MFA enrollment failure for new hires",
        "Service account expired — breaking automated jobs",
    ],
    "device": [
        "Laptop cannot connect to Wi-Fi after update",
        "Blue screen on Windows update rollout",
        "VPN client not installing on macOS Sonoma",
        "Printer driver causing device manager crash",
        "BitLocker recovery key not escrowed",
        "Device compliance check failing in Intune",
        "USB ports disabled by policy blocking peripherals",
        "Screen flickering on docking station",
    ],
    "application": [
        "Claims portal returning 502 after deploy",
        "Policy upload timing out on large files",
        "Reports module showing blank screen",
        "Notification emails not sending from CRM",
        "API gateway 429 during business hours",
        "Database connection pool exhausted",
        "Session timeout too aggressive",
        "Bulk export job crashing at 50k rows",
    ],
    "security": [
        "Suspicious login from unusual geolocation",
        "Phishing email clicked — endpoint isolation needed",
        "Expired SSL certificate on internal service",
        "Unauthorized S3 bucket access detected",
        "Privileged account used outside maintenance window",
        "Vulnerability scanner flagging CVE on web server",
        "Failed brute-force attempts on VPN gateway",
        "Data loss prevention alert on email attachment",
    ],
    "database": [
        "Slow query degrading reporting performance",
        "Transaction log fill causing backup failures",
        "Replication lag exceeding 30 minutes",
        "Index fragmentation causing timeouts",
        "Dead lock in claims processing workflow",
        "Storage threshold reached on primary DB",
        "Connection string misconfigured post-migration",
        "Backup job failing silently",
    ],
}

ISSUES = {
    "network": [
        "Phase-2 IPsec proposal mismatch causing tunnel reset",
        "STP topology change flooding broadcast domain",
        "MTU mismatch between MPLS and local LAN",
        "NAT translation table overflow during peak hours",
        "Misconfigured ACL blocking internal subnet",
    ],
    "identity": [
        "Stale federation metadata not updated after cert rotation",
        "MFA token delivery delay exceeding 30s timeout",
        "LDAP referral chasing disabled causing sync gap",
        "UPN suffix mismatch after domain migration",
        "Token cache not cleared after password change",
    ],
    "device": [
        "Windows update KB5034441 incompatible with recovery partition",
        "Intune compliance policy conflict with local GPO",
        "Certificate trust chain broken after root CA renewal",
        "Driver signing enforcement blocking third-party VPN",
        "Registry key missing after OS reimaging",
    ],
    "application": [
        "App pool recycling mid-request under load",
        "Thread pool starvation from synchronous database calls",
        "Redis cache eviction under memory pressure",
        "Blob storage SAS token expiry not handled gracefully",
        "CORS origin mismatch after frontend domain change",
    ],
    "security": [
        "Credential reuse from compromised third-party site",
        "Phishing kit using homograph domain",
        "Certificate not renewed due to expired ACME account",
        "S3 bucket public-read ACL left from dev environment",
        "SOC alert threshold too low causing false positive storm",
    ],
    "database": [
        "Missing index on high-cardinality filter column",
        "Autogrow event holding schema lock",
        "Replication subscriber falling behind due to locking contention",
        "Statistics not updated after bulk data load",
        "Connection string pointing to old endpoint post-failover",
    ],
}

RESOLUTIONS = {
    "network": [
        "Replaced stale phase-2 proposal with AES-256-GCM and rekeyed",
        "Cleared STP topology by disabling portfast on trunk ports",
        "Aligned MTU to 1400 bytes on MPLS edge router",
        "Increased NAT translation table to 65k entries",
        "Updated ACL to permit required subnet with audit log",
    ],
    "identity": [
        "Refreshed federation metadata XML and restarted ADFS service",
        "Switched MFA delivery to TOTP app, removed SMS fallback",
        "Enabled LDAP referral chasing in directory sync config",
        "Added alternate UPN suffix and resynced affected accounts",
        "Forced token cache flush via PowerShell + re-enrollment",
    ],
    "device": [
        "Applied safe-OS update workaround per MS KB5034441",
        "Created policy exclusion for compliant legacy hardware group",
        "Re-issued certificates from renewed root CA and pushed via SCCM",
        "Added driver signing exception in Intune policy profile",
        "Deployed registry fix via Group Policy Preferences",
    ],
    "application": [
        "Increased app pool recycling interval to 4h, added warm-up script",
        "Refactored synchronous DB calls to async with connection pooling",
        "Increased Redis maxmemory and switched to allkeys-lru policy",
        "Implemented SAS token rotation with 15-minute overlap window",
        "Updated API gateway CORS allowlist with verified origins",
    ],
    "security": [
        "Forced password reset + MFA re-enrollment, blocked IP range",
        "Blocked homograph domain at DNS and email gateway",
        "Renewed certificate via ACME and added renewal alert at 30d",
        "Removed public-read ACL and enabled access logging on bucket",
        "Tuned SOC alert threshold and added suppression for known IPs",
    ],
    "database": [
        "Added covering index on filter column, rebuilding statistics nightly",
        "Set autogrowth to fixed 1GB increments, pre-allocated space",
        "Reduced replication article count, filtered non-critical tables",
        "Scheduled AUTO_UPDATE_STATISTICS after ETL jobs complete",
        "Updated connection string in all services and restarted dependents",
    ],
}

START_DATE = datetime(2026, 1, 1)
END_DATE = datetime(2026, 3, 31)


def _random_date(start: datetime, end: datetime) -> datetime:
    delta = end - start
    return start + timedelta(seconds=random.randint(0, int(delta.total_seconds())))


def _generate_ticket(ticket_num: int, created_at: datetime, category: str, priority: str) -> dict:
    sla_hours = SLA_TARGETS[priority]
    # Variance: P1/P2 usually met, P3/P4 more often breached
    breach_probability = {"P1": 0.08, "P2": 0.12, "P3": 0.22, "P4": 0.30}[priority]
    sla_breached = random.random() < breach_probability

    if sla_breached:
        actual_hours = round(sla_hours * random.uniform(1.1, 3.0), 1)
    else:
        actual_hours = round(sla_hours * random.uniform(0.2, 0.95), 1)

    resolved_at = created_at + timedelta(hours=actual_hours)

    summary = random.choice(SUMMARIES[category])
    issue = random.choice(ISSUES[category])
    resolution = random.choice(RESOLUTIONS[category])
    group = random.choice(ASSIGNMENT_GROUPS)

    return {
        "ticket_id": f"INC{ticket_num:05d}",
        "category": category,
        "priority": priority,
        "status": "Resolved",
        "summary": summary,
        "issue": issue,
        "resolution": resolution,
        "assignment_group": group,
        "source": "ServiceNow",
        "created_at": created_at.strftime("%Y-%m-%dT%H:%M:%S"),
        "resolved_at": resolved_at.strftime("%Y-%m-%dT%H:%M:%S"),
        "sla_target_hours": sla_hours,
        "actual_resolution_hours": actual_hours,
        "sla_breached": str(sla_breached).upper(),
    }


def generate(output_path: Path) -> None:
    tickets = []
    ticket_num = 10001

    # Baseline: ~120 tickets spread evenly Jan-Mar
    for _ in range(120):
        category = random.choices(CATEGORIES, weights=[20, 18, 16, 18, 14, 14])[0]
        priority = random.choices(PRIORITIES, weights=[5, 20, 45, 30])[0]
        created_at = _random_date(START_DATE, END_DATE)
        tickets.append(_generate_ticket(ticket_num, created_at, category, priority))
        ticket_num += 1

    # Anomaly 1: Identity spike — week 3 (Jan 13–19)
    week3_start = datetime(2026, 1, 13)
    week3_end = datetime(2026, 1, 19, 23, 59)
    for _ in range(25):
        priority = random.choices(PRIORITIES, weights=[10, 35, 40, 15])[0]
        created_at = _random_date(week3_start, week3_end)
        tickets.append(_generate_ticket(ticket_num, created_at, "identity", priority))
        ticket_num += 1

    # Anomaly 2: Network outage cluster — week 6 (Feb 3–9)
    week6_start = datetime(2026, 2, 3)
    week6_end = datetime(2026, 2, 9, 23, 59)
    for _ in range(25):
        priority = random.choices(PRIORITIES, weights=[20, 40, 30, 10])[0]
        created_at = _random_date(week6_start, week6_end)
        tickets.append(_generate_ticket(ticket_num, created_at, "network", priority))
        ticket_num += 1

    # Additional P1s sprinkled throughout
    for _ in range(10):
        category = random.choice(CATEGORIES)
        created_at = _random_date(START_DATE, END_DATE)
        tickets.append(_generate_ticket(ticket_num, created_at, category, "P1"))
        ticket_num += 1

    # Sort by created_at
    tickets.sort(key=lambda t: t["created_at"])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(tickets[0].keys())
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(tickets)

    print(f"Generated {len(tickets)} tickets -> {output_path}")
    cats = {}
    for t in tickets:
        cats[t["category"]] = cats.get(t["category"], 0) + 1
    for cat, count in sorted(cats.items()):
        print(f"  {cat}: {count}")
    breached = sum(1 for t in tickets if t["sla_breached"] == "TRUE")
    print(f"  SLA breached: {breached}/{len(tickets)} ({100*breached//len(tickets)}%)")


if __name__ == "__main__":
    out = Path(__file__).parent / "incident_ops_agent_demo.csv"
    generate(out)
