# CollabDocs Demo Video: Step-by-Step Recording Script (5–10 Minutes)

> **Submission Requirement (Section 6.3)**:  
> Screen-recorded video with voiceover audio walking through the app via Postman.  
> Must cover the 4 mandatory demonstration points.

---

## 1. Quick Recording Setup

1. **Tools you can use to record (free & easy)**:
   - **Loom** (Recommended): [loom.com](https://www.loom.com) — records screen + microphone directly to a shareable link.
   - **Windows Built-in Recorder**: Press `Windows Key + Alt + R` to record screen and microphone.
   - **OBS Studio**: Free open-source screen recorder.
2. **Setup your screen layout**:
   - **Left half of screen**: Postman with the `CollabDocs API Collection` loaded.
   - **Right half of screen**: Terminal window running the Django server (`python manage.py runserver`).
3. **Pre-requisite (run this once before recording)**:
   ```bash
   python manage.py migrate
   python manage.py seed_data
   python manage.py runserver
   ```
   *This pre-populates users (`alice`, `bob`, `carol`), workspaces (`Core Engineering`), documents with versions, tags, and comments so you don't have to type long UUIDs during the recording.*

---

## 2. Word-for-Word Walkthrough Script (6–8 Minutes)

---

### [0:00 - 1:00] Introduction & Architecture Overview

**What to show on screen**:  
Show your VS Code or Postman with the CollabDocs project structure.

**What to say**:
> *"Hello! Today I am presenting the backend API for **CollabDocs** — a collaborative workspace and document platform built with Django 6.1 and Django REST Framework.*  
>  
> *CollabDocs implements 8 core models with 100% UUID primary keys, role-based access control, atomic document versioning, threaded comments, tag categorization, automated audit logging via signals, and latency tracking middleware.*  
>  
> *In this walkthrough, I will demonstrate the API in Postman, specifically highlighting the four required architectural milestones:*  
> *1. Middleware logging in the terminal console.*  
> *2. An atomic transaction with rollback on failure.*  
> *3. An aggregation endpoint utilizing Django ORM's `Count` and `aggregate`.*  
> *4. An automated `AuditLog` entry written by a `post_save` signal after a document update."*

---

### [1:00 - 2:15] Requirement 1: Middleware Logs Appearing in Console

**What to show on screen**:  
Have your Postman on one side and the terminal running `python manage.py runserver` visible on the other side.

**Actions in Postman**:
1. Open the **1. Users** folder $\to$ select **1.1 List Users**. Click **Send**.
2. Open the **2. Workspaces** folder $\to$ select **2.1 List Workspaces**. Click **Send**.

**What to point out on screen**:  
Switch your cursor to the terminal window and highlight the console output.

**What to say**:
> *"Here in the terminal, you can see our custom `RequestLoggingMiddleware` in action.*  
>  
> *For every incoming request, the middleware intercepts the execution, starts a high-resolution monotonic timer with `time.perf_counter()`, processes the view, stops the clock, and prints the HTTP method, endpoint path, status code, and latency in milliseconds.*  
>  
> *Notice: `[CollabDocs Logger] Method: GET | Path: /api/workspaces/ | Status: 200 | Time: 6.19ms`.*  
> *This provides zero-overhead observability for production monitoring."*

---

### [2:15 - 4:00] Requirement 2: Complete Atomic Transaction with Rollback on Failure

**What to show on screen**:  
In Postman, expand the **2. Workspaces** folder.

**Part A: The Postman 409 Conflict Demonstration**:
1. Select **2.4 Add Member to Workspace**.
2. Notice the request body:
   ```json
   {
     "user_id": "<User ID of Alice or Bob>",
     "role": "editor"
   }
   ```
3. Click **Send** twice:
   - First call: `201 Created`.
   - Second call: `409 Conflict`!
4. Point out the response:
   ```json
   {
     "error": "Conflict: User 'bob' is already a member of workspace 'Core Engineering'."
   }
   ```

**Part B: The Terminal Transaction Rollback Test**:
Switch to a secondary terminal tab and run:
```bash
python manage.py test tests.test_transactions.TransactionRollbackTests -v 2
```

**What to say**:
> *"Now let's demonstrate data integrity and atomic transactions.*  
>  
> *In CollabDocs, workspace creation and member addition are wrapped in `transaction.atomic()`. Furthermore, our `WorkspaceMember` model enforces a composite `UniqueConstraint` on `(workspace, user)`.*  
>  
> *When we attempt to add a collaborator who is already a member, our view catches the database `IntegrityError` inside an atomic block and returns an explicit HTTP `409 Conflict`.*  
>  
> *To verify atomic rollback on failure, let's look at our test suite where we simulate a crash during a workspace creation. As you can see: `test_workspace_and_member_atomic_rollback ... ok`.*  
> *Because of `transaction.atomic()`, when the secondary operation failed, the workspace record was completely rolled back. Zero orphaned records leaked into the database."*

---

### [4:00 - 5:30] Requirement 3: Aggregation Endpoint (Stats or Summary)

**What to show on screen**:  
In Postman, select **2.5 Workspace Stats** (`GET /api/workspaces/{{workspaceId}}/stats/`).

**Action**: Click **Send**.

**What to point out in the response body**:
```json
{
  "workspace_id": "...",
  "workspace_name": "Core Engineering",
  "is_active": true,
  "total_members": 3,
  "member_user_ids": [
    "e2762b3a-...",
    "fa9817cd-..."
  ],
  "document_statistics": {
    "total_documents": 2,
    "draft_count": 0,
    "review_count": 1,
    "published_count": 1,
    "archived_count": 0
  }
}
```

**What to say**:
> *"Next is our aggregation requirement.*  
>  
> *This endpoint — `/api/workspaces/{id}/stats/` — uses Django ORM's `aggregate()` and `Count()` functions to perform on-the-fly SQL aggregation.*  
>  
> *Under the hood, it compiles into an SQL query with conditional counts for draft, review, published, and archived documents, plus the total members.*  
>  
> *Notice also the `member_user_ids` field: here we used `values_list('user_id', flat=True)` as required by Section 4.3, fetching only raw primary keys directly from the database cursor without the overhead of instantiating full model instances.*  
>  
> *We also have `GET /api/documents/{id}/summary/` which computes word counts and comment aggregations."*

---

### [5:30 - 7:00] Requirement 4: AuditLog Written Automatically by the Signal

**What to show on screen**:  
In Postman, expand the **3. Documents** folder and **6. Audit Logs** folder.

**Step 1: Check existing Audit Logs**:
1. Select **6.1 List Audit Logs** (`GET /api/audit-logs/`).
2. Click **Send**. Note the existing logs.

**Step 2: Update a Document**:
1. Select **3.4 Update Document** (`PUT /api/documents/{{documentId}}/`).
2. In the JSON body, change the title to:
   ```json
   {
     "workspace_id": "{{workspaceId}}",
     "title": "System Architecture Specification v3 - LIVE DEMO",
     "content": "Updated live during video walkthrough to demonstrate post_save signal.",
     "status": "published"
   }
   ```
3. Click **Send**. Status `200 OK`.
4. Point out: Notice that `versions_count` incremented, creating a new `DocumentVersion` inside `transaction.atomic()`!

**Step 3: Verify the Signal wrote the AuditLog**:
1. Go back to **6.1 List Audit Logs** (`GET /api/audit-logs/?action=updated`).
2. Click **Send**.
3. Highlight the newly created entry at the top:
   ```json
   {
     "id": "...",
     "actor_details": { "username": "alice" },
     "action": "updated",
     "model_name": "Document",
     "object_id": "<document_id>",
     "details": {
       "title": "System Architecture Specification v3 - LIVE DEMO",
       "status": "published"
     },
     "timestamp": "2026-..."
   }
   ```

**What to say**:
> *"Finally, requirement 4: automated audit logging via signals.*  
>  
> *In `core/signals.py`, we connected a `post_save` signal receiver to the `Document` model.*  
>  
> *We inspect `instance._state.adding` (cached during `pre_save`) to detect whether the save was a creation or an update.*  
>  
> *When I sent that `PUT` request to update the document, Django saved the document, and the `post_save` signal fired inside the exact same atomic transaction, writing this new `AuditLog` entry.*  
>  
> *Notice: `action: "updated"`, `model_name: "Document"`, the matching `object_id`, and the actor who made the change. Everything is automated, decoupled, and transaction-safe."*

---

### [7:00 - 7:30] Conclusion & Wrap Up

**What to say**:
> *"To conclude, we have demonstrated:*  
> *1. Real-time request logging middleware.*  
> *2. Atomic transactions with rollback and 409 Conflict error handling.*  
> *3. Query optimizations including `aggregate()`, `Count()`, and `values_list()`.*  
> *4. Automated event-driven audit logging via signals.*  
>  
> *The entire test suite with 28 automated tests is passing cleanly, and our full Postman collection covers all 17+ endpoints.*  
> *Thank you!"*

---

## 3. After Recording

1. If using Loom: Copy your Loom video link.
2. If recording locally: Upload the video file (`.mp4`) to Google Drive and set sharing to **"Anyone with the link can view"**.
3. Open `README.md` and paste your link in Section 8:
   ```markdown
   > **Link to Demo Video**: https://www.loom.com/share/your-actual-video-id
   ```
4. Commit and push your code to your GitHub repository!

