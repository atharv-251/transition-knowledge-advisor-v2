# Phase 2 — Deploy the KT Tracker Bot to Azure App Service

This is a manual, click-by-click guide (no IaC, no CI/CD pipeline) for deploying
the KT Tracker Bot to **Azure App Service (Linux)** using your own
resource-group access. It assumes Phase 1 (Microsoft 365/Graph access) is
still pending with IT — this phase does **not** depend on that and can be
done in parallel.

## What you need before starting

- Contributor access to a resource group (e.g. `SalesForceTransition`).
- The repo working locally (already confirmed running via `python main.py`).
- [Visual Studio Code Azure App Service extension](https://marketplace.visualstudio.com/items?itemName=ms-azuretools.vscode-azureappservice)
  — this is the simplest way to push code to App Service without setting up
  Git remotes or CI/CD. Install it from the VS Code Extensions panel
  (search "Azure App Service").

## Success criteria for Phase 2 (all must pass before moving to Phase 3)

1. Web App is created and reachable at `https://<app-name>.azurewebsites.net`.
2. `GET /api/v1/health` returns `200 {"status":"healthy",...}`.
3. `GET /docs` (Swagger UI) loads and lists all endpoints.
4. App Service has a **System-assigned Managed Identity** enabled.
5. Application settings are configured (no secrets hardcoded in code or Docker image).
6. Only **one instance** is running (no autoscale) — required because the
   Microsoft Graph sync scheduler runs in-process (see "Known limitation" below).
7. You can redeploy a code change and see it reflected within a few minutes.

---

## Step 1 — Create the App Service Plan

1. Azure Portal → your resource group (e.g. `SalesForceTransition`) → **+ Create** → search **"App Service Plan"**.
2. Configure:
   - **Operating System**: Linux
   - **Region**: same region you plan to use for Azure SQL (keeps latency/cost down)
   - **Pricing tier**: `B1` (Basic) is enough for dev/test; use `P0v3` if you want
     staging slots or better performance later.
3. Create.

## Step 2 — Create the Web App

1. In the same resource group → **+ Create** → **"Web App"**.
2. Configure:
   - **Name**: e.g. `kt-tracker-bot-dev` (this becomes `kt-tracker-bot-dev.azurewebsites.net`)
   - **Publish**: `Code` (not Docker Container — we'll run the Python app directly; you can switch to `Docker Container` later using the existing [Dockerfile](/Users/wdqvvoz/OneDrive%20-%20Volkswagen%20AG/Vivek%20Chaurasia/Trainings/Agentic%20Mesh/transition-knowledge-advisor-v2/Dockerfile) if you prefer)
   - **Runtime stack**: `Python 3.13`
   - **Operating System**: Linux
   - **Region**: same as the App Service Plan
   - **App Service Plan**: select the one created in Step 1
3. Under **Monitoring** tab: enable **Application Insights** (creates one for you) — this gives you logs/traces without extra setup.
4. Create.

## Step 3 — Configure the startup command

App Service's Python auto-detection (Oryx) doesn't know how to start a custom
FastAPI entry point automatically, so set an explicit startup command:

1. Web App → **Settings → Configuration → General settings**.
2. **Startup Command**:
   ```
   python main.py
   ```
3. Save (this restarts the app).

> Why this works: [main.py](/Users/wdqvvoz/OneDrive%20-%20Volkswagen%20AG/Vivek%20Chaurasia/Trainings/Agentic%20Mesh/transition-knowledge-advisor-v2/main.py) already reads the `PORT` environment variable
> (`int(os.getenv("PORT", "8088"))`), and Azure App Service Linux automatically
> injects `PORT` (usually `8000`) into the container/runtime — no code change needed.

## Step 4 — Configure application settings (environment variables)

Web App → **Settings → Configuration → Application settings** → **+ New application setting** for each value currently in your local `.env` file. At minimum:

| Setting | Notes |
|---|---|
| `AGENTIC_BLUEPRINT_ENVIRONMENT` | Set to `production` (not `development`) — this switches [sql_connection.py](/Users/wdqvvoz/OneDrive%20-%20Volkswagen%20AG/Vivek%20Chaurasia/Trainings/Agentic%20Mesh/transition-knowledge-advisor-v2/app/database/sql_connection.py) from `AzureCliCredential` to `DefaultAzureCredential`, which uses the Managed Identity set up in Step 5 |
| `DATABASE_MODE` | `azure_sql` |
| `AZURE_SQL_SERVER`, `AZURE_SQL_DATABASE` | Your Azure SQL server/database names |
| `AZURE_SQL_AUTH_MODE` | `entra` (uses Managed Identity, no password stored anywhere) |
| `LLMAAS_API_KEY`, `LLMAAS_CLIENT_ID`, `LLMAAS_CLIENT_SECRET` | Mark these **sticky** and treat as secrets (see Key Vault note below) |
| `KT_GRAPH_SYNC_ENABLED` | Leave `false` until Phase 1 (Graph access) is validated |
| All other vars from [.env.example](/Users/wdqvvoz/OneDrive%20-%20Volkswagen%20AG/Vivek%20Chaurasia/Trainings/Agentic%20Mesh/transition-knowledge-advisor-v2/.env.example) | Copy as needed |

**Security note:** For a quick dev deployment, plain Application Settings are
fine — they're encrypted at rest and not visible in code. For production,
move secrets (`LLMAAS_API_KEY`, `LLMAAS_CLIENT_SECRET`, future Graph
`AZURE_CLIENT_SECRET`) into **Azure Key Vault** and reference them from App
Settings as `@Microsoft.KeyVault(SecretUri=...)` — this can be a Phase 2.1
follow-up rather than a blocker.

## Step 5 — Enable Managed Identity (for passwordless Azure SQL access)

1. Web App → **Settings → Identity → System assigned** → toggle **On** → Save.
2. Copy the generated **Object (principal) ID**.
3. On your Azure SQL Server, connect as an Azure AD admin (or ask whoever
   set up Azure SQL) and run:
   ```sql
   CREATE USER [kt-tracker-bot-dev] FROM EXTERNAL PROVIDER;
   ALTER ROLE db_datareader ADD MEMBER [kt-tracker-bot-dev];
   ALTER ROLE db_datawriter ADD MEMBER [kt-tracker-bot-dev];
   ```
   (Use the Web App's name, not the Object ID, in the `CREATE USER` statement —
   Azure SQL resolves it against Entra ID automatically.)

This lets the app authenticate to Azure SQL with **zero passwords/secrets**,
matching the `create_azure_credential()` logic already in
[sql_connection.py](/Users/wdqvvoz/OneDrive%20-%20Volkswagen%20AG/Vivek%20Chaurasia/Trainings/Agentic%20Mesh/transition-knowledge-advisor-v2/app/database/sql_connection.py).

## Step 6 — Allow the Web App to reach Azure SQL

1. Azure SQL Server → **Networking**.
2. Under **Firewall rules**, enable **"Allow Azure services and resources to
   access this server"** (simplest for now).
3. For tighter security later, replace this with **VNet integration +
   Private Endpoint** so traffic never leaves Azure's private network — worth
   revisiting once the dev deployment works end-to-end.

## Step 7 — Deploy the code (VS Code extension, no CI/CD)

1. In VS Code, open this workspace, click the **Azure** icon in the sidebar.
2. Sign in with your VW Azure account.
3. Under **App Service**, find your Web App (`kt-tracker-bot-dev`).
4. Right-click it → **Deploy to Web App...** → select this project folder.
5. Confirm the prompt (it will zip and upload the app, then run
   `pip install -r requirements.txt` on the server via Oryx build).
6. Wait for "Deployment successful" notification.

Repeat this step any time you want to push a new code change — it's manual
but fully repeatable without needing Git/CI setup.

## Step 8 — Verify

```powershell
curl https://kt-tracker-bot-dev.azurewebsites.net/api/v1/health
curl https://kt-tracker-bot-dev.azurewebsites.net/api/v1/ready
```

Then open `https://kt-tracker-bot-dev.azurewebsites.net/docs` in a browser to
confirm Swagger UI loads with all endpoints.

- `/api/v1/health` should return `200` immediately (no dependencies checked).
- `/api/v1/ready` will return `503` until Azure SQL is reachable — expected
  until Phase 3 (Azure SQL migration) is complete, since the app currently
  keeps KT data in memory and only opens a SQL connection for the readiness
  probe itself.

## Step 9 — Health check + Always On

1. Web App → **Settings → Health check** → enable, path `/api/v1/health`.
2. Web App → **Configuration → General settings** → **Always On** → **On**
   (prevents the app from unloading due to idle timeout, which would kill the
   in-process Graph sync scheduler once Phase 1 is complete).

## Known limitation — do not scale out past 1 instance (yet)

The Microsoft Graph meeting-sync scheduler
([scheduler.py](/Users/wdqvvoz/OneDrive%20-%20Volkswagen%20AG/Vivek%20Chaurasia/Trainings/Agentic%20Mesh/transition-knowledge-advisor-v2/app/kt_tracker/scheduler.py))
runs as an in-process `asyncio` loop started in the FastAPI `lifespan`. If
you scale the App Service Plan to more than one instance, **each instance
would run its own copy of the scheduler**, causing duplicate Graph API calls
and duplicate KT activity upserts (the dedupe logic protects against
duplicate *data*, but you'd still waste Graph API quota and get noisy logs).

- **For now**: keep the App Service Plan at a single instance, no autoscale rules.
- **Future fix** (when this becomes a real constraint): move the scheduler
  out of the web process into a separate **Azure Function with a Timer
  trigger**, or use a distributed lock (e.g. a row in Azure SQL) so only one
  instance runs the sync at a time. Flagging this now so it's a conscious
  choice, not a surprise later when the mesh needs to scale.

## What's intentionally deferred to later phases

- Azure SQL Bicep/ARM templates and schema migration → **Phase 3**.
- Key Vault secret references → optional Phase 2.1 hardening.
- CI/CD pipeline (GitHub Actions/Azure DevOps) → only worth it once this repo
  is pushed to a real Git remote; can revisit any time.
- Custom domain + TLS certificate → optional, cosmetic.
