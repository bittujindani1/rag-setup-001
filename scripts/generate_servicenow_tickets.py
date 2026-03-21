from __future__ import annotations

import csv
import json
from pathlib import Path


CATEGORIES = {
    "network": {
        "priorities": ["high", "medium", "medium", "low"],
        "locations": ["Pune", "Chennai", "Hyderabad", "Bengaluru", "Mumbai"],
        "templates": [
            (
                "Branch office internet outage",
                "Users in the {location} office cannot access external websites after a router update.",
                "Rolled back the router firmware and restarted WAN services for the {location} site.",
            ),
            (
                "VPN tunnel flapping",
                "The site-to-site VPN for {location} drops every 20 minutes and reconnects automatically.",
                "Replaced the stale phase-2 proposal and stabilized the tunnel keepalive settings.",
            ),
            (
                "Wireless packet loss in claims bay",
                "Adjusters in {location} report video calls dropping on the guest and corp SSIDs.",
                "Retuned AP channel assignments and disabled an overlapping rogue access point.",
            ),
            (
                "Network latency spike",
                "Users in {location} see severe latency when opening policy applications across the MPLS link.",
                "Moved the branch to the backup path and corrected QoS classification on the edge device.",
            ),
            (
                "Firewall rule blocking vendor access",
                "The vendor support subnet for {location} cannot reach the claims integration endpoint.",
                "Added the missing firewall object group and refreshed the published security policy.",
            ),
        ],
    },
    "identity": {
        "priorities": ["medium", "medium", "high", "low"],
        "locations": ["Operations", "Claims", "Underwriting", "Finance", "Service Desk"],
        "templates": [
            (
                "MFA prompt loop",
                "{location} users are repeatedly prompted for MFA on each login after a policy update.",
                "Cleared stale federation cookies and updated the conditional access session policy.",
            ),
            (
                "SSO token expired early",
                "{location} staff are getting logged out of the portal every 15 minutes.",
                "Aligned the SSO token lifetime with the IdP session timeout and republished the app config.",
            ),
            (
                "Group membership not syncing",
                "New joiners in {location} are missing app entitlements because AD groups are not syncing.",
                "Repaired the provisioning connector and reran incremental group synchronization.",
            ),
            (
                "Password reset emails delayed",
                "{location} users receive password reset messages nearly 30 minutes late.",
                "Fixed outbound mail throttling on the identity notification service.",
            ),
            (
                "Service account lockout",
                "A scheduled job for {location} is failing because the bound service account keeps locking out.",
                "Rotated the credential and updated the downstream application secret store.",
            ),
        ],
    },
    "device": {
        "priorities": ["medium", "medium", "low", "high"],
        "locations": ["field adjuster", "claims lead", "branch manager", "underwriter", "remote agent"],
        "templates": [
            (
                "Laptop encryption recovery key missing",
                "Support could not find the BitLocker recovery key for a replacement device issued to a {location}.",
                "Recovered the key from Intune escrow and rotated the device compliance policy.",
            ),
            (
                "Device compliance stuck pending",
                "A {location}'s Windows device has been pending compliance for over 24 hours.",
                "Forced a management sync and repaired the local MDM enrollment state.",
            ),
            (
                "Printer driver crash on startup",
                "A shared workstation used by a {location} crashes when the universal print driver loads.",
                "Removed the corrupt driver package and reinstalled the approved vendor driver.",
            ),
            (
                "Docking station not detected",
                "A {location}'s laptop intermittently fails to detect dual monitors on the office dock.",
                "Updated USB-C firmware and replaced the faulty dock power adapter.",
            ),
            (
                "Endpoint protection quarantine false positive",
                "The endpoint agent on a {location} laptop quarantined an approved claims utility.",
                "Whitelisted the signed binary and updated the detection policy baseline.",
            ),
        ],
    },
    "application": {
        "priorities": ["high", "high", "medium", "medium"],
        "locations": ["claims portal", "policy admin", "agent dashboard", "customer app", "billing API"],
        "templates": [
            (
                "Claims portal returns 502",
                "The {location} intermittently throws 502 errors during peak hours.",
                "Scaled the app pool and corrected an upstream timeout on the reverse proxy.",
            ),
            (
                "Search results missing recent records",
                "Users say the {location} does not show policies created in the last hour.",
                "Rebuilt the stale search shard and restarted the indexing worker.",
            ),
            (
                "Form submit hangs at validation",
                "The {location} stalls after client-side validation when users submit new requests.",
                "Fixed a dependency mismatch in the validation service and flushed cached bundles.",
            ),
            (
                "Attachment preview broken",
                "The {location} cannot render uploaded document previews for PDF and TIFF files.",
                "Restored the preview microservice and increased its memory allocation.",
            ),
            (
                "Batch job missed nightly run",
                "A scheduled process behind the {location} did not execute during the maintenance window.",
                "Corrected the cron expression and restored the job runner after patching.",
            ),
        ],
    },
    "email": {
        "priorities": ["low", "medium", "medium", "high"],
        "locations": ["regional support", "claims intake", "broker relations", "executive office", "shared mailbox"],
        "templates": [
            (
                "Shared mailbox not visible",
                "New joiners cannot see the {location} mailbox in Outlook after onboarding.",
                "Reapplied mailbox permissions and forced an autodiscover refresh.",
            ),
            (
                "Mail flow delayed to vendor",
                "Messages sent from the {location} team to an external vendor are delayed by over an hour.",
                "Corrected a transport connector rule and retried the message queue.",
            ),
            (
                "Calendar delegate cannot edit",
                "An assistant in the {location} team lost delegate edit access on the manager calendar.",
                "Repaired delegate permissions and refreshed the Outlook profile.",
            ),
            (
                "Phishing banner missing",
                "The warning banner is not being stamped on suspicious emails for the {location} mailbox.",
                "Updated the transport rule priority and re-enabled the banner action.",
            ),
            (
                "Archiving policy skipped mailbox",
                "The {location} mailbox exceeded quota because archive retention was never applied.",
                "Assigned the correct retention policy and started the managed folder assistant run.",
            ),
        ],
    },
    "database": {
        "priorities": ["high", "medium", "high", "medium"],
        "locations": ["claims reporting", "customer profile", "policy ledger", "analytics mart", "quote cache"],
        "templates": [
            (
                "Connection pool exhaustion",
                "The {location} database reached max pool size during morning traffic.",
                "Raised pool limits, terminated orphaned sessions, and tuned idle connection recycling.",
            ),
            (
                "Slow stored procedure",
                "A critical stored procedure in {location} now takes more than 90 seconds to complete.",
                "Added the missing composite index and updated statistics on the affected tables.",
            ),
            (
                "Replica lag impacting reads",
                "Read-only queries against {location} are stale because the replica is several minutes behind.",
                "Increased replica IOPS and fixed a long-running write transaction on the primary.",
            ),
            (
                "Migration failed midway",
                "The latest deployment left the {location} schema in a partially migrated state.",
                "Rolled back the failed migration and reapplied the patch with corrected DDL ordering.",
            ),
            (
                "Backup validation failure",
                "Nightly restore testing failed for the {location} snapshot set.",
                "Repaired the backup manifest and reran the restore validation job successfully.",
            ),
        ],
    },
}

STATUS_CYCLE = ["closed", "closed", "closed", "resolved", "closed", "closed"]
SOURCE_CYCLE = ["portal", "email", "phone", "chat", "monitoring", "self-service"]
ASSIGNEE_CYCLE = [
    "Network Ops",
    "Identity Team",
    "Endpoint Support",
    "Application Support",
    "Messaging Team",
    "Database Ops",
]


def build_tickets() -> list[dict[str, str]]:
    tickets: list[dict[str, str]] = []
    ticket_number = 1001

    for category, config in CATEGORIES.items():
        templates = config["templates"]
        priorities = config["priorities"]
        locations = config["locations"]

        for cycle in range(5):
            for index, (summary, issue_template, resolution_template) in enumerate(templates):
                location = locations[(cycle + index) % len(locations)]
                tickets.append(
                    {
                        "ticket_id": f"INC{ticket_number}",
                        "category": category,
                        "priority": priorities[(cycle + index) % len(priorities)],
                        "summary": summary,
                        "issue": issue_template.format(location=location),
                        "resolution": resolution_template.format(location=location),
                        "status": STATUS_CYCLE[(cycle + index) % len(STATUS_CYCLE)],
                        "source": SOURCE_CYCLE[(cycle + index) % len(SOURCE_CYCLE)],
                        "assignment_group": ASSIGNEE_CYCLE[list(CATEGORIES.keys()).index(category)],
                    }
                )
                ticket_number += 1

    return tickets


def main() -> None:
    tickets = build_tickets()
    output_dir = Path(__file__).resolve().parent / "generated"
    output_dir.mkdir(parents=True, exist_ok=True)

    csv_path = output_dir / "servicenow_tickets.csv"
    json_path = output_dir / "servicenow_tickets.json"

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(tickets[0].keys()))
        writer.writeheader()
        writer.writerows(tickets)

    json_path.write_text(json.dumps({"tickets": tickets}, indent=2), encoding="utf-8")
    print(f"Generated {len(tickets)} tickets")
    print(csv_path)
    print(json_path)


if __name__ == "__main__":
    main()
