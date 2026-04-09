# Gmail API Setup Guide

A step-by-step guide for connecting the `gmail-monitor` skill to your Gmail account.
No prior Google Cloud experience required.

---

## Overview

The `gmail-monitor` skill uses the official Gmail API with OAuth 2.0. This means:
- Google asks you to approve access once in a browser window
- The skill gets a **read-only** token — it can never send, delete, or modify mail
- Your password is never stored anywhere

Total setup time: ~10 minutes.

---

## Part 1 — Google Cloud Console

### Step 1 — Create a Google Cloud project

1. Go to **[https://console.cloud.google.com](https://console.cloud.google.com)**
2. Sign in with the Google account whose Gmail you want to monitor
3. In the top bar, click **"Select a project"** → then click **"New Project"**

   ![New Project button is in the top-right of the project picker dialog]

4. Fill in:
   - **Project name:** `ai-employee`
   - **Location:** leave as "No organisation" unless you have a Workspace account
5. Click **Create** and wait ~10 seconds for it to provision
6. Make sure the new project is selected in the top bar before continuing

---

### Step 2 — Enable the Gmail API

1. In the left sidebar click **"APIs & Services"** → **"Library"**
2. In the search box type `Gmail API` and press Enter
3. Click the **Gmail API** card (blue envelope icon)
4. Click the blue **"Enable"** button
5. Wait for the page to reload — you should now see the Gmail API dashboard

---

### Step 3 — Configure the OAuth consent screen

> This is the screen Google shows you when asking for permission. You only
> configure it once.

1. In the left sidebar click **"APIs & Services"** → **"OAuth consent screen"**
2. Select **"External"** and click **Create**
3. Fill in the required fields on the first page:
   - **App name:** `AI Employee`
   - **User support email:** your Gmail address
   - **Developer contact email:** your Gmail address
   - Leave everything else blank
4. Click **Save and Continue**
5. On the **Scopes** page — click **Save and Continue** (no changes needed)
6. On the **Test users** page:
   - Click **"+ Add Users"**
   - Enter your Gmail address
   - Click **Add**
7. Click **Save and Continue**, then **Back to Dashboard**

> **Why test users?** While your app is in "testing" mode (which is fine for
> personal use), only listed addresses can authorise it. Add the Gmail account
> you want to monitor.

---

### Step 4 — Create OAuth 2.0 credentials

1. In the left sidebar click **"APIs & Services"** → **"Credentials"**
2. Click **"+ Create Credentials"** → **"OAuth client ID"**
3. Set **Application type** to **"Desktop app"**
4. Set **Name** to `ai-employee-desktop`
5. Click **Create**
6. A dialog appears showing your client ID and secret — click **"Download JSON"**
7. The file downloads as something like `client_secret_123456-abc.apps.googleusercontent.com.json`

---

## Part 2 — Installing Credentials

### Step 5 — Create the .credentials folder

Open a terminal in the project folder and run:

```bash
mkdir -p .credentials
```

Or navigate to `ai-employee-project/` in File Explorer and create a folder
named `.credentials` manually.

> **Note:** The leading dot makes it a hidden folder on Mac/Linux. On Windows
> it is visible but treated as a regular folder.

---

### Step 6 — Move credentials.json into place

Rename the downloaded file to exactly `credentials.json` and move it:

```bash
# From the project root — adjust the source path to match your download filename
mv ~/Downloads/client_secret_*.json .credentials/credentials.json
```

Or in File Explorer: rename the file to `credentials.json` and drag it into
the `.credentials/` folder.

Verify the file is in the right place:

```bash
ls .credentials/
# Expected output:  credentials.json
```

---

### Step 7 — First-run authorisation

The first time the `gmail-monitor` skill runs it will:

1. Detect that no `token.json` exists yet
2. Open your default browser to a Google sign-in page
3. Ask you to choose the Google account you added as a test user
4. Show a permissions screen: **"AI Employee wants to access your Gmail"**
   - Click **"Continue"** (you may see a warning that the app is unverified — this
     is expected for personal/testing apps; click "Advanced" → "Go to AI Employee")
5. Grant the **read Gmail messages and settings** permission
6. The browser will show `"The authentication flow has completed"` — you can close it
7. Back in the terminal you will see:

```
[gmail-monitor] Token saved to .credentials/token.json
```

The token is stored and all future runs skip the browser entirely.

---

## Part 3 — Testing the Setup

### Running the gmail-monitor skill

Ask Claude Code in this project:

```
Check my email
```
or
```
Scan inbox
```

### What to expect on first run

```
[gmail-monitor] Authenticating with Gmail API...
[gmail-monitor] Opening browser for first-time authorization...
[gmail-monitor] Token saved to .credentials/token.json
[gmail-monitor] Query: is:unread label:inbox ("urgent" OR "asap" OR "invoice" OR "payment")
[gmail-monitor] 2 matching unread email(s) found.
  [new]  Card created: EMAIL_20260404_143055_1a2b3c4d_Invoice_April.md
  [new]  Card created: EMAIL_20260404_091200_5e6f7a8b_Urgent_review.md
[gmail-monitor] 2 new inbox card(s) created.
```

### What to expect on subsequent runs

```
[gmail-monitor] Authenticating with Gmail API...
[gmail-monitor] Refreshing access token...
[gmail-monitor] Query: is:unread label:inbox ("urgent" OR "asap" OR "invoice" OR "payment")
[gmail-monitor] 0 matching unread email(s) found.
[gmail-monitor] No new priority emails to log.
```

### Token storage location

```
ai-employee-project/
└── .credentials/
    ├── credentials.json   ← OAuth app identity (from Google Cloud Console)
    └── token.json         ← your personal access token (auto-created on first run)
```

Both files are listed in `.gitignore` and will never be committed to git.

---

## Troubleshooting

### "credentials.json not found"

```
[gmail-monitor] Setup required:
credentials.json not found at .credentials/credentials.json
```

**Fix:** The file is missing or misnamed. Check:
- File is named exactly `credentials.json` (not `credentials (1).json` or the original long name)
- File is inside `.credentials/` folder, not the project root

---

### "Access blocked: This app's request is invalid"

**Fix:** You skipped the OAuth consent screen setup or used an email address not
added as a test user. Go back to **Part 1 → Step 3** and ensure your Gmail
address is in the **Test users** list.

---

### "Token has been expired or revoked"

```
google.auth.exceptions.RefreshError: Token has been expired or revoked
```

**Fix:** Delete the old token and re-authorise:

```bash
rm .credentials/token.json
```

Then run the skill again — the browser flow will repeat once.

---

### "quota exceeded" or 429 errors

The free Gmail API quota is 1 billion units/day for personal accounts —
effectively unlimited for this use case. If you see quota errors, wait a few
minutes and try again. You can check usage at:
**Google Cloud Console → APIs & Services → Gmail API → Metrics**

---

### Browser does not open automatically

The skill uses `flow.run_local_server(port=0)`. If your environment blocks
browser auto-open, copy the URL printed to the terminal and paste it manually
into a browser.

---

### "This app isn't verified" warning

This is expected. Your app is in **testing mode** (personal use only).

Click **"Advanced"** → **"Go to AI Employee (unsafe)"** → grant permission.

To remove the warning permanently you would need to submit the app for Google
verification — not required for personal/hackathon use.

---

## Security Reminders

| Rule | Why it matters |
|------|---------------|
| Never commit `.credentials/` to git | `credentials.json` contains your OAuth client secret; `token.json` grants inbox access — either file in a public repo is a serious breach |
| Keep scope to `gmail.readonly` | The skill cannot send, delete, or label mail — intentional design |
| Only add trusted addresses as test users | Anyone added can authorise the app against your client credentials |
| Revoke access any time | Go to **myaccount.google.com/permissions** → find "AI Employee" → Remove Access |
| Rotate credentials if compromised | Delete the OAuth client in Google Cloud Console → create a new one → replace `credentials.json` |

---

## Quick Reference

| File | Location | Purpose |
|------|----------|---------|
| `credentials.json` | `.credentials/credentials.json` | OAuth app identity (download once from Cloud Console) |
| `token.json` | `.credentials/token.json` | Your personal access token (auto-created on first run) |
| `GMAIL_SETUP.md` | project root | This guide |
| `gmail-monitor/SKILL.md` | `.claude/skills/gmail-monitor/` | Full skill implementation |
