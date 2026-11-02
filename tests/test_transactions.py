from django.test import TestCase
from django.db import transaction, IntegrityError
from core.models import User, Workspace, WorkspaceMember, Document, DocumentVersion


class TransactionRollbackTests(TestCase):
    """
    Section 6.3 Demo & Section 4.4 Requirement:
    Demonstrates complete atomic transactions with rollback on failure.
    Guarantees no orphaned or partial records when an error occurs inside transaction.atomic().
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username='trans_user',
            email='trans@example.com',
            password='Password123!'
        )

    def test_workspace_and_member_atomic_rollback(self):
        """
        Verify that if member creation fails within transaction.atomic(),
        the workspace creation rolls back completely.
        """
        initial_workspaces_count = Workspace.objects.count()
        initial_members_count = WorkspaceMember.objects.count()

        try:
            with transaction.atomic():
                # Step 1: Create workspace
                workspace = Workspace.objects.create(
                    name='Rollback Workspace',
                    owner=self.user
                )

                # Step 2: Simulate failure (e.g. invalid operation or forced exception)
                raise ValueError("Simulated unexpected failure during membership assignment!")

                # Step 3: This won't be reached
                WorkspaceMember.objects.create(
                    workspace=workspace,
                    user=self.user,
                    role=WorkspaceMember.Role.ADMIN
                )
        except ValueError:
            pass

        # Verification: Neither workspace nor member exists in the database
        self.assertEqual(Workspace.objects.count(), initial_workspaces_count)
        self.assertEqual(WorkspaceMember.objects.count(), initial_members_count)
        self.assertFalse(Workspace.objects.filter(name='Rollback Workspace').exists())

    def test_document_and_version_atomic_rollback(self):
        """
        Verify that if version creation fails within transaction.atomic(),
        the document creation rolls back completely.
        """
        workspace = Workspace.objects.create(name='Valid WS', owner=self.user)
        initial_docs_count = Document.objects.count()
        initial_versions_count = DocumentVersion.objects.count()

        try:
            with transaction.atomic():
                doc = Document.objects.create(
                    workspace=workspace,
                    title='Uncommitted Document',
                    content='Content that should roll back',
                    created_by=self.user
                )

                # Simulate a failure before version creation finishes
                raise RuntimeError("Simulated database timeout or version collision!")

                DocumentVersion.objects.create(
                    document=doc,
                    version_number=1,
                    title=doc.title,
                    created_by=self.user
                )
        except RuntimeError:
            pass

        # Verification: Document creation was rolled back cleanly
        self.assertEqual(Document.objects.count(), initial_docs_count)
        self.assertEqual(DocumentVersion.objects.count(), initial_versions_count)
        self.assertFalse(Document.objects.filter(title='Uncommitted Document').exists())

