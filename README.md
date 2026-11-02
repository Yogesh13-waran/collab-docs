# CollabDocs Backend API

> **High-Performance Collaborative Document Workspace Backend**  
> Built with Django 6.1, Django REST Framework 3.18, and PostgreSQL/SQLite.  
> Designed for enterprise scalability, ACID transactions, atomic versioning, and role-based access control.

---

## 1. Project Overview

**CollabDocs** is an API-first backend for collaborative document workspaces (similar to Notion or Google Docs). It provides a full set of RESTful capabilities for workspace management, role-based collaborator access, version-controlled document authoring, threaded discussions, categorization tags, and automated audit logging.

### Key Architectural Highlights
- **100% UUID Primary Keys**: All 8 models use auto-generated `UUIDField` primary keys (`uuid.uuid4`) for security and distributed scalability.
- **ACID Transactions**:
  - Workspace creation guarantees atomic creation of the workspace and the owner's `admin` membership.
  - Document saves/updates execute in a `transaction.atomic()` block, calculating per-document version numbers without a global counter (`Document.versions.count() + 1`).
- **Real-Time Audit Trail**: Connected via a `post_save` signal on `Document`, using `instance._state.adding` to distinguish creation from updates.
- **Query Optimization**: Completely eliminates the N+1 query problem through `select_related` and `prefetch_related`.
- **Advanced Querying**: Demonstrates `Q` objects for multi-field OR search, range/lookup filters (`gte`, `lte`, `in`, `__icontains`), aggregations/annotations with `Count`, and `values_list()` for index/ID lookups.
- **Observability Middleware**: Custom `RequestLoggingMiddleware` measures request latency in milliseconds and prints structured HTTP logs to stdout for every incoming request.
- **Conflict Handling**: Explicitly catches `IntegrityError` to return HTTP `409 Conflict` when duplicate workspace memberships are attempted.

---

## 2. System Architecture & Tech Stack

| Layer | Technology | Details |
|---|---|---|
| **Framework** | Django 6.1 | Web foundation, ORM, authentication, signals, middleware |
| **API Layer** | Django REST Framework 3.18 | `ModelViewSet`, `@action` decorators, serializers, exception handlers |
| **Database** | PostgreSQL / SQLite | Pinned via `.env`; psycopg3 (`psycopg-binary==3.3.4`) driver |
| **Authentication** | Django Auth | Custom `User` model with UUID PK; pluggable for JWT / Token auth |
| **Configuration** | `python-dotenv` 1.2.4 | 12-factor configuration via `.env` file |
| **Testing** | Django Test Framework / unittest | 28 automated tests covering models, transactions, views, and middleware |
| **API Client** | Postman | Postman Collection v2.1.0 with sample bodies for all 17+ endpoints |

---

## 3. The 8 Data Models

```
+---------------------------------------------------------------------------------+
|                                 CollabDocs Models                               |
+---------------------------------------------------------------------------------+
| 1. User            -> AbstractUser with UUID4 PK                                |
| 2. Workspace       -> id, name, description, owner (FK User), is_active=True    |
| 3. WorkspaceMember -> UniqueConstraint(workspace, user), role (admin/editor/view)|
| 4. Document        -> workspace (FK), title, content, status (TextChoices)      |
| 5. DocumentVersion -> UniqueConstraint(document, version_number), snapshot data |
| 6. Comment         -> self-referential parent FK for threaded replies           |
| 7. Tag             -> ManyToMany join table with Document                       |
| 8. AuditLog        -> actor, action, model_name, object_id, timestamp           |
+---------------------------------------------------------------------------------+
```

1. **`User`**: Custom user model extending `AbstractUser` with UUID primary key.
2. **`Workspace`**: Workspaces owned by a user; holds documents and collaborator memberships.
3. **`WorkspaceMember`**: Role-based access control (`admin`, `editor`, `viewer`). Enforces `UniqueConstraint(fields=['workspace', 'user'])`.
4. **`Tag`**: Categorization tags linked via `ManyToManyField(Tag, related_name='documents')`.
5. **`Document`**: The core document entity with lifecycle states (`draft`, `review`, `published`, `archived`).
6. **`DocumentVersion`**: Immutable historical snapshot created atomically on every save with per-document `version_number`.
7. **`Comment`**: Threaded discussion entity using `parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='replies')`.
8. **`AuditLog`**: Automatic lifecycle tracking created via `post_save` signal on `Document`.

---

## 4. Setup & Installation

### Step 1: Clone and Set Up Virtual Environment

```bash
# Clone the repository
git clone <your-repository-url>
cd python-collabdocs

# Create a virtual environment
python -m venv venv

# Activate the virtual environment
# Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# Linux / macOS:
source venv/bin/activate
```

### Step 2: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 3: Configure Environment Variables

Copy `.env.example` to `.env`:

```bash
# Windows:
copy .env.example .env
# Linux / macOS:
cp .env.example .env
```

Edit `.env` to configure your database settings:
```env
# Application Settings
SECRET_KEY=your-secure-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0

# Database Engine Selection:
# For PostgreSQL (Evaluation/Production):
DB_ENGINE=django.db.backends.postgresql
DB_NAME=collabdocs_db
DB_USER=postgres
DB_PASSWORD=your_postgres_password
DB_HOST=localhost
DB_PORT=5432

# For SQLite (Local rapid development without local PostgreSQL server):
# DB_ENGINE=django.db.backends.sqlite3
```

### Step 4: Apply Database Migrations

```bash
python manage.py migrate
```

### Step 5: (Optional) Seed the Database with Realistic Demo Data

A custom management command is provided to pre-populate users, workspaces, documents, versions, tags, comments, and audit logs:

```bash
python manage.py seed_data
```

This creates:
- Users: `alice` (admin), `bob` (editor), `carol` (viewer)
- Workspaces: `Core Engineering`, `Product & Design`
- Documents with multiple versions, tags, and threaded comments

### Step 6: Run the Server

```bash
python manage.py runserver
```

The API will be accessible at: `http://127.0.0.1:8000/api/`

---

## 5. Running Automated Tests

A comprehensive test suite of 28 unit and integration tests is included:

```bash
python manage.py test tests
```

Output:
```
Ran 28 tests in ~30s
OK
System check identified no issues (0 silenced).
```

### Test Suite Breakdown
- `tests/test_models.py`: Validates all 8 models, UUID primary keys, `TextChoices`, `UniqueConstraint` on memberships, document version numbering constraint, self-referential comment FK, and ManyToMany tags.
- `tests/test_views.py`: Tests all 17+ API endpoints across the 6 folders, query filters, Q objects OR filtering, 409 conflict handling, serializer validations, and count aggregations.
- `tests/test_transactions.py`: Verifies transaction rollback behavior inside `transaction.atomic()`, ensuring zero database leaks on failure.
- `tests/test_signals.py`: Verifies `post_save` signal on `Document` creates `AuditLog` records for `created` and `updated` actions.
- `tests/test_middleware.py`: Validates `RequestLoggingMiddleware` latency measurement and stdout logging format.

---

## 6. API Reference (All 17+ Endpoints across 6 Folders)

Base URL: `http://127.0.0.1:8000/api`

### Folder 1: Users
| # | Method | Endpoint | Description | Status Code |
|---|---|---|---|---|
| 1 | `GET` | `/api/users/` | List all users (supports `?search=`) | `200 OK` |
| 2 | `POST` | `/api/users/` | Create a new user with hashed password | `201 Created` |
| 3 | `GET` | `/api/users/{id}/` | Retrieve user details by UUID | `200 OK` |

### Folder 2: Workspaces
| # | Method | Endpoint | Description | Status Code |
|---|---|---|---|---|
| 4 | `GET` | `/api/workspaces/` | List workspaces (filters: `is_active`, `name`, `created_at__gte`) | `200 OK` |
| 5 | `POST` | `/api/workspaces/` | Create workspace (atomic: creates workspace + adds owner as admin member) | `201 Created` |
| 6 | `GET` | `/api/workspaces/{id}/` | Retrieve workspace with nested members and `members_count` | `200 OK` |
| 7 | `POST` | `/api/workspaces/{id}/members/` | Add member to workspace (returns 409 Conflict if duplicate member) | `201 Created` / `409 Conflict` |
| 8 | `GET` | `/api/workspaces/{id}/stats/` | Workspace statistics using `aggregate()` and `Count` | `200 OK` |

### Folder 3: Documents
| # | Method | Endpoint | Description | Status Code |
|---|---|---|---|---|
| 9 | `GET` | `/api/documents/` | List documents (Q OR search across title/content, `status__in`, `tag`) | `200 OK` |
| 10 | `POST` | `/api/documents/` | Create document (atomic: creates doc + version 1 + signal audit log) | `201 Created` |
| 11 | `GET` | `/api/documents/{id}/` | Retrieve document details with versions/comments count | `200 OK` |
| 12 | `PUT` | `/api/documents/{id}/` | Update document (atomic: updates doc + creates version N+1 + audit log) | `200 OK` |
| 13 | `GET` | `/api/documents/{id}/versions/` | List all versions of a document | `200 OK` |
| 14 | `GET` | `/api/documents/{id}/summary/` | Document summary with word count, comment count, and metrics | `200 OK` |
| 15 | `POST` | `/api/documents/{id}/tags/` | Add tags to document using ManyToMany and `values_list()` | `200 OK` |

### Folder 4: Comments
| # | Method | Endpoint | Description | Status Code |
|---|---|---|---|---|
| 16 | `GET` | `/api/comments/` | List comments (supports `?document={id}&top_level=true`) | `200 OK` |
| 17 | `POST` | `/api/comments/` | Create comment or threaded reply (validates parent comment matches doc) | `201 Created` |

### Folder 5: Tags
| # | Method | Endpoint | Description | Status Code |
|---|---|---|---|---|
| 18 | `GET` | `/api/tags/` | List tags with annotated `document_count` | `200 OK` |
| 19 | `POST` | `/api/tags/` | Create a new tag with unique name validation | `201 Created` |

### Folder 6: Audit Logs
| # | Method | Endpoint | Description | Status Code |
|---|---|---|---|---|
| 20 | `GET` | `/api/audit-logs/` | List audit logs (filters: `model_name`, `action`, `object_id`) | `200 OK` |
| 21 | `GET` | `/api/audit-logs/{id}/` | Retrieve individual audit log entry | `200 OK` |

---

## 7. Postman Collection

The file `CollabDocs.postman_collection.json` is located in the repository root.

### Importing into Postman
1. Open Postman.
2. Click **Import** in the top-left corner.
3. Drag and drop `CollabDocs.postman_collection.json`.
4. The collection is organized into the exact 6 folders:
   - `1. Users`
   - `2. Workspaces`
   - `3. Documents`
   - `4. Comments`
   - `5. Tags`
   - `6. Audit Logs`
5. The collection contains collection variables (`baseUrl`, `userId`, `workspaceId`, `documentId`, `commentId`, `tagId`, `auditLogId`) and test scripts that automatically capture IDs from responses and propagate them to subsequent requests.

---

## 8. Demo Video Guide (5–10 Minutes)

> **Link to Demo Video**: `https://www.loom.com/share/your-recorded-video-id` *(Replace with your actual Loom or Google Drive link before final submission)*

### Video Checklist Required by Section 6.3:

1. **One Complete Atomic Transaction with Rollback on Failure**:
   - Demonstrate adding a duplicate member to a workspace or running the transaction rollback test:
     ```bash
     python manage.py test tests.test_transactions.TransactionRollbackTests
     ```
   - Show in Postman: POST `/api/workspaces/{id}/members/` with an already-joined user ID. Show the clean HTTP `409 Conflict` response with message `"User ... is already a member of workspace ..."`.
2. **Middleware Logs Appearing in Console**:
   - Point your screen recorder to the running Django server terminal.
   - Send requests from Postman (e.g. GET `/api/workspaces/` or POST `/api/documents/`).
   - Highlight the console logs generated by `RequestLoggingMiddleware`:
     ```
     [CollabDocs Logger] Method: POST | Path: /api/documents/ | Status: 201 | Time: 14.91ms
     ```
3. **At Least One Aggregation Endpoint**:
   - In Postman, call `GET /api/workspaces/{id}/stats/` or `GET /api/documents/{id}/summary/`.
   - Point out the `aggregate(total_documents=Count('id'), ...)` and `annotate()` metrics in the JSON response.
4. **AuditLog Written Automatically by the Signal**:
   - Send a `PUT /api/documents/{id}/` in Postman updating the document's content.
   - Send a `GET /api/audit-logs/?model_name=Document&object_id={id}`.
   - Show the new entry created by the `post_save` signal recording `action: "updated"`, the timestamp, and the actor.

---

## 9. Comprehensive Interview & Architecture Guide

For an in-depth breakdown of every file, internal Django & DRF mechanisms, database query optimizations, and 25+ real-world senior backend engineering interview questions with answers, read [INTERVIEW_AND_ARCHITECTURE_GUIDE.md](file:///c:/Users/yoges/python-collabdocs/INTERVIEW_AND_ARCHITECTURE_GUIDE.md).

