# Job Hunter Autofill — Chrome Extension

Fills any job-application page from your Job Hunter profile — saved
Application Answers, learned answers, and resume-grounded AI drafts.
You review every field and click the page's own submit. Nothing is sent
automatically.

## Install (unpacked)
1. Chrome → `chrome://extensions`
2. Toggle **Developer mode** (top right)
3. **Load unpacked** → select this `extension/` folder
4. Click the extension icon → sign in with your Job Hunter email/password

## Use
- Open any job application page (Workday, Greenhouse, iCIMS, Lever, Ashby, …)
- Click the floating **Fill with Job Hunter** button, or the extension icon → **Fill this application**
- Green outline = filled from your profile; purple outline = AI draft (review these)
- Check every answer, then submit on the page yourself

## How it works
The content script scans the page's form fields and sends their labels to
`/api/extension/answer`, which runs the same answer engine as the in-app
Auto-Apply modal (profile + saved answers + learned memory + class rules),
plus AI drafts for open-ended questions. The token lives in the extension's
local storage; the background worker proxies all API calls.
