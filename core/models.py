import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings


class User(AbstractUser):
    """
    Custom User model for CollabDocs.
    Uses UUID as the primary key as required by Section 2.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)

    class Meta:
        ordering = ['username']

    def __str__(self):
        return self.username


class Workspace(models.Model):
    """
    Workspace model representing a collaborative space for documents and users.
    Section 2.2: is_active is BooleanField with default=True.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='owned_workspaces'
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class WorkspaceMember(models.Model):
    """
    WorkspaceMember join model connecting Workspaces and Users with Role-Based Access Control.
    Section 2.2: role uses TextChoices, Meta class has UniqueConstraint on (workspace, user).
    """
    class Role(models.TextChoices):
        ADMIN = 'admin', 'Admin'
        EDITOR = 'editor', 'Editor'
        VIEWER = 'viewer', 'Viewer'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name='memberships'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='workspace_memberships'
    )
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.VIEWER
    )
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['workspace', 'user'], name='unique_workspace_member')
        ]
        ordering = ['-joined_at']

    def __str__(self):
        return f"{self.user.username} ({self.role}) in {self.workspace.name}"


class Tag(models.Model):
    """
    Tag model for categorizing documents.
    Section 2.1: ManyToManyField join table with Document.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Document(models.Model):
    """
    Document model representing collaborative files inside a workspace.
    Section 2.2: status uses TextChoices.
    Section 2.1: ManyToManyField with Tag.
    """
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        REVIEW = 'review', 'In Review'
        PUBLISHED = 'published', 'Published'
        ARCHIVED = 'archived', 'Archived'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name='documents'
    )
    title = models.CharField(max_length=255)
    content = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='documents'
    )
    tags = models.ManyToManyField(
        Tag,
        related_name='documents',
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return self.title


class DocumentVersion(models.Model):
    """
    DocumentVersion model storing snapshot history for every document save/update.
    Section 2.1 & 2.2:
    - version_number computed as Document.versions.count() + 1 inside transaction.atomic()
    - Per-document numbering without global counter.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name='versions'
    )
    version_number = models.PositiveIntegerField()
    title = models.CharField(max_length=255)
    content = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='document_versions'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['document', 'version_number'], name='unique_document_version')
        ]
        ordering = ['-version_number']

    def __str__(self):
        return f"{self.document.title} - v{self.version_number}"


class Comment(models.Model):
    """
    Comment model supporting threaded discussions on documents.
    Section 2.1: Self-referential FK parent = ForeignKey('self', null=True, blank=True,
                 on_delete=models.SET_NULL, related_name='replies').
    A comment with no parent is a top-level comment.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name='comments'
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='comments'
    )
    content = models.TextField()
    parent = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='replies'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        prefix = f"Reply to {self.parent_id}: " if self.parent else "Top-level: "
        return f"{prefix}{self.content[:30]} by {self.author.username}"


class AuditLog(models.Model):
    """
    AuditLog model recording system events and document lifecycle changes.
    Section 4.5: Recorded automatically via post_save signal on Document.
    Records: actor (created_by), action ('created' or 'updated'), model_name ('Document'), object_id.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs'
    )
    action = models.CharField(max_length=50)  # e.g., 'created', 'updated', 'deleted'
    model_name = models.CharField(max_length=50, default='Document')
    object_id = models.CharField(max_length=64)
    details = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        actor_name = self.actor.username if self.actor else "System"
        return f"[{self.timestamp:%Y-%m-%d %H:%M:%S}] {actor_name} {self.action} {self.model_name}:{self.object_id}"
