from django.test import TestCase
from core.models import User, Workspace, Document, AuditLog


class SignalAuditLogTests(TestCase):
    """
    Section 4.5 & 6.3 Requirement:
    Verifies that the post_save signal on Document automatically generates AuditLog entries
    for both document creation and document update.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username='signal_user',
            email='signal@example.com',
            password='Password123!'
        )
        self.workspace = Workspace.objects.create(
            name='Signal Workspace',
            owner=self.user
        )

    def test_document_creation_triggers_audit_log(self):
        """Verify post_save signal creates AuditLog with action='created'."""
        doc = Document.objects.create(
            workspace=self.workspace,
            title='Audited Document Create',
            content='Initial draft content',
            status=Document.Status.DRAFT,
            created_by=self.user
        )

        audit_entry = AuditLog.objects.filter(
            object_id=str(doc.id),
            action='created'
        ).first()

        self.assertIsNotNone(audit_entry)
        self.assertEqual(audit_entry.actor, self.user)
        self.assertEqual(audit_entry.model_name, 'Document')
        self.assertEqual(audit_entry.details.get('title'), 'Audited Document Create')

    def test_document_update_triggers_audit_log(self):
        """Verify post_save signal creates AuditLog with action='updated'."""
        doc = Document.objects.create(
            workspace=self.workspace,
            title='Original Title',
            content='Original content',
            status=Document.Status.DRAFT,
            created_by=self.user
        )

        # Update the document
        doc.title = 'Updated Document Title'
        doc.status = Document.Status.REVIEW
        doc.save()

        update_audit = AuditLog.objects.filter(
            object_id=str(doc.id),
            action='updated'
        ).first()

        self.assertIsNotNone(update_audit)
        self.assertEqual(update_audit.actor, self.user)
        self.assertEqual(update_audit.model_name, 'Document')
        self.assertEqual(update_audit.details.get('title'), 'Updated Document Title')
        self.assertEqual(update_audit.details.get('status'), Document.Status.REVIEW)

