from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from core.models import (
    User, Workspace, WorkspaceMember, Tag,
    Document, DocumentVersion, Comment, AuditLog
)


class ViewSetTests(TestCase):
    """
    Comprehensive test suite covering all 17+ endpoints across the 6 folders:
    Users, Workspaces, Documents, Comments, Tags, Audit Logs.
    """

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='johndoe',
            email='john@example.com',
            password='SecretPassword123!'
        )
        self.user2 = User.objects.create_user(
            username='janedoe',
            email='jane@example.com',
            password='SecretPassword123!'
        )
        self.workspace = Workspace.objects.create(
            name='Design Workspace',
            description='Design team documents',
            owner=self.user,
            is_active=True
        )
        WorkspaceMember.objects.create(
            workspace=self.workspace,
            user=self.user,
            role=WorkspaceMember.Role.ADMIN
        )

    # ==========================================
    # Folder 1: Users
    # ==========================================
    def test_01_list_users(self):
        """Endpoint 1: GET /api/users/"""
        response = self.client.get('/api/users/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data.get('results', response.data)), 2)

    def test_02_create_user(self):
        """Endpoint 2: POST /api/users/"""
        payload = {
            "username": "alex",
            "email": "alex@example.com",
            "password": "StrongPassword999!"
        }
        response = self.client.post('/api/users/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['username'], 'alex')

    def test_03_retrieve_user(self):
        """Endpoint 3: GET /api/users/{id}/"""
        response = self.client.get(f'/api/users/{self.user.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['username'], 'johndoe')

    # ==========================================
    # Folder 2: Workspaces
    # ==========================================
    def test_04_list_workspaces_and_filter(self):
        """Endpoint 4: GET /api/workspaces/ with filters"""
        response = self.client.get('/api/workspaces/?is_active=true&name=Design')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', response.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['name'], 'Design Workspace')

    def test_05_create_workspace_atomic(self):
        """Endpoint 5: POST /api/workspaces/ (Atomic owner + admin member)"""
        payload = {
            "name": "Frontend Team",
            "description": "React and UI work",
            "owner_id": str(self.user.id)
        }
        response = self.client.post('/api/workspaces/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        ws_id = response.data['id']

        # Verify owner was automatically added as admin member in atomic block
        membership = WorkspaceMember.objects.filter(workspace_id=ws_id, user=self.user).first()
        self.assertIsNotNone(membership)
        self.assertEqual(membership.role, WorkspaceMember.Role.ADMIN)

    def test_06_retrieve_workspace(self):
        """Endpoint 6: GET /api/workspaces/{id}/"""
        response = self.client.get(f'/api/workspaces/{self.workspace.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'Design Workspace')
        self.assertIn('members_count', response.data)

    def test_07_add_workspace_member_success_and_duplicate_409(self):
        """Endpoint 7: POST /api/workspaces/{id}/members/ (Tests 201 & 409 Conflict)"""
        # Success: Add user2 as editor
        payload = {
            "user_id": str(self.user2.id),
            "role": "editor"
        }
        response = self.client.post(f'/api/workspaces/{self.workspace.id}/members/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['role'], 'editor')

        # Conflict: Re-add user2 to verify Section 4.4 IntegrityError -> 409 Conflict handling
        response_dup = self.client.post(f'/api/workspaces/{self.workspace.id}/members/', payload, format='json')
        self.assertEqual(response_dup.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("already a member", response_dup.data['error'])

    def test_08_workspace_stats(self):
        """Endpoint 8: GET /api/workspaces/{id}/stats/ (Aggregation with Count)"""
        Document.objects.create(
            workspace=self.workspace,
            title='Spec Doc',
            status=Document.Status.PUBLISHED,
            created_by=self.user
        )
        response = self.client.get(f'/api/workspaces/{self.workspace.id}/stats/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('document_statistics', response.data)
        self.assertEqual(response.data['document_statistics']['total_documents'], 1)
        self.assertEqual(response.data['document_statistics']['published_count'], 1)
        self.assertIn('member_user_ids', response.data)

    # ==========================================
    # Folder 3: Documents
    # ==========================================
    def test_09_list_documents_with_q_search_and_filters(self):
        """Endpoint 9: GET /api/documents/ with Q OR search and lookups"""
        doc1 = Document.objects.create(
            workspace=self.workspace,
            title='Backend Guidelines',
            content='Django REST Framework patterns',
            status=Document.Status.DRAFT,
            created_by=self.user
        )
        doc2 = Document.objects.create(
            workspace=self.workspace,
            title='Frontend Roadmap',
            content='Next.js and Tailwind CSS',
            status=Document.Status.REVIEW,
            created_by=self.user
        )

        # Test Q OR filter: searches both title and content
        response = self.client.get('/api/documents/?search=Framework')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', response.data)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['title'], 'Backend Guidelines')

        # Test status__in filter
        response_status = self.client.get('/api/documents/?status__in=draft,review')
        results_status = response_status.data.get('results', response_status.data)
        self.assertEqual(len(results_status), 2)

    def test_10_create_document_atomic_version_and_signal(self):
        """Endpoint 10: POST /api/documents/ (Atomic version creation + AuditLog)"""
        tag = Tag.objects.create(name='devops')
        payload = {
            "workspace_id": str(self.workspace.id),
            "created_by_id": str(self.user.id),
            "title": "CI/CD Pipeline",
            "content": "GitHub Actions workflow setup",
            "status": "draft",
            "tag_ids": [str(tag.id)]
        }
        response = self.client.post('/api/documents/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        doc_id = response.data['id']

        # Verify initial DocumentVersion version_number=1 was automatically created
        versions = DocumentVersion.objects.filter(document_id=doc_id)
        self.assertEqual(versions.count(), 1)
        self.assertEqual(versions.first().version_number, 1)

        # Verify AuditLog was recorded via post_save signal
        audit = AuditLog.objects.filter(object_id=doc_id, action='created').first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.model_name, 'Document')

    def test_11_retrieve_document(self):
        """Endpoint 11: GET /api/documents/{id}/"""
        doc = Document.objects.create(
            workspace=self.workspace,
            title='Release Notes',
            content='Version 1.0 details',
            created_by=self.user
        )
        response = self.client.get(f'/api/documents/{doc.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], 'Release Notes')

    def test_12_update_document_creates_version_and_audit(self):
        """Endpoint 12: PUT /api/documents/{id}/ (Atomic new version + AuditLog)"""
        doc = Document.objects.create(
            workspace=self.workspace,
            title='Initial Spec',
            content='Draft text',
            created_by=self.user
        )
        DocumentVersion.objects.create(
            document=doc,
            version_number=1,
            title=doc.title,
            content=doc.content,
            created_by=self.user
        )

        update_payload = {
            "workspace_id": str(self.workspace.id),
            "title": "Updated Spec",
            "content": "Comprehensive updated text",
            "status": "review"
        }
        response = self.client.put(f'/api/documents/{doc.id}/', update_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify second version created with version_number = 2
        versions = DocumentVersion.objects.filter(document_id=doc.id).order_by('version_number')
        self.assertEqual(versions.count(), 2)
        self.assertEqual(versions.last().version_number, 2)
        self.assertEqual(versions.last().title, 'Updated Spec')

        # Verify AuditLog recorded 'updated'
        audit = AuditLog.objects.filter(object_id=str(doc.id), action='updated').first()
        self.assertIsNotNone(audit)

    def test_13_document_versions(self):
        """Endpoint 13: GET /api/documents/{id}/versions/"""
        doc = Document.objects.create(
            workspace=self.workspace,
            title='Versioned Doc',
            created_by=self.user
        )
        DocumentVersion.objects.create(document=doc, version_number=1, title='v1', created_by=self.user)
        DocumentVersion.objects.create(document=doc, version_number=2, title='v2', created_by=self.user)

        response = self.client.get(f'/api/documents/{doc.id}/versions/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_14_document_summary(self):
        """Endpoint 14: GET /api/documents/{id}/summary/"""
        doc = Document.objects.create(
            workspace=self.workspace,
            title='Summary Doc',
            content='One two three four five',
            created_by=self.user
        )
        DocumentVersion.objects.create(document=doc, version_number=1, title='v1', created_by=self.user)
        Comment.objects.create(document=doc, author=self.user, content='Feedback')

        response = self.client.get(f'/api/documents/{doc.id}/summary/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['word_count'], 5)
        self.assertEqual(response.data['metrics']['versions_count'], 1)
        self.assertEqual(response.data['metrics']['comments_count'], 1)

    # ==========================================
    # Folder 4: Comments
    # ==========================================
    def test_15_list_comments(self):
        """Endpoint 15: GET /api/comments/"""
        doc = Document.objects.create(workspace=self.workspace, title='Doc C', created_by=self.user)
        Comment.objects.create(document=doc, author=self.user, content='Top level')

        response = self.client.get(f'/api/comments/?document={doc.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', response.data)
        self.assertEqual(len(results), 1)

    def test_16_create_comment_and_reply(self):
        """Endpoint 16: POST /api/comments/"""
        doc = Document.objects.create(workspace=self.workspace, title='Doc D', created_by=self.user)

        # Create top-level comment
        payload1 = {
            "document_id": str(doc.id),
            "author_id": str(self.user.id),
            "content": "Is this ready for review?"
        }
        res1 = self.client.post('/api/comments/', payload1, format='json')
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)
        parent_id = res1.data['id']

        # Create reply comment referencing parent
        payload2 = {
            "document_id": str(doc.id),
            "author_id": str(self.user2.id),
            "content": "Yes, looks solid!",
            "parent_id": parent_id
        }
        res2 = self.client.post('/api/comments/', payload2, format='json')
        self.assertEqual(res2.status_code, status.HTTP_201_CREATED)
        self.assertEqual(str(res2.data['parent']), parent_id)

    # ==========================================
    # Folder 5: Tags
    # ==========================================
    def test_17_list_tags_with_document_count(self):
        """Endpoint 17: GET /api/tags/ (with Count annotation)"""
        tag = Tag.objects.create(name='architecture')
        doc = Document.objects.create(workspace=self.workspace, title='Arch Doc', created_by=self.user)
        doc.tags.add(tag)

        response = self.client.get('/api/tags/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', response.data)
        self.assertTrue(any(t['name'] == 'architecture' and t['document_count'] == 1 for t in results))

    # ==========================================
    # Folder 6: Audit Logs
    # ==========================================
    def test_18_list_audit_logs(self):
        """Endpoint 18: GET /api/audit-logs/"""
        doc = Document.objects.create(workspace=self.workspace, title='Audited Doc', created_by=self.user)
        response = self.client.get(f'/api/audit-logs/?model_name=Document&object_id={doc.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get('results', response.data)
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0]['model_name'], 'Document')
