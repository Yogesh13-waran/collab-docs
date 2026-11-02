# CollabDocs: Master Interview & Architecture Engineering Guide

> **Authoritative Technical Deep-Dive into the CollabDocs Backend Architecture**  
> *Written for senior engineering reviews, technical interviews, and architectural audits.*

---

## Table of Contents
1. [Executive Architectural Summary](#1-executive-architectural-summary)
2. [End-to-End File-by-File Blueprint](#2-end-to-end-file-by-file-blueprint)
   - [`collabdocs/settings.py`](#collabdocssettingspy)
   - [`collabdocs/middleware.py`](#collabdocsmiddlewarepy)
   - [`collabdocs/urls.py` & `core/urls.py`](#collabdocsurlspy--coreurlspy)
   - [`core/models.py`](#coremodelspy)
   - [`core/serializers.py`](#coreserializerspy)
   - [`core/views.py`](#coreviewspy)
   - [`core/signals.py` & `core/apps.py`](#coresignalspy--coreappspy)
   - [`core/exceptions.py`](#coreexceptionspy)
   - [`tests/` Suite](#tests-suite)
3. [Deep-Dive Technical Concepts](#3-deep-dive-technical-concepts)
   - [The N+1 Query Problem: `select_related` vs `prefetch_related`](#the-n1-query-problem-select_related-vs-prefetch_related)
   - [ACID Transactions & Atomic Concurrency](#acid-transactions--atomic-concurrency)
   - [UUIDv4 vs Auto-Incrementing BigInt](#uuidv4-vs-auto-incrementing-bigint)
   - [`UniqueConstraint` vs Legacy `unique_together`](#uniqueconstraint-vs-legacy-unique_together)
   - [Signal Lifecycle & `instance._state.adding`](#signal-lifecycle--instance_stateadding)
   - [Serializers: Internal Lifecycle & Validation Flow](#serializers-internal-lifecycle--validation-flow)
   - [`aggregate()` vs `annotate()`: The SQL Reality](#aggregate-vs-annotate-the-sql-reality)
   - [Middleware Internals: Onion Request-Response Lifecycle](#middleware-internals-onion-request-response-lifecycle)
4. [Top 25 Senior/Mid Backend Engineering Interview Questions & Master Answers](#4-top-25-seniormid-backend-engineering-interview-questions--master-answers)
5. [Comprehensive Assignment Objectives Mapping & Mastery Matrix](#5-comprehensive-assignment-objectives-mapping--mastery-matrix)
   - [Objective 1: Data Model Design & Relational Integrity (Sections 2 & 4.1)](#objective-1-data-model-design--relational-integrity-sections-2--41)
   - [Objective 2: API Architecture & Serializers (Sections 3 & 4.2)](#objective-2-api-architecture--serializers-sections-3--42)
   - [Objective 3: QuerySets & Query Optimization (Section 4.3)](#objective-3-querysets--query-optimization-section-43)
   - [Objective 4: Transactions & Data Integrity (Section 4.4)](#objective-4-transactions--data-integrity-section-44)
   - [Objective 5: Observability & Signals (Sections 3.1 & 4.5)](#objective-5-observability--signals-sections-31--45)
   - [Objective 6: Project Setup & Submission Compliance (Section 4.6 & 6)](#objective-6-project-setup--submission-compliance-section-46--6)

---

## 1. Executive Architectural Summary

CollabDocs is an enterprise-grade backend API engineered around the **Twelve-Factor App** methodology and Domain-Driven Design (DDD). It represents the core backend engine of a collaborative document workspace like Notion or Google Docs.

### Architectural Tenets
1. **API-First & Headless**: Decoupled from any specific frontend client; Postman, web SPAs, or mobile applications consume consistent, predictable JSON.
2. **Data Integrity Above All**: Zero orphaned records. Workspace creation with admin role initialization and document authoring with version history are bound by atomic transactions (`transaction.atomic()`).
3. **Optimized I/O & Database Querying**: Foreign-key relationships are eager-loaded using SQL joins (`select_related`) to guarantee $O(1)$ query complexity instead of $O(N)$ execution.
4. **Auditability & Observability**: Every mutation to a document generates an audit record via asynchronous/synchronous signals, and every incoming HTTP request is profiled for latency via custom middleware.

---

## 2. End-to-End File-by-File Blueprint

### `collabdocs/settings.py`

#### What It Does:
The central configuration engine for the Django application. It manages environment variable ingestion, installed applications, middleware pipeline order, database engine binding, and REST Framework defaults.

#### Key Architectural Highlights:
- **12-Factor Ingestion**: Uses `python-dotenv` to load `.env` at boot time (`load_dotenv(BASE_DIR / '.env')`).
- **Dynamic Database Engine**:
  ```python
  DB_ENGINE = os.getenv('DB_ENGINE', 'django.db.backends.postgresql')
  if 'sqlite' in DB_ENGINE.lower():
      DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'db.sqlite3'}}
  else:
      DATABASES = {
          'default': {
              'ENGINE': DB_ENGINE,
              'NAME': os.getenv('DB_NAME'),
              'USER': os.getenv('DB_USER'),
              'PASSWORD': os.getenv('DB_PASSWORD'),
              'HOST': os.getenv('DB_HOST'),
              'PORT': os.getenv('DB_PORT'),
          }
      }
  ```
  *Why this matters:* Production targets PostgreSQL with `psycopg3` (`psycopg-binary`), while local development or lightweight automated test environments can switch dynamically to SQLite without codebase modifications.
- **Custom User Model**:
  ```python
  AUTH_USER_MODEL = 'core.User'
  ```
  *Interview Critical Note:* Declaring `AUTH_USER_MODEL` before running the very first migration is mandatory in Django. Changing the user model after migrations are created requires intricate database schema restructuring.
- **Middleware Ordering**: `RequestLoggingMiddleware` is placed at the end of the `MIDDLEWARE` list. This ensures that response timing captures the total latency including all inner middleware and view processing.
- **DRF Configuration**:
  ```python
  REST_FRAMEWORK = {
      'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
      'PAGE_SIZE': 20,
      'EXCEPTION_HANDLER': 'core.exceptions.custom_exception_handler',
  }
  ```

---

### `collabdocs/middleware.py`

#### What It Does:
Implements `RequestLoggingMiddleware`, a custom middleware class that profiles every HTTP request passing through the server.

```python
import time
import logging

class RequestLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start_time = time.perf_counter()
        response = self.get_response(request)
        duration_ms = (time.perf_counter() - start_time) * 1000.0
        log_message = (
            f"[CollabDocs Logger] Method: {request.method} | "
            f"Path: {request.path} | "
            f"Status: {response.status_code} | "
            f"Time: {duration_ms:.2f}ms"
        )
        print(log_message)
        return response
```

#### Engineering Concepts:
1. **`time.perf_counter()` vs `time.time()`**:
   `time.time()` measures wall-clock time and can jump backward if system NTP syncs occur. `time.perf_counter()` is a monotonic clock with the highest available resolution on the operating system, making it the only appropriate choice for profiling execution duration.
2. **Django Onion Pattern**:
   When a request arrives, Django passes it sequentially down the middleware chain (`__call__` before `get_response`), into the view, and then bubbles the response back up in reverse order (`__call__` after `get_response`).

---

### `collabdocs/urls.py` & `core/urls.py`

#### What It Does:
Configures the routing hierarchy. `core/urls.py` uses DRF's `DefaultRouter` to automatically wire ViewSets into standardized RESTful endpoints:
```python
router = DefaultRouter()
router.register(r'users', UserViewSet, basename='user')
router.register(r'workspaces', WorkspaceViewSet, basename='workspace')
router.register(r'documents', DocumentViewSet, basename='document')
router.register(r'comments', CommentViewSet, basename='comment')
router.register(r'tags', TagViewSet, basename='tag')
router.register(r'audit-logs', AuditLogViewSet, basename='audit-log')
```

#### Engineering Concepts:
- **`DefaultRouter` vs `SimpleRouter`**: `DefaultRouter` automatically generates an API Root view (`GET /api/`) providing hyperlinks to all registered collections, and appends format suffixes (`.json`).
- **Dynamic Action Routing**: Methods decorated with `@action(detail=True, methods=['post'], url_path='members')` automatically generate `/api/workspaces/{id}/members/` without manual URL regex manipulation.

---

### `core/models.py`

The core data layer containing all 8 models.

```
+-----------------------------------------------------------------------------------+
| Model              | Primary Key | Constraints / Enums / Special Fields           |
+--------------------+-------------+------------------------------------------------+
| User               | UUID4       | AbstractUser extension, unique email           |
| Workspace          | UUID4       | is_active (default=True), owner FK User        |
| WorkspaceMember    | UUID4       | UniqueConstraint(workspace, user), TextChoices |
| Tag                | UUID4       | name (unique=True)                             |
| Document           | UUID4       | status (TextChoices: draft, review, pub, arch) |
| DocumentVersion    | UUID4       | UniqueConstraint(document, version_number)     |
| Comment            | UUID4       | parent = FK('self', null=True, SET_NULL)       |
| AuditLog           | UUID4       | actor FK, action, model_name, object_id        |
+-----------------------------------------------------------------------------------+
```

#### Key Implementation Details:

1. **`TextChoices` Enum Classes**:
   ```python
   class Role(models.TextChoices):
       ADMIN = 'admin', 'Admin'
       EDITOR = 'editor', 'Editor'
       VIEWER = 'viewer', 'Viewer'
   ```
   *Why not raw strings?* TextChoices prevent typos ("Admn"), provide human-readable labels, enable IDE auto-completion, and allow direct introspection via `Role.values` and `Role.choices`.

2. **`WorkspaceMember` Constraint**:
   ```python
   class Meta:
       constraints = [
           models.UniqueConstraint(fields=['workspace', 'user'], name='unique_workspace_member')
       ]
   ```
   *Why UniqueConstraint over unique_together?* `UniqueConstraint` represents the modern Django standard. It creates a formal database UNIQUE index and supports conditional expressions (e.g., `condition=Q(is_active=True)`).

3. **Threaded Comments Self-Referential Foreign Key**:
   ```python
   parent = models.ForeignKey(
       'self',
       null=True,
       blank=True,
       on_delete=models.SET_NULL,
       related_name='replies'
   )
   ```
   Top-level comments have `parent=None`. When a user replies, `parent` points to the ancestor comment ID. Using `on_delete=models.SET_NULL` ensures that if a parent comment is deleted, child replies are not catastrophically cascaded out of the database; instead, they remain with `parent=NULL`.

4. **DocumentVersion Per-Document Versioning**:
   ```python
   version_number = models.PositiveIntegerField()
   class Meta:
       constraints = [
           models.UniqueConstraint(fields=['document', 'version_number'], name='unique_document_version')
       ]
   ```
   Each document maintains an isolated version sequence starting at 1 ($1, 2, 3 \dots$). Document A can have version 1, and Document B can also have version 1, guaranteed unique by the composite constraint.

---

### `core/signals.py` & `core/apps.py`

#### What It Does:
Automates audit logging for every document creation and update.

```python
@receiver(pre_save, sender=Document)
def document_pre_save_receiver(sender, instance, **kwargs):
    # Cache the lifecycle state before SQL INSERT/UPDATE executes
    instance._was_adding = getattr(instance._state, 'adding', False)

@receiver(post_save, sender=Document)
def document_post_save_audit_handler(sender, instance, created, **kwargs):
    is_created = getattr(instance, '_was_adding', None)
    if is_created is None:
        is_created = created or getattr(instance._state, 'adding', False)

    action = 'created' if is_created else 'updated'

    AuditLog.objects.create(
        actor=instance.created_by,
        action=action,
        model_name='Document',
        object_id=str(instance.id),
        details={'title': instance.title, 'status': instance.status}
    )
```

#### Engineering Concepts:
1. **Understanding `instance._state.adding`**:
   `instance._state` is an instance of `ModelState`. When a model object is first instantiated in Python (`doc = Document(...)`), `doc._state.adding = True`. During `save_base()`, Django inspects `self._state.adding` to decide whether to issue an SQL `INSERT` or `UPDATE`. Once the SQL `INSERT` succeeds, Django sets `self._state.adding = False`. Therefore, in `pre_save`, `_state.adding` accurately reflects whether the operation is an insert!
2. **Atomic Context of Signals**:
   Because the document save is executed within `with transaction.atomic():`, the `post_save` signal executes **inside the same database transaction**. If a subsequent line in that atomic block raises an exception, the `AuditLog` row rolls back alongside the document.

---

### `core/serializers.py`

#### What It Does:
Serializers perform bidirectional transformation: converting complex ORM QuerySets into Python primitives/JSON (serialization) and validating incoming JSON payloads against business rules before database persistence (deserialization).

#### Key Implementations:

1. **`SerializerMethodField` Usage**:
   - `WorkspaceSerializer.members_count`: Computes member count dynamically or reads annotated value.
   - `DocumentSerializer.versions_count`: Computes version count dynamically.
   - `DocumentSerializer.comments_count`: Computes total comments attached to the document.
   - `CommentSerializer.replies_count`: Computes total direct replies.

2. **Custom Validation**:
   - **Field-level validation**:
     ```python
     def validate_name(self, value):
         trimmed = value.strip()
         if len(trimmed) < 3:
             raise serializers.ValidationError("Workspace name must be at least 3 characters long.")
         if trimmed.isdigit():
             raise serializers.ValidationError("Workspace name cannot consist solely of digits.")
         return trimmed
     ```
   - **Object-level validation**:
     ```python
     def validate(self, data):
         content = data.get('content', getattr(self.instance, 'content', ''))
         status_val = data.get('status', getattr(self.instance, 'status', Document.Status.DRAFT))
         if status_val == Document.Status.PUBLISHED and (not content or not content.strip()):
             raise serializers.ValidationError({
                 "content": "A document cannot be published with empty content."
             })
         return data
     ```
   - **Threaded Comment Integrity Validation**:
     Validates that if `parent_id` is supplied, `parent.document_id == document.id`, preventing cross-document orphaned comment trees!

---

### `core/views.py`

#### What It Does:
Houses the API controller logic using DRF `ModelViewSet` instances.

#### Key Endpoints & Query Optimizations:

1. **`select_related` on Eager Loading**:
   ```python
   Workspace.objects.select_related('owner')
   Document.objects.select_related('workspace', 'created_by').prefetch_related('tags')
   Comment.objects.select_related('author', 'document', 'parent')
   AuditLog.objects.select_related('actor')
   ```
2. **`Q` Objects for Multi-Field OR Filtering**:
   ```python
   search = params.get('search')
   if search:
       queryset = queryset.filter(Q(title__icontains=search) | Q(content__icontains=search))
   ```
   Compiles into SQL:
   ```sql
   WHERE (UPPER("core_document"."title") LIKE UPPER('%search%') OR UPPER("core_document"."content") LIKE UPPER('%search%'))
   ```
3. **Atomic Workspace Creation with Admin Member**:
   ```python
   with transaction.atomic():
       workspace = serializer.save(owner=owner)
       WorkspaceMember.objects.create(
           workspace=workspace,
           user=owner,
           role=WorkspaceMember.Role.ADMIN
       )
   ```
4. **Duplicate Member Handling with 409 Conflict**:
   ```python
   try:
       with transaction.atomic():
           member = WorkspaceMember.objects.create(workspace=workspace, user=user, role=role)
           return Response(WorkspaceMemberSerializer(member).data, status=status.HTTP_201_CREATED)
   except IntegrityError:
       return Response(
           {"error": f"Conflict: User '{user.username}' is already a member of workspace '{workspace.name}'."},
           status=status.HTTP_409_CONFLICT
       )
   ```
5. **Atomic Document Save + Version Number Calculation**:
   ```python
   with transaction.atomic():
       document = serializer.save()
       version_number = document.versions.count() + 1
       DocumentVersion.objects.create(
           document=document,
           version_number=version_number,
           title=document.title,
           content=document.content,
           created_by=actor
       )
   ```
6. **Aggregations & Annotations with `Count`**:
   - `WorkspaceViewSet.stats`:
     ```python
     stats_data = workspace.documents.aggregate(
         total_documents=Count('id'),
         draft_count=Count('id', filter=Q(status=Document.Status.DRAFT)),
         published_count=Count('id', filter=Q(status=Document.Status.PUBLISHED))
     )
     ```
   - `TagViewSet.get_queryset`:
     ```python
     Tag.objects.annotate(document_count=Count('documents'))
     ```
7. **`values_list()` for Fast Scalar Lookups**:
   ```python
   member_ids = list(workspace.memberships.values_list('user_id', flat=True))
   tag_ids = list(document.tags.values_list('id', flat=True))
   ```

---

### `core/exceptions.py`

#### What It Does:
Custom centralized exception handler that intercepts exceptions raised during view execution and ensures consistent JSON error envelopes.

```json
{
  "success": false,
  "status_code": 409,
  "error": "Conflict: User 'bob' is already a member of workspace 'Design'.",
  "details": null
}
```

It maps unhandled `ObjectDoesNotExist` to `404 NOT FOUND` and unhandled `IntegrityError` to `409 CONFLICT`.

---

### `tests/` Suite

28 unit and integration tests verifying every layer of the architecture:
- `test_models.py`: Validates UUID generation, unique constraints, and self-referential relations.
- `test_views.py`: Tests all 17+ endpoints across the 6 folders, status codes, and search queries.
- `test_transactions.py`: Proves transaction rollback guarantees (ensuring zero leaked records when an operation fails inside `transaction.atomic()`).
- `test_signals.py`: Verifies signal emission and audit logging.
- `test_middleware.py`: Validates timing and stdout format.

---

## 3. Deep-Dive Technical Concepts

### The N+1 Query Problem: `select_related` vs `prefetch_related`

#### The Problem:
Imagine rendering a list of 100 documents, and displaying each document's author and workspace name.
Without optimization:
1. Query 1: `SELECT * FROM core_document LIMIT 100;`
2. For each of the 100 documents:
   - Query: `SELECT * FROM core_user WHERE id = <author_id>;`
   - Query: `SELECT * FROM core_workspace WHERE id = <workspace_id>;`

Total queries: $1 + 200 = 201$ queries! Under high traffic, this exhausts database connection pools and causes latency spikes.

#### The Solution:
- **`select_related` (SQL JOIN)**:
  Used for **single-valued** relationships (`ForeignKey`, `OneToOne`).
  ```python
  Document.objects.select_related('workspace', 'created_by')
  ```
  Generates a single SQL query:
  ```sql
  SELECT core_document.*, core_workspace.*, core_user.*
  FROM core_document
  INNER JOIN core_workspace ON core_document.workspace_id = core_workspace.id
  INNER JOIN core_user ON core_document.created_by_id = core_user.id;
  ```
  Result: Exactly **1 SQL Query**!

- **`prefetch_related` (Separate `IN` Query)**:
  Used for **multi-valued** relationships (`ManyToManyField`, reverse `ForeignKey`).
  ```python
  Document.objects.prefetch_related('tags')
  ```
  Why not an SQL `JOIN`? Joining a ManyToMany table with multiple tags per document creates a Cartesian product, multiplying rows and causing massive memory overhead.
  Instead, Django executes:
  1. `SELECT * FROM core_document;`
  2. `SELECT core_tag.*, core_document_tags.document_id FROM core_tag INNER JOIN core_document_tags ... WHERE core_document_tags.document_id IN (<doc1_id>, <doc2_id>, ...);`
  Django then pairs the tags to each document in Python memory. Total queries: Exactly **2 SQL queries**, regardless of whether there are 10 or 10,000 documents!

---

### ACID Transactions & Atomic Concurrency

CollabDocs uses `django.db.transaction.atomic()` to guarantee ACID guarantees:

1. **Atomicity**: Either all operations in the block succeed, or none do.
2. **Consistency**: Database invariants (foreign keys, check constraints, unique constraints) are never violated.
3. **Isolation**: Concurrent transactions cannot observe partial intermediate states.
4. **Durability**: Once committed, changes survive server crashes or restarts.

```
       +---------------------------------------------+
       |           transaction.atomic()              |
       |                                             |
       | 1. Document.save()                          |
       |    -> Pre-save signal                       |
       |    -> SQL INSERT/UPDATE                     |
       |    -> Post-save signal (AuditLog created)   |
       |                                             |
       | 2. DocumentVersion.create()                 |
       |                                             |
       +---------------------------------------------+
                              |
               +--------------+--------------+
               |                             |
          [SUCCESS]                      [FAILURE]
               |                             |
      COMMIT to Database             ROLLBACK All Changes
      (Doc, Version, AuditLog        (Zero orphaned records
       permanently saved)             in database)
```

#### Under the Hood: Savepoints:
In PostgreSQL and SQLite, nesting `transaction.atomic()` creates **Savepoints**:
```sql
BEGIN;
SAVEPOINT "s1";
-- create document
-- create audit log
-- create version
RELEASE SAVEPOINT "s1";
COMMIT;
```
If an exception occurs within an inner block, Django issues `ROLLBACK TO SAVEPOINT "s1";`, allowing graceful error recovery without aborting the entire outer transaction.

---

### UUIDv4 vs Auto-Incrementing BigInt

CollabDocs mandates `UUIDField(primary_key=True, default=uuid.uuid4, editable=False)` on all 8 models.

| Metric | Auto-Increment (`BigInt`) | UUIDv4 (`UUIDField`) |
|---|---|---|
| **Collision Risk** | Impossible locally | $1 \text{ in } 2^{122}$ (practically zero globally) |
| **Security / Enumeration** | Vulnerable: attacker iterates `/api/documents/1`, `/2` | Immune: unguessable 128-bit random strings |
| **Distributed ID Generation** | Requires central DB sequence (bottleneck) | Client/Worker can generate ID before database write |
| **Storage Size** | 8 bytes | 16 bytes (PostgreSQL native `uuid`) |
| **Index B-Tree Fragmentation** | None (sequential appending) | Moderate (random insertions require B-Tree page splits) |

---

### `UniqueConstraint` vs Legacy `unique_together`

CollabDocs uses:
```python
class Meta:
    constraints = [
        models.UniqueConstraint(fields=['workspace', 'user'], name='unique_workspace_member')
    ]
```

#### Why `unique_together` is Deprecated:
`unique_together = (('workspace', 'user'),)` is legacy Django syntax.
`UniqueConstraint`:
1. Follows ANSI SQL standard naming (`name='unique_workspace_member'`), allowing explicit migration and index management.
2. Supports **Partial / Conditional Unique Indexes**:
   ```python
   UniqueConstraint(fields=['workspace', 'user'], condition=Q(is_active=True), name='unique_active_member')
   ```
3. Supports deferred constraint checks (`deferrable=models.Deferrable.DEFERRED`).

---

### Signal Lifecycle & `instance._state.adding`

Django's `Model.save_base()` lifecycle operates as follows:

```
[ doc.save() called ]
         |
         v
[ pre_save signal emitted ]  ---> doc._state.adding is True if record does not yet exist in DB
         |
         v
[ SQL INSERT or UPDATE executed ]
         |
         v
[ doc._state.adding set to False by Django ORM ]
         |
         v
[ post_save signal emitted ] ---> created=True passed as argument
```

Because `_state.adding` is flipped to `False` by the ORM before `post_save` handlers run, capturing it in `pre_save` guarantees accurate tracking of whether the object was freshly inserted or updated!

---

### Serializers: Internal Lifecycle & Validation Flow

When you call `serializer.is_valid(raise_exception=True)` in DRF:

```
                      [ Incoming JSON Data ]
                                 |
                                 v
                     to_internal_value(data)
           (Converts JSON strings to Python datatypes)
                                 |
                                 v
                    validate_<field_name>(value)
           (Executes field-specific validation methods)
                                 |
                                 v
                          validate(attrs)
           (Executes cross-field object-level validation)
                                 |
                                 v
          +----------------------+----------------------+
          |                                             |
      [ Valid ]                                    [ Invalid ]
          |                                             |
  Populates validated_data                      Raises ValidationError
  Returns True                                  Returns HTTP 400 Bad Request
```

---

### `aggregate()` vs `annotate()`: The SQL Reality

#### `annotate()` (Per-Row Grouping):
Annotates **each row** in the QuerySet with a calculated value. Equivalent to `GROUP BY`.
```python
Tag.objects.annotate(document_count=Count('documents'))
```
Generated SQL:
```sql
SELECT core_tag.id, core_tag.name, COUNT(core_document_tags.document_id) AS document_count
FROM core_tag
LEFT OUTER JOIN core_document_tags ON core_tag.id = core_document_tags.tag_id
GROUP BY core_tag.id, core_tag.name;
```

#### `aggregate()` (Entire QuerySet Collapse):
Collapses the **entire table/QuerySet** into a single dictionary of summary scalars.
```python
workspace.documents.aggregate(total=Count('id'))
```
Generated SQL:
```sql
SELECT COUNT(core_document.id) AS total
FROM core_document
WHERE core_document.workspace_id = '...';
```
Returns: `{'total': 14}`.

---

### Middleware Internals: Onion Request-Response Lifecycle

```
[ Incoming HTTP Request ]
           |
           v
+---------------------------------------+
| SecurityMiddleware                    |
+---------------------------------------+
| SessionMiddleware                     |
+---------------------------------------+
| CommonMiddleware                      |
+---------------------------------------+
| AuthenticationMiddleware              |
+---------------------------------------+
| RequestLoggingMiddleware (start_time) |  <-- Enters our custom middleware
+---------------------------------------+
                   |
                   v
             [ View Execution ]
                   |
                   v
+---------------------------------------+
| RequestLoggingMiddleware (stops clock)|  <-- Calculates duration, prints to stdout
+---------------------------------------+
| SessionMiddleware (saves session)     |
+---------------------------------------+
| SecurityMiddleware (adds headers)     |
+---------------------------------------+
           |
           v
[ Outgoing HTTP Response ]
```

---

## 4. Top 25 Senior/Mid Backend Engineering Interview Questions & Master Answers

### Q1: Why did you use UUIDv4 for primary keys instead of auto-incrementing BigInts?
**Answer**: Auto-incrementing integers leak business intelligence (competitors can deduce total orders/users simply by observing integer IDs) and present severe ID enumeration security vulnerabilities. Furthermore, auto-incrementing IDs require a centralized database sequence lock, which becomes a bottleneck in distributed architectures or sharded databases. UUIDv4 provides 122 bits of cryptographically random entropy, enabling clients or microservices to generate IDs independently before reaching the database without collision risk. In PostgreSQL, UUIDs are natively supported as a 128-bit datatype, ensuring optimal storage and index performance.

---

### Q2: How does `select_related` differ from `prefetch_related` under the hood?
**Answer**: `select_related` performs an SQL `INNER JOIN` or `LEFT OUTER JOIN` in a single database query. It is designed specifically for single-valued relationships (ForeignKey and OneToOne). Conversely, `prefetch_related` executes separate SQL queries (e.g. `WHERE id IN (...)`) and performs the relationship stitching in Python memory. It is used for multi-valued relationships (ManyToMany and reverse ForeignKeys) to prevent the massive Cartesian explosion that occurs when joining multiple tables with one-to-many cardinality.

---

### Q3: What happens when an exception occurs inside a `transaction.atomic()` block?
**Answer**: `transaction.atomic()` functions as a context manager managing database transactions and savepoints. If the code block executes without error, Django commits the transaction. If an unhandled exception is raised, Django catches it, issues an SQL `ROLLBACK` (or `ROLLBACK TO SAVEPOINT`), restores the database connection state, and re-raises the exception. No intermediate writes made inside that block persist to disk.

---

### Q4: Why did we catch `IntegrityError` to return HTTP 409 Conflict instead of doing a `.filter().exists()` check?
**Answer**: Doing `if WorkspaceMember.objects.filter(workspace=ws, user=user).exists(): raise Conflict` suffers from a **Time-of-Check to Time-of-Use (TOCTOU) race condition**. In a concurrent environment with two simultaneous requests, both could pass the `.exists()` check simultaneously, and both would attempt an `INSERT`, causing an unhandled database collision. Relying on the database-level `UniqueConstraint` and catching the resulting `IntegrityError` ensures ACID-compliant concurrency safety at the database engine level.

---

### Q5: What is the purpose of `instance._state.adding` in Django?
**Answer**: `instance._state` is an instance of `ModelState` tracking the lifecycle of an active ORM object. When `_state.adding` is `True`, Django knows the record does not yet exist in the database and must be saved via an SQL `INSERT`. When `False`, Django issues an SQL `UPDATE`. Because Django resets `_state.adding = False` immediately after the SQL INSERT completes, caching this attribute in `pre_save` allows the subsequent `post_save` signal handler to reliably distinguish between record creation and update.

---

### Q6: What is a `SerializerMethodField` in DRF, and what is its performance consideration?
**Answer**: `SerializerMethodField` is a read-only field whose value is calculated by invoking a method on the serializer class (e.g. `get_members_count(self, obj)`). While versatile, if the method issues a database query (e.g. `obj.memberships.count()`), calling this on a serialized list of 100 items will trigger 100 separate database queries (an N+1 query problem). To optimize, we annotate the QuerySet with `Count('memberships')` in `get_queryset()` and have `SerializerMethodField` read the pre-computed attribute if present.

---

### Q7: How does a self-referential ForeignKey model threaded comments, and why did you choose `on_delete=models.SET_NULL`?
**Answer**: A self-referential foreign key points to the model itself (`models.ForeignKey('self', ...)`). Root comments have `parent=None`. Child replies set `parent_id` to the parent comment's UUID, forming an Adjacency List tree. We use `on_delete=models.SET_NULL` (combined with `null=True`) rather than `CASCADE` so that if a parent comment is deleted or moderated, the entire reply sub-tree is not accidentally deleted; instead, replies become detached orphan nodes or indicate `[Comment deleted]`.

---

### Q8: What is the execution order of validation in Django REST Framework?
**Answer**:
1. Field coercion (`to_internal_value`)
2. Field-level validators: methods named `validate_<field_name>(self, value)`
3. Object-level validators: `validate(self, attrs)` where cross-field dependencies are checked
4. Custom validator classes registered in `Meta.validators`
If all pass, the dictionary is accessible via `serializer.validated_data`.

---

### Q9: Why is `values_list('id', flat=True)` faster than `.all()` when inspecting IDs?
**Answer**: Calling `.all()` requires the ORM to allocate full model instances in memory, populate internal dictionaries, set up state trackers, and cast all column values. `values_list('id', flat=True)` bypasses model instantiation entirely; it instructs the database driver to return a raw Python tuple/list of scalar values directly from the database cursor, saving significant CPU and memory overhead.

---

### Q10: How does Django's middleware onion architecture handle exceptions?
**Answer**: As a request travels inward, each middleware's code before `get_response` executes. As the response travels outward, code after `get_response` executes in reverse order. If an exception occurs, Django invokes `process_exception(request, exception)` on any middleware defining it, proceeding up the stack until an `HttpResponse` is returned or the exception handler handles it.

---

### Q11: What is the difference between `ModelViewSet` and raw `APIView`?
**Answer**: `APIView` is low-level, requiring manual definition of `get()`, `post()`, `put()`, `delete()`, explicit serializer validation, and manual QuerySet filtering. `ModelViewSet` inherits from `GenericAPIView` and multiple mixins (`ListModelMixin`, `CreateModelMixin`, `RetrieveModelMixin`, `UpdateModelMixin`, `DestroyModelMixin`), providing standard CRUD workflows, pagination, search filters, and automatic URL wiring via routers while maintaining extension points like `perform_create` and `@action`.

---

### Q12: Why should `SECRET_KEY` and database credentials never be stored in Git?
**Answer**: `SECRET_KEY` is used to sign session cookies, CSRF tokens, and password reset tokens. If compromised, attackers can forge admin session cookies and achieve remote code execution. Database credentials committed to Git can be indexed by public scanners within seconds. Adhering to 12-Factor principles means injecting configuration via environment variables at runtime.

---

### Q13: How do you prevent race conditions when computing `version_number = Document.versions.count() + 1` under high concurrency?
**Answer**: If two users save a document simultaneously, both counts could return $N$, causing a unique constraint violation when both attempt to insert $N+1$. To prevent this in high-concurrency environments, we wrap the read and write in `transaction.atomic()` and execute `Document.objects.select_for_update().get(id=pk)`. This acquires an exclusive row-level lock (`SELECT ... FOR UPDATE`) in PostgreSQL, forcing concurrent transactions to wait until the lock is released.

---

### Q14: What is the difference between `PUT` and `PATCH` in REST API standards?
**Answer**: `PUT` represents a complete idempotent replacement of the target resource; any field omitted in the request payload should be reset to null or default. `PATCH` represents a partial update, modifying only the fields provided in the payload while preserving all other existing attributes.

---

### Q15: Why is `psycopg3` (`psycopg`) preferred over legacy `psycopg2`?
**Answer**: `psycopg3` is a ground-up rewrite of the PostgreSQL adapter for Python. It natively supports Python's asynchronous I/O (`asyncio`), server-side binding, prepared statements, native Python type conversions, connection pooling, and binary protocol data transfers, offering superior performance and compatibility with modern asynchronous Django.

---

### Q16: How does Django prevent SQL Injection in QuerySets?
**Answer**: Django ORM uses parameterized queries (prepared statements). When you run `Document.objects.filter(title=user_input)`, the ORM does not concatenate strings. Instead, it sends the query structure with placeholders (`%s` or `$1`) and passes the user input separately as query parameters, rendering SQL injection impossible.

---

### Q17: What are database migrations, and how does Django know which ones have been applied?
**Answer**: Migrations are Python files representing schema transformations over time. Django maintains a database table called `django_migrations`. Before running migrations, Django queries this table to see which migration files (e.g., `core.0001_initial`) have already executed, and only executes pending migrations in strict dependency order within a transaction.

---

### Q18: What is the difference between `null=True` and `blank=True` in Django models?
**Answer**: `null=True` is database-related; it configures the database column to accept `NULL` values. `blank=True` is validation-related; it dictates whether forms or serializers allow empty values during validation. For string-based fields (`CharField`, `TextField`), Django convention prefers `blank=True, default=""` to avoid having two distinct representations of "no data" (`NULL` vs empty string `""`).

---

### Q19: Why are signals sometimes considered an anti-pattern in large Django systems?
**Answer**: Signals execute synchronously and introduce implicit, invisible side-effects. When an engineer calls `doc.save()`, they might not realize that 5 different signal receivers are sending emails, updating cache, and writing audit logs. In large distributed architectures, explicit domain service layers or asynchronous message queues (e.g. RabbitMQ/Celery) are preferred over complex signal chains.

---

### Q20: What is the purpose of `related_name` in ForeignKeys?
**Answer**: `related_name` defines the attribute name on the target model that accesses the reverse relationship. For example, `document = models.ForeignKey(Document, related_name='versions')` allows `my_doc.versions.all()`. If omitted, Django defaults to `<modelname>_set` (`my_doc.documentversion_set.all()`).

---

### Q21: How does DRF handle pagination, and why is it necessary?
**Answer**: Pagination restricts the number of rows returned in a single HTTP response (e.g., `PAGE_SIZE = 20`). Without pagination, calling `GET /api/documents/` on a table with 1,000,000 rows would fetch all records into server RAM, serializing millions of objects, crashing the Python process with Out-of-Memory (OOM), and timing out the client.

---

### Q22: What is connection pooling, and why is PgBouncer essential for PostgreSQL?
**Answer**: PostgreSQL uses a process-based connection model where each client connection spawns a new OS backend process, consuming 2–10MB of RAM. Creating and destroying connections on every HTTP request introduces significant latency and resource thrashing. PgBouncer maintains a pool of persistent connections to PostgreSQL and multiplexes thousands of lightweight application requests across a small pool of database connections in transaction mode.

---

### Q23: How would you implement Role-Based Access Control (RBAC) in this API?
**Answer**: We implement a custom DRF `BasePermission` class:
```python
class HasWorkspaceRole(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        workspace = obj if isinstance(obj, Workspace) else obj.workspace
        membership = WorkspaceMember.objects.filter(workspace=workspace, user=request.user).first()
        if not membership:
            return False
        if request.method in permissions.SAFE_METHODS:
            return True  # Viewers, Editors, Admins can read
        if request.method in ['PUT', 'PATCH']:
            return membership.role in [WorkspaceMember.Role.ADMIN, WorkspaceMember.Role.EDITOR]
        if request.method == 'DELETE':
            return membership.role == WorkspaceMember.Role.ADMIN
        return False
```

---

### Q24: What is the difference between `django.test.TestCase` and `django.test.TransactionTestCase`?
**Answer**: `TestCase` wraps each test method in an atomic database transaction and rolls it back at the end of the test. It does not commit changes to disk, making it extremely fast. `TransactionTestCase` resets the database by truncating tables between tests, which is slower but required when testing actual multi-threaded code or explicit transaction commits.

---

### Q25: How would you scale this API to support 100,000 concurrent users?
**Answer**:
1. **Stateless API Web Tier**: Deploy behind an Nginx / AWS ALB load balancer running multiple Gunicorn or Uvicorn worker instances across auto-scaling containers (Kubernetes).
2. **Database Read Replicas**: Direct all read traffic (`GET`) to PostgreSQL read replicas using Django database routers (`db_for_read()`), reserving the primary database node strictly for write transactions (`POST`, `PUT`, `DELETE`).
3. **In-Memory Caching**: Cache expensive aggregations (`/stats/`, `/summary/`) and static workspaces in Redis with time-to-live (TTL) and cache-invalidation triggers on document mutations.
4. **Asynchronous Background Processing**: Offload audit logging, email notifications, and document export tasks to Celery workers backed by Redis or RabbitMQ.
5. **Connection Pooling**: Place PgBouncer in front of PostgreSQL to manage thousands of incoming database queries without exhausting connection limits.



---

## 5. Comprehensive Assignment Objectives Mapping & Mastery Matrix

This section maps each core objective from the CollabDocs specification directly to its implementation, internal mechanics, underlying database operations, and interview relevance.

```
+----------------------------------------------------------------------------------------------------------------------+
|                                     CollabDocs Assignment Objectives Map                                             |
+------------------------------------+-------------------------------------------+-------------------------------------+
| Objective Category                 | Key Mechanisms                            | Code Location                       |
+------------------------------------+-------------------------------------------+-------------------------------------+
| 1. Relational Integrity & Schema   | UUID4 PKs, TextChoices, UniqueConstraints | core/models.py                      |
| 2. API Controllers & Serializers   | ModelViewSet, @action, SerializerMethod   | core/views.py, core/serializers.py  |
| 3. Query Optimization & Filtering  | select_related, Q objects, annotate/aggreg| core/views.py                       |
| 4. ACID Transactions & Concurrency | transaction.atomic(), rollback, 409 error | core/views.py, core/exceptions.py   |
| 5. Middleware & Event Signals      | RequestLoggingMiddleware, post_save audit | collabdocs/middleware.py, signals.py|
| 6. Setup & Rubric Compliance       | PostgreSQL .env, 28 tests, Postman json   | .env.example, tests/, postman.json  |
+------------------------------------+-------------------------------------------+-------------------------------------+
```

---

### Objective 1: Data Model Design & Relational Integrity (Sections 2 & 4.1)

#### 1.1 Auto-Generated UUID4 Primary Keys
- **Assignment Mandate**: All primary keys must be `UUIDField` with auto-generation and `editable=False`.
- **Implementation**:
  ```python
  id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
  ```
- **How It Works**:
  Instead of an auto-incrementing integer (`1, 2, 3`), Python's `uuid.uuid4()` generates 128 random bits conforming to RFC 4122 (Version 4).
- **SQL Representation (PostgreSQL)**:
  ```sql
  "id" uuid NOT NULL PRIMARY KEY
  ```
- **Why Interviewers Care**:
  - Eliminates enumeration attacks (`/api/documents/1` vs `/api/documents/f47ac10b-58cc-4372-a567-0e02b2c3d479`).
  - Supports client-side ID generation and distributed microservice writes without a central sequence coordinator.

#### 1.2 `models.TextChoices` Enumerations
- **Assignment Mandate**: Use `TextChoices` for all enums—no raw string values (`Document.status`, `WorkspaceMember.role`).
- **Implementation**:
  ```python
  class Role(models.TextChoices):
      ADMIN = 'admin', 'Admin'
      EDITOR = 'editor', 'Editor'
      VIEWER = 'viewer', 'Viewer'
  ```
- **How It Works**:
  `TextChoices` is a subclass of Python's `Enum` with Django-specific metadata. It exposes:
  - `Role.values`: `['admin', 'editor', 'viewer']`
  - `Role.choices`: `[('admin', 'Admin'), ('editor', 'Editor'), ...]`
  - `Role.labels`: `['Admin', 'Editor', 'Viewer']`
- **Why Interviewers Care**:
  Prevents typographical errors ("Admn"), standardizes validation in serializers, and maintains self-documenting code across backend and API documentation.

#### 1.3 Composite `UniqueConstraint` on `(workspace, user)` and `(document, version_number)`
- **Assignment Mandate**: Implement `UniqueConstraint` in model Meta classes.
- **Implementation**:
  ```python
  class Meta:
      constraints = [
          models.UniqueConstraint(fields=['workspace', 'user'], name='unique_workspace_member')
      ]
  ```
- **SQL Representation (PostgreSQL)**:
  ```sql
  ALTER TABLE "core_workspacemember"
  ADD CONSTRAINT "unique_workspace_member" UNIQUE ("workspace_id", "user_id");
  ```
- **Why Interviewers Care**:
  Guarantees integrity at the database storage engine layer (creating a unique B-Tree index) rather than relying on error-prone application-level validation.

#### 1.4 Self-Referential Threaded Comments (`parent = models.ForeignKey('self')`)
- **Assignment Mandate**: Self-referential FK with `null=True, blank=True, on_delete=models.SET_NULL, related_name='replies'`.
- **Implementation**:
  ```python
  parent = models.ForeignKey(
      'self',
      null=True,
      blank=True,
      on_delete=models.SET_NULL,
      related_name='replies'
  )
  ```
- **How It Works (Adjacency List Tree Pattern)**:
  - Top-level comment: `parent = None`
  - Reply: `parent = <Parent_Comment_Instance>`
  - Reverse query: `parent_comment.replies.all()` returns all direct children.
- **Why `SET_NULL`**: If a parent comment is deleted, child comments are not wiped out via cascade; their `parent_id` is set to `NULL`, maintaining thread continuity.

#### 1.5 Many-to-Many Tags Join Table
- **Assignment Mandate**: `ManyToManyField` between `Tag` and `Document`.
- **Implementation**:
  ```python
  tags = models.ManyToManyField(Tag, related_name='documents', blank=True)
  ```
- **How It Works**:
  Django automatically creates an intermediary join table `core_document_tags` containing `id`, `document_id`, and `tag_id`, with a composite unique index on `(document_id, tag_id)`.

---

### Objective 2: API Architecture & Serializers (Sections 3 & 4.2)

#### 2.1 Standardized CRUD with `ModelViewSet`
- **Assignment Mandate**: Use `ModelViewSet` wherever CRUD is standard; do not use raw `APIView`.
- **Why ModelViewSet?**:
  `ModelViewSet` bundles:
  - `list()` $\to$ `GET /api/workspaces/`
  - `create()` $\to$ `POST /api/workspaces/`
  - `retrieve()` $\to$ `GET /api/workspaces/{id}/`
  - `update()` $\to$ `PUT /api/workspaces/{id}/`
  - `partial_update()` $\to$ `PATCH /api/workspaces/{id}/`
  - `destroy()` $\to$ `DELETE /api/workspaces/{id}/`
  This drastically reduces boilerplate code while adhering to uniform HTTP semantics.

#### 2.2 Custom Endpoints with `@action`
- **Assignment Mandate**: Use `@action` decorators for non-standard endpoints (`stats`, `summary`, `tags`, `versions`, `members`).
- **Implementation Example**:
  ```python
  @action(detail=True, methods=['get'], url_path='stats')
  def stats(self, request, pk=None):
      ...
  ```
  - `detail=True`: Binds the action to a specific instance (`/api/workspaces/{id}/stats/`).
  - `detail=False`: Binds the action to the collection root (`/api/workspaces/stats/`).

#### 2.3 `SerializerMethodField` Usages
- **Assignment Mandate**: At least two `SerializerMethodField` uses across the project.
- **Implementation**:
  1. `WorkspaceSerializer.members_count`: Computes active members.
  2. `DocumentSerializer.versions_count`: Computes total historical versions.
  3. `DocumentSerializer.comments_count`: Computes total comments attached.
  4. `CommentSerializer.replies_count`: Computes direct child replies.
- **How It Works**:
  When DRF serializes an instance, it looks for a method `get_<field_name>(self, obj)` on the serializer and injects its return value into the output JSON.

#### 2.4 Custom Field-Level & Object-Level Validation
- **Assignment Mandate**: Custom validation in at least two serializers.
- **Implementation**:
  - `WorkspaceSerializer.validate_name`: Ensures workspace names are at least 3 characters and not solely numeric digits.
  - `DocumentSerializer.validate`: Enforces that documents marked as `PUBLISHED` cannot have empty or whitespace-only content.
  - `CommentSerializer.validate`: Enforces that a reply's parent comment belongs to the exact same document.

---

### Objective 3: QuerySets & Query Optimization (Section 4.3)

#### 3.1 Eager Loading with `select_related`
- **Assignment Mandate**: Use `select_related` on every endpoint returning nested user, workspace, or document data.
- **Under the Hood**:
  ```python
  Document.objects.select_related('workspace', 'created_by')
  ```
  Executes an SQL `INNER JOIN` in 1 query instead of 3 queries per row.
- **Performance Impact**:
  For 100 documents:
  - Without `select_related`: $1 + 100 + 100 = 201$ queries ($O(N)$).
  - With `select_related`: Exactly $1$ query ($O(1)$).

#### 3.2 Complex OR Queries with `Q` Objects
- **Assignment Mandate**: Use `Q` objects for OR filtering on the document list endpoint.
- **Implementation**:
  ```python
  search = self.request.query_params.get('search')
  if search:
      queryset = queryset.filter(Q(title__icontains=search) | Q(content__icontains=search))
  ```
- **Under the Hood**:
  Django compiles `Q(A) | Q(B)` into SQL:
  ```sql
  WHERE (UPPER("core_document"."title") LIKE UPPER('%term%') OR UPPER("core_document"."content") LIKE UPPER('%term%'))
  ```

#### 3.3 Aggregations & Annotations with `Count`
- **Assignment Mandate**: Use `aggregate()` or `annotate()` with `Count` in at least 3 endpoints.
- **Implementation**:
  1. `WorkspaceViewSet.stats`:
     ```python
     workspace.documents.aggregate(
         total_documents=Count('id'),
         draft_count=Count('id', filter=Q(status=Document.Status.DRAFT)),
         published_count=Count('id', filter=Q(status=Document.Status.PUBLISHED))
     )
     ```
  2. `DocumentViewSet.summary`:
     ```python
     Document.objects.filter(id=document.id).aggregate(
         versions_count=Count('versions', distinct=True),
         comments_count=Count('comments', distinct=True)
     )
     ```
  3. `TagViewSet.get_queryset`:
     ```python
     Tag.objects.annotate(document_count=Count('documents'))
     ```
  4. `WorkspaceViewSet.get_queryset`:
     ```python
     Workspace.objects.annotate(annotated_members_count=Count('memberships', distinct=True))
     ```

#### 3.4 Efficient Scalar Lookups with `values_list()`
- **Assignment Mandate**: Use `values_list()` where only IDs are needed.
- **Implementation**:
  ```python
  member_ids = list(workspace.memberships.values_list('user_id', flat=True))
  tag_ids = list(document.tags.values_list('id', flat=True))
  ```
- **Performance Benefit**:
  Bypasses the instantiation of hundreds of Python model objects, reducing memory footprint by up to 80% on batch lookups.

---

### Objective 4: Transactions & Data Integrity (Section 4.4)

#### 4.1 Atomic Workspace & Owner Admin Creation
- **Assignment Mandate**: Workspace creation and owner added as admin member in a single `transaction.atomic()`.
- **Implementation**:
  ```python
  with transaction.atomic():
      workspace = serializer.save(owner=owner)
      WorkspaceMember.objects.create(
          workspace=workspace,
          user=owner,
          role=WorkspaceMember.Role.ADMIN
      )
  ```
- **Guarantee**: If creating the `WorkspaceMember` fails, the `Workspace` row is rolled back immediately. No orphan workspace can exist without an owner.

#### 4.2 Atomic Document Save & Per-Document Version Calculation
- **Assignment Mandate**: Every save must create a new `DocumentVersion` inside the same `transaction.atomic()` block with `version_number = Document.versions.count() + 1`.
- **Implementation**:
  ```python
  with transaction.atomic():
      document = serializer.save()
      version_number = document.versions.count() + 1
      DocumentVersion.objects.create(
          document=document,
          version_number=version_number,
          title=document.title,
          content=document.content,
          created_by=actor
      )
  ```
- **Guarantee**: The version number starts at 1 for new documents and increments monotonically per document. The document update and version creation succeed together or fail together.

#### 4.3 Explicit `IntegrityError` Handling & HTTP 409 Conflict
- **Assignment Mandate**: Catch `IntegrityError` on `WorkspaceMember` creation to return HTTP 409 Conflict when a duplicate member is added.
- **Implementation**:
  ```python
  try:
      with transaction.atomic():
          member = WorkspaceMember.objects.create(workspace=workspace, user=user, role=role)
          return Response(WorkspaceMemberSerializer(member).data, status=status.HTTP_201_CREATED)
  except IntegrityError:
      return Response(
          {"error": f"Conflict: User '{user.username}' is already a member of workspace '{workspace.name}'."},
          status=status.HTTP_409_CONFLICT
      )
  ```

---

### Objective 5: Observability & Signals (Sections 3.1 & 4.5)

#### 5.1 Request Latency Logging Middleware
- **Assignment Mandate**: Class-based middleware recording method, path, response status, and duration in ms.
- **Implementation**:
  ```python
  class RequestLoggingMiddleware:
      def __init__(self, get_response):
          self.get_response = get_response

      def __call__(self, request):
          start = time.perf_counter()
          response = self.get_response(request)
          duration = (time.perf_counter() - start) * 1000.0
          print(f"[CollabDocs Logger] Method: {request.method} | Path: {request.path} | Status: {response.status_code} | Time: {duration:.2f}ms")
          return response
  ```

#### 5.2 Document `post_save` Signal & `instance._state.adding`
- **Assignment Mandate**: `post_save` signal on `Document` in `signals.py`, connected in `AppConfig.ready()`, using `instance._state.adding` to distinguish created vs updated, recording `actor`, `action`, `model_name`, `object_id`.
- **Implementation**:
  ```python
  @receiver(pre_save, sender=Document)
  def document_pre_save_receiver(sender, instance, **kwargs):
      instance._was_adding = getattr(instance._state, 'adding', False)

  @receiver(post_save, sender=Document)
  def document_post_save_audit_handler(sender, instance, created, **kwargs):
      is_created = getattr(instance, '_was_adding', None)
      if is_created is None:
          is_created = created or getattr(instance._state, 'adding', False)

      action = 'created' if is_created else 'updated'

      AuditLog.objects.create(
          actor=instance.created_by,
          action=action,
          model_name='Document',
          object_id=str(instance.id),
          details={'title': instance.title, 'status': instance.status}
      )
  ```
- **Connection**:
  ```python
  class CoreConfig(AppConfig):
      name = 'core'
      def ready(self):
          import core.signals
  ```

---

### Objective 6: Project Setup & Submission Compliance (Section 4.6 & 6)

| Rubric Requirement | Verification & Location |
|---|---|
| **PostgreSQL via `.env`** | Configured in [settings.py](file:///c:/Users/yoges/python-collabdocs/collabdocs/settings.py) reading `.env` via `python-dotenv`. Documented in [.env.example](file:///c:/Users/yoges/python-collabdocs/.env.example). |
| **requirements.txt pinned** | Fully pinned: Django 6.1.0, DRF 3.18.0, psycopg-binary 3.3.4, python-dotenv 1.2.4, etc. |
| **Migrations applying cleanly** | `0001_initial.py` applied cleanly from scratch with zero errors. |
| **Postman collection (.json)** | [CollabDocs.postman_collection.json](file:///c:/Users/yoges/python-collabdocs/CollabDocs.postman_collection.json) covering all 17+ endpoints organized into the 6 required folders. |
| **Automated Tests** | 28 automated tests covering all 17+ endpoints, transactions, rollbacks, signals, and middleware. |
| **Demo Video Guide** | Comprehensive 4-point demo walkthrough script in [README.md](file:///c:/Users/yoges/python-collabdocs/README.md#8-demo-video-guide-510-minutes). |
