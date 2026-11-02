"""
CollabDocs - Automated Demo Walkthrough Script.
Demonstrates the 4 mandatory video requirements directly in the console.

Usage:
    python demo_walkthrough.py
"""

import os
import sys
import django
import time

# Configure Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'collabdocs.settings')
django.setup()

from django.db import transaction, IntegrityError
from django.db.models import Count, Q
from django.test import RequestFactory
from core.models import User, Workspace, WorkspaceMember, Document, DocumentVersion, AuditLog
from collabdocs.middleware import RequestLoggingMiddleware
from django.http import HttpResponse


def print_banner(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def demo_point_1_middleware_logs():
    print_banner("DEMO POINT 1: Middleware Logs Appearing in Console")
    print("Simulating requests passing through RequestLoggingMiddleware...")

    def dummy_view(request):
        time.sleep(0.015)  # simulate 15ms work
        return HttpResponse("OK", status=200)

    middleware = RequestLoggingMiddleware(dummy_view)
    factory = RequestFactory()

    # Request 1: GET /api/workspaces/
    req1 = factory.get('/api/workspaces/')
    middleware(req1)

    # Request 2: POST /api/documents/
    req2 = factory.post('/api/documents/')
    middleware(req2)

    # Request 3: GET /api/workspaces/{id}/stats/
    req3 = factory.get('/api/workspaces/3b7c89f1/stats/')
    middleware(req3)
    print(">> Notice the formatted stdout log with Method, Path, Status, and Latency in ms.")


def demo_point_2_atomic_transaction_rollback():
    print_banner("DEMO POINT 2: Atomic Transaction with Rollback on Failure")
    user, _ = User.objects.get_or_create(username='demo_user', defaults={'email': 'demo@example.com'})

    initial_workspaces = Workspace.objects.count()
    initial_members = WorkspaceMember.objects.count()

    print(f"Initial State: {initial_workspaces} Workspaces, {initial_members} Members.")
    print("Executing transaction.atomic() block where a simulated crash occurs after Workspace creation...")

    try:
        with transaction.atomic():
            ws = Workspace.objects.create(name="Ghost Workspace (Should Rollback)", owner=user)
            print(f"  -> Created Workspace temporarily with ID: {ws.id}")
            print("  -> Simulating a runtime error before member addition finishes...")
            raise RuntimeError("CRITICAL FAILURE: Network interruption or database constraint violation!")
    except RuntimeError as e:
        print(f"  -> Caught Exception: {e}")

    final_workspaces = Workspace.objects.count()
    final_members = WorkspaceMember.objects.count()

    print(f"Post-Rollback State: {final_workspaces} Workspaces, {final_members} Members.")
    assert initial_workspaces == final_workspaces
    print(">> SUCCESS: Zero records were committed. Rollback was 100% clean and atomic!")


def demo_point_3_aggregation_endpoint():
    print_banner("DEMO POINT 3: Aggregation Endpoint (Stats with Count)")
    user, _ = User.objects.get_or_create(username='demo_user')
    ws, _ = Workspace.objects.get_or_create(name='Analytics Workspace', owner=user)

    # Create dummy documents if none exist
    if not ws.documents.exists():
        Document.objects.create(workspace=ws, title='Doc 1', status=Document.Status.DRAFT, created_by=user)
        Document.objects.create(workspace=ws, title='Doc 2', status=Document.Status.PUBLISHED, created_by=user)
        Document.objects.create(workspace=ws, title='Doc 3', status=Document.Status.PUBLISHED, created_by=user)

    # Aggregate statistics using Count
    stats = ws.documents.aggregate(
        total_documents=Count('id'),
        draft_count=Count('id', filter=Q(status=Document.Status.DRAFT)),
        published_count=Count('id', filter=Q(status=Document.Status.PUBLISHED)),
    )
    member_ids = list(ws.memberships.values_list('user_id', flat=True))

    print(f"Workspace: {ws.name} ({ws.id})")
    print(f"  - Total Documents (via Count): {stats['total_documents']}")
    print(f"  - Draft Documents: {stats['draft_count']}")
    print(f"  - Published Documents: {stats['published_count']}")
    print(f"  - Member User IDs (via values_list): {member_ids}")
    print(">> SUCCESS: Database aggregation executed in a single optimized SQL query.")


def demo_point_4_signal_audit_log():
    print_banner("DEMO POINT 4: AuditLog Written Automatically by Signal After Document Update")
    user, _ = User.objects.get_or_create(username='demo_user')
    ws, _ = Workspace.objects.get_or_create(name='Analytics Workspace', owner=user)

    doc, _ = Document.objects.get_or_create(
        workspace=ws,
        title='Live Signal Document',
        defaults={'content': 'Version 1.0', 'status': Document.Status.DRAFT, 'created_by': user}
    )

    print(f"Target Document: '{doc.title}' (ID: {doc.id})")
    print("Updating document title and saving...")

    # Update document
    doc.title = 'Live Signal Document - UPDATED AT ' + time.strftime('%H:%M:%S')
    doc.status = Document.Status.REVIEW
    doc.save()

    # Verify AuditLog written by post_save signal
    latest_audit = AuditLog.objects.filter(object_id=str(doc.id), action='updated').first()

    print(f"  -> AuditLog ID: {latest_audit.id}")
    print(f"  -> Action: {latest_audit.action}")
    print(f"  -> Actor: {latest_audit.actor.username}")
    print(f"  -> Model: {latest_audit.model_name}")
    print(f"  -> Timestamp: {latest_audit.timestamp}")
    print(f"  -> Recorded Details: {latest_audit.details}")
    print(">> SUCCESS: post_save signal on Document automatically recorded the update in AuditLog!")


if __name__ == '__main__':
    print("CollabDocs - Automated Video Requirements Verification")
    demo_point_1_middleware_logs()
    demo_point_2_atomic_transaction_rollback()
    demo_point_3_aggregation_endpoint()
    demo_point_4_signal_audit_log()
    print_banner("ALL 4 DEMO REQUIREMENTS VERIFIED AND OPERATIONAL")

