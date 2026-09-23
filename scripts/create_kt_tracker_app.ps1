<#
.SYNOPSIS
    One-shot script to create the KT Tracker Bot app registration with the
    minimum read-only Microsoft Graph permissions needed for automated KT
    meeting/transcript tracking.

.DESCRIPTION
    Per the VW Group App Registration process, this is intended to be run
    by the App Owner (that's you) directly inside the Volkswagen AG DEV
    tenant, once you have been granted Admin User rights there via the
    "Microsoft 365 / Entra: Admin User Request" myServe form. It does NOT
    require Global Administrator rights in the production tenant - only
    whatever admin role the DEV tenant request grants you (typically
    Application Administrator scoped to that tenant).

    See docs/IT_ACCESS_REQUEST.md for the full step-by-step process,
    including the LeanIX registration requirement and the myServe
    self-service forms this script complements/replaces (Step 3:
    "M365 | App Registration Request").

    It:
      1. Creates a single-tenant app registration "kt-tracker-bot"
         (no redirect URI - this is a daemon/service, not an interactive app).
      2. Requests 4 READ-ONLY Microsoft Graph application permissions:
           Calendars.Read
           OnlineMeetings.Read.All
           OnlineMeetingArtifact.Read.All
           OnlineMeetingTranscript.Read.All
      3. Creates a client secret (12-month validity).
      4. Optionally grants admin consent immediately, if run with
         -GrantAdminConsent and sufficient privilege.

    It does NOT configure the Teams Application Access Policy - that must
    still be run separately by someone with the Teams Administrator role
    (see docs/IT_ACCESS_REQUEST.md for the exact command).

.PARAMETER GrantAdminConsent
    If specified (and the running account has Global Administrator or
    Privileged Role Administrator rights), grants admin consent for the
    requested permissions automatically instead of requiring a manual
    portal click afterwards.

.NOTES
    Requires the Microsoft.Graph PowerShell module:
        Install-Module Microsoft.Graph -Scope CurrentUser
#>

param(
    [switch]$GrantAdminConsent,
    [string]$AppDisplayName = "kt-tracker-bot"
)

$ErrorActionPreference = "Stop"

Import-Module Microsoft.Graph.Applications -ErrorAction SilentlyContinue
Import-Module Microsoft.Graph.Identity.SignIns -ErrorAction SilentlyContinue

Write-Host "Connecting to Microsoft Graph (interactive sign-in)..." -ForegroundColor Cyan
Connect-MgGraph -Scopes "Application.ReadWrite.All", "AppRoleAssignment.ReadWrite.All", "DelegatedPermissionGrant.ReadWrite.All"

# Well-known Microsoft Graph resource app ID.
$graphResourceAppId = "00000003-0000-0000-c000-000000000000"
$requiredPermissionNames = @(
    "Calendars.Read"
    "OnlineMeetings.Read.All"
    "OnlineMeetingArtifact.Read.All"
    "OnlineMeetingTranscript.Read.All"
)

Write-Host "Looking up current Microsoft Graph app role IDs for this tenant..." -ForegroundColor Cyan
$graphSp = Get-MgServicePrincipal -Filter "appId eq '$graphResourceAppId'"
$graphRoles = $graphSp.AppRoles | Where-Object { $_.Value -in $requiredPermissionNames } |
    ForEach-Object { @{ Name = $_.Value; Id = $_.Id } }

$missing = $requiredPermissionNames | Where-Object { $_ -notin $graphRoles.Name }
if ($missing) {
    throw "Could not resolve these Graph application permissions in this tenant: $($missing -join ', '). Verify the names are current in Microsoft's Graph permissions reference before retrying."
}
Write-Host "Resolved $($graphRoles.Count) permission(s):" -ForegroundColor Green
$graphRoles | ForEach-Object { Write-Host "  $($_.Name) -> $($_.Id)" }


Write-Host "Creating app registration '$AppDisplayName'..." -ForegroundColor Cyan
$app = New-MgApplication -DisplayName $AppDisplayName -SignInAudience "AzureADMyOrg" `
    -RequiredResourceAccess @(
        @{
            ResourceAppId  = $graphResourceAppId
            ResourceAccess = $graphRoles | ForEach-Object {
                @{ Id = $_.Id; Type = "Role" }
            }
        }
    )

Write-Host "Creating service principal..." -ForegroundColor Cyan
$sp = New-MgServicePrincipal -AppId $app.AppId

Write-Host "Creating client secret (12 months validity)..." -ForegroundColor Cyan
$secret = Add-MgApplicationPassword -ApplicationId $app.Id -PasswordCredential @{
    DisplayName = "kt-tracker-bot-secret"
    EndDateTime = (Get-Date).AddMonths(12)
}

if ($GrantAdminConsent) {
    Write-Host "Granting admin consent for requested permissions..." -ForegroundColor Cyan
    $graphSp = Get-MgServicePrincipal -Filter "appId eq '$graphResourceAppId'"
    foreach ($role in $graphRoles) {
        New-MgServicePrincipalAppRoleAssignment -ServicePrincipalId $sp.Id `
            -PrincipalId $sp.Id -ResourceId $graphSp.Id -AppRoleId $role.Id | Out-Null
        Write-Host "  Granted: $($role.Name)" -ForegroundColor Green
    }
} else {
    Write-Host "Skipped automatic consent. An admin must still click:" -ForegroundColor Yellow
    Write-Host "  Entra ID portal -> App registrations -> $AppDisplayName -> API permissions -> Grant admin consent" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== SAVE THESE VALUES SECURELY (share via Key Vault / secure channel, not chat/email) ===" -ForegroundColor Magenta
Write-Host "Tenant ID     : $((Get-MgContext).TenantId)"
Write-Host "Client ID     : $($app.AppId)"
Write-Host "Client Secret : $($secret.SecretText)"
Write-Host ""
Write-Host "NEXT STEP (requires Teams Administrator role, run separately):" -ForegroundColor Cyan
Write-Host "  New-CsApplicationAccessPolicy -Identity kt-tracker-bot-policy -AppIds `"$($app.AppId)`" -Description 'KT Tracker Bot read-only access'"
Write-Host "  Grant-CsApplicationAccessPolicy -PolicyName kt-tracker-bot-policy -Identity '<kt-mailbox@vwgroup.com>'"
