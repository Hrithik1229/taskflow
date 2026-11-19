# TaskFlow UI Screenshots

> **Status:** Automated headless browser capture (Playwright / Puppeteer) is not installed in this execution environment. Per the project instructions, screenshots are **clearly marked as missing** and have **not been fabricated or mocked**.

Follow the instructions below to capture the complete suite of reviewer-ready application screenshots.

---

## Required Screenshots Inventory

| File Name | View / Component | Viewport / State | Required Content & Actions |
| :--- | :--- | :---: | :--- |
| `01-dashboard.png` | Main Dashboard | Desktop (1440 × 900) | Logged-in view showing project metric summary cards (Total Tasks, Assigned to Me, Overdue, Completed) and project list. |
| `02-kanban-board.png` | Kanban Board | Desktop (1440 × 900) | Active project board showing the 4 columns (`To do`, `In progress`, `Review`, `Completed`) with populated task cards, priority indicators, and live filter bar. |
| `03-task-detail-comments.png` | Task Detail Modal | Desktop (1440 × 900) | Opened task modal displaying editable fields, assigned reviewer, and discussion comment thread with timestamps and author badges. |
| `04-member-management.png` | Project Members View | Desktop (1440 × 900) | Members page showing owner/admin/member roles, invitation form, and role management controls. |
| `05-notifications-tray.png` | Notification Menu | Desktop (1440 × 900) | Top navigation bar with open notification popover displaying unread and read alerts, badge counter, and "Mark all read" button. |
| `06-mobile-view.png` | Mobile Kanban / Nav | Mobile (390 × 844) | Responsive mobile view demonstrating collapsible navigation, fluid column scrolling, and responsive action buttons. |

---

## Step-by-Step Capture Instructions

### 1. Start the Local Production-Like Stack
```bash
# In the project root:
docker compose -f docker-compose.prod-like.yml --env-file .env.prod-like up -d
```
Verify services are healthy:
- Backend: `http://localhost:8000/api/health`
- Frontend: `http://localhost:3000`

### 2. Seed Demo Accounts & Data
Run the database seed script:
```bash
backend\.venv\Scripts\python.exe backend/scripts/seed_dev.py
```
This provisions:
- **Project Owner:** `demo.owner@example.com` / `TaskFlowDemoOwner1!`
- **Project Member:** `demo.member@example.com` / `TaskFlowDemoMember1!`
- A sample project with populated tasks in all four columns.

### 3. Capture Screenshots
1. Open Google Chrome or Chromium in Incognito mode.
2. Open DevTools (`F12`), toggle Device Toolbar (`Ctrl+Shift+M`).
3. Set dimension to **1440 × 900** (DPR: 1.0 or 2.0).
4. Log in as `demo.owner@example.com`.
5. Capture each specified view using Chrome's **"Capture full size screenshot"** or **"Capture screenshot"** in the DevTools Command Menu (`Ctrl+Shift+P`).
6. Save the PNG files into `docs/screenshots/` matching the exact filenames listed in the table above.
