# KT Tracker Bot – App Registration & Graph Access Plan (VW Group process)

**Requested by:** Vivek Chaurasia
**Purpose:** Enable a read-only automation bot ("KT Tracker Bot") to detect
Knowledge Transfer (KT) meetings from Outlook/Teams and read their
attendance/transcript so KT completion status can be tracked automatically
instead of manually.

**Scope:** Read-only. No write, delete, or send-as permissions requested.
No access to mailbox content beyond calendar metadata and Teams meeting
artifacts (attendance/transcript) for meetings the KT bot is explicitly
scoped to.

---

## This is now based on the official VW Group "App Registration" process

Per the internal documentation
([General information about App Registration](https://volkswagengroup.sharepoint.com/sites/GlobalTenantInfoboard/SitePages/en/Dokumentation-App-Registration.aspx)),
the KT Tracker Bot clearly qualifies for an Entra ID app registration because
it meets this stated condition:

> "The application requires the Microsoft Graph API of the 'M365 VW Group
> tenant' in order to function."

Importantly, **this is a self-service, app-owner-driven process** — it does
**not** require pre-existing Global Admin / Entra ID rights in the production
tenant (the 401 you hit browsing App registrations directly was expected;
that portal blade is for tenant admins, not the request process below).

### Roles in this process (per VW documentation)

| Role | Who | Responsibility |
|---|---|---|
| **App owner** | **You (Vivek)** | Submit the request, configure the app **in the DEV tenant**, specify required API permissions, test, maintain the LeanIX entry, initiate the security assessment when ready for production, manage credentials |
| Tenant Infrastructure Basis Services | IT platform team | Platform operations, staging, overall process management |
| IT Security | IT Security team | Evaluates the app/API integration for security & data protection, confirms assessment to the governance body |
| Group IT Security (Conditional Access governance body) | IT Security governance | Validates the assessment, evaluates risk/necessity of permissions, **approves production deployment only** |

**Key implication:** DEV tenant testing (what we need for Phase 1) is
almost entirely in your hands as App Owner. IT Security / governance
approval is only required before moving to **production** (real
organization-wide mailboxes), not for building/testing in DEV.

---

## Step-by-step plan

### Step 1 — Request Admin User access in the Volkswagen AG DEV tenant

- In **myServe / Audi Service Portal**, search for and submit:
  **"Microsoft 365 / Entra: Admin User Request"**
- This grants you admin rights **scoped to the separate VW AG DEV tenant**
  used for testing — not the production tenant you were denied access to.
  This is the form that should unblock Phase 1 testing.

### Step 2 — Reference the app in LeanIX

- VW requires every app registration to be referenced in **LeanIX**
  (enterprise architecture catalog), mapping a "consumer interface" to the
  Graph API. As App Owner this is your responsibility to create/maintain.
- If you don't already have LeanIX access or aren't sure how KT Tracker Bot
  should be modeled there, this is worth a quick question to your EA/architecture
  contact — it's a documentation step, not a technical blocker.

### Step 3 — Create the app registration

Two equivalent paths, pick whichever is available to you once Step 1 is done:

- **Self-service form**: submit **"M365 | App Registration Request"** via
  myServe, or
- **Directly in the DEV tenant**: once you have DEV tenant admin rights from
  Step 1, you can create the app registration yourself in the DEV tenant's
  Azure Portal (App registrations blade) — the same portal blade that gave a
  401 before will work once you're operating inside the DEV tenant with the
  granted role.

Either way, request these 4 **Microsoft Graph Application permissions**
(all read-only, admin consent required):

- `Calendars.Read`
- `OnlineMeetings.Read.All`
- `OnlineMeetingArtifact.Read.All`
- `OnlineMeetingTranscript.Read.All`

`scripts/create_kt_tracker_app.ps1` in this repo automates this step (app
registration + these 4 permissions + a secret) — **run it yourself** once you
have DEV tenant admin rights; it no longer needs to be handed off to a
separate admin. It resolves the exact permission IDs live from the tenant
rather than hardcoding them, so it's safe to run in the DEV tenant directly.

### Step 4 — Get a credential (certificate preferred over secret)

- VW policy explicitly recommends **certificates over client secrets**
  (secrets still work, but trigger expiry-notification cycles at
  60/30/14/7/1 days). For a first DEV test, a secret is fine and is what
  `create_kt_tracker_app.ps1` provisions by default.
- If a secret is what's provisioned, you can also self-serve via
  **"M365 | App Registration Secret Request"** if you'd rather not run the
  script yourself.

### Step 5 — Grant the app access to the specific KT mailbox/calendar

- Submit **"M365 | Exchange Application Permission Assignment"** via myServe
  — this is the VW-sanctioned self-service path to scope the app's Graph
  permissions down to a specific mailbox (rather than every mailbox in the
  tenant), which is both more secure and more likely to be approved quickly.
- There is also a related VW article, **"API access to an Exchange Online
  mailbox"**, worth reading alongside this form if questions come up.
- If Teams meeting artifacts (attendance, transcripts) still require a
  separate **Teams Application Access Policy**, the same PowerShell approach
  documented previously still applies as a fallback (requires a Teams
  Administrator role):

  ```powershell
  Install-Module -Name MicrosoftTeams -Force
  Connect-MicrosoftTeams
  New-CsApplicationAccessPolicy -Identity kt-tracker-bot-policy `
      -AppIds "<CLIENT_ID_FROM_APP_REGISTRATION>" `
      -Description "KT Tracker Bot - read-only Graph access"
  Grant-CsApplicationAccessPolicy -PolicyName kt-tracker-bot-policy `
      -Identity "<kt-mailbox@vwgroup.com>"
  ```

### Step 6 — (Optional) Request a DEV test user/mailbox

- Submit **"Test User Request - DEV environment"** if you need a dedicated
  test mailbox to schedule sample KT meetings against, rather than using a
  real colleague's calendar for early testing.

### Step 7 — Test entirely within the DEV tenant

- Confirm the DEV tenant's Teams meeting policy has
  `AllowTranscription = $true` so transcripts actually get generated.
- Run `scripts/graph_connectivity_check.py` end-to-end against the DEV
  tenant credentials — this is exactly what Phase 1 success criteria (7
  checks) validates, now achievable without waiting on production security
  approval.

### Step 8 — Only when ready for production

- As App Owner, you **initiate** (not perform) the IT Security assessment.
- IT Security evaluates the app; Group IT Security (Conditional Access
  governance body) validates risk/necessity of the permissions and approves
  production admin consent.
- This step is deferred until Phase 1 is fully validated in DEV — consistent
  with the "one phase at a time" approach already agreed.

---

## A note on "Work IQ Calendar" (the other option IT mentioned)

Work IQ Calendar is a Microsoft Foundry-hosted MCP tool that can read/manage
**Outlook Calendar** events (create, update, free/busy, attendee status) for
agentic workflows. It does **not** cover Teams attendance reports or meeting
transcripts, which are essential to Steps 2–4 of our automation (analyzing
what was actually discussed). It could be a useful **complementary** tool
later for calendar-only tasks (e.g. auto-scheduling follow-up KT sessions),
but it cannot replace the Graph app registration above for transcript-driven
analysis, so it is not pursued as the primary path for Phase 1.

## What to keep secure once provisioned

- Tenant ID (DEV tenant), Client ID (Application ID), Client Secret/Certificate
- Store these only in `.env` (already gitignored) or a secrets vault — never
  in chat, email, or committed to the repo.

## Estimated effort

Mostly self-service once DEV tenant admin access (Step 1) is granted —
no longer blocked on a separate IT admin's time for DEV testing. Production
rollout still requires the formal security assessment / governance approval
described above.
