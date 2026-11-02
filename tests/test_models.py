import uuid
from django.test import TestCase
from django.db import IntegrityError
from core.models import (
    User, Workspace, WorkspaceMember, Tag,
    Document, DocumentVersion, Comment, AuditLog
)


class ModelTests(TestCase):
    """
    Test suite for CollabDocs 8 Models, UUID Primary Keys, TextChoices, and Constraints.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username='alice',
            email='alice@example.com',
            password='Password123!'
        )
        self.user2 = User.objects.create_user(
            username='bob',
            email='bob@example.com',
            password='Password123!'
        )
        self.workspace = Workspace.objects.create(
            name='Engineering',
            description='Tech workspace',
            owner=self.user,
            is_active=True
        )

    def test_all_models_have_valid_uuid_primary_keys(self):
        """Verify all 8 models use valid UUID4 primary keys."""
        member = WorkspaceMember.objects.create(
            workspace=self.workspace,
            user=self.user,
            role=WorkspaceMember.Role.ADMIN
        )
        tag = Tag.objects.create(name='python')
        doc = Document.objects.create(
            workspace=self.workspace,
            title='Architecture Guide',
            content='Backend docs',
            status=Document.Status.DRAFT,
            created_by=self.user
        )
        doc.tags.add(tag)
        version = DocumentVersion.objects.create(
            document=doc,
            version_number=1,
            title=doc.title,
            content=doc.content,
            created_by=self.user
        )
        comment = Comment.objects.create(
            document=doc,
            author=self.user,
            content='Initial comment'
        )
        audit = AuditLog.objects.create(
            actor=self.user,
            action='created',
            model_name='Document',
            object_id=str(doc.id)
        )

        for obj in [self.user, self.workspace, member, tag, doc, version, comment, audit]:
            self.assertIsInstance(obj.id, uuid.UUID)

    def test_workspace_member_unique_constraint(self):
        """Verify UniqueConstraint on (workspace, user) raises IntegrityError on duplicates."""
        WorkspaceMember.objects.create(
            workspace=self.workspace,
            user=self.user,
            role=WorkspaceMember.Role.ADMIN
        )
        with self.assertRaises(IntegrityError):
            WorkspaceMember.objects.create(
                workspace=self.workspace,
                user=self.user,
                role=WorkspaceMember.Role.EDITOR
            )

    def test_document_version_unique_constraint(self):
        """Verify UniqueConstraint on (document, version_number) prevents duplicate versions."""
        doc = Document.objects.create(
            workspace=self.workspace,
            title='Doc A',
            created_by=self.user
        )
        DocumentVersion.objects.create(
            document=doc,
            version_number=1,
            title='v1',
            created_by=self.user
        )
        with self.assertRaises(IntegrityError):
            DocumentVersion.objects.create(
                document=doc,
                version_number=1,
                title='v1 duplicate',
                created_by=self.user
            )

    def test_comment_self_referential_foreign_key(self):
        """Verify threaded comments using self-referential parent FK."""
        doc = Document.objects.create(
            workspace=self.workspace,
            title='Doc Threads',
            created_by=self.user
        )
        top_comment = Comment.objects.create(
            document=doc,
            author=self.user,
            content='Top level thread'
        )
        reply_comment = Comment.objects.create(
            document=doc,
            author=self.user2,
            content='Reply thread',
            parent=top_comment
        )
        self.assertIsNone(top_comment.parent)
        self.assertEqual(reply_comment.parent, top_comment)
        self.assertEqual(top_comment.replies.count(), 1)
        self.assertEqual(top_comment.replies.first(), reply_comment)

    def test_tag_many_to_many_with_document(self):
        """Verify ManyToMany relationship between Tag and Document."""
        doc = Document.objects.create(
            workspace=self.workspace,
            title='Tag Doc',
            created_by=self.user
        )
        tag1 = Tag.objects.create(name='django')
        tag2 = Tag.objects.create(name='api')
        doc.tags.add(tag1, tag2)

        self.assertEqual(doc.tags.count(), 2)
        self.assertEqual(Document.objects.filter(tags__name='django').count(), 1)

