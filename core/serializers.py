from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.db.models import Count
from .models import Workspace, WorkspaceMember, Tag, Document, DocumentVersion, Comment, AuditLog

User = get_user_model()


class UserSummarySerializer(serializers.ModelSerializer):
    """Compact serializer for nested user representations."""
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']
        read_only_fields = fields


class UserSerializer(serializers.ModelSerializer):
    """
    User model serializer with secure password hashing.
    Used for user management and registration.
    """
    password = serializers.CharField(write_only=True, required=False, min_length=8)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'password', 'date_joined']
        read_only_fields = ['id', 'date_joined']

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        user = User(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class TagSerializer(serializers.ModelSerializer):
    """
    Tag model serializer.
    Includes annotated document_count if available.
    """
    document_count = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = Tag
        fields = ['id', 'name', 'created_at', 'document_count']
        read_only_fields = ['id', 'created_at', 'document_count']

    def validate_name(self, value):
        cleaned = value.strip().lower()
        if not cleaned:
            raise serializers.ValidationError("Tag name cannot be empty.")
        if len(cleaned) < 2:
            raise serializers.ValidationError("Tag name must be at least 2 characters long.")
        return cleaned


class WorkspaceMemberSerializer(serializers.ModelSerializer):
    """
    WorkspaceMember serializer.
    Includes nested user details and custom role validation.
    """
    user_details = UserSummarySerializer(source='user', read_only=True)
    user_id = serializers.UUIDField(write_only=True)
    workspace_id = serializers.UUIDField(read_only=True, source='workspace.id')

    class Meta:
        model = WorkspaceMember
        fields = ['id', 'workspace', 'workspace_id', 'user', 'user_id', 'user_details', 'role', 'joined_at']
        read_only_fields = ['id', 'workspace', 'workspace_id', 'user', 'joined_at']

    def validate_role(self, value):
        """Custom Field-Level Validation 1: Ensure role matches valid choices."""
        if value not in WorkspaceMember.Role.values:
            valid_roles = ", ".join(WorkspaceMember.Role.values)
            raise serializers.ValidationError(f"Invalid role '{value}'. Must be one of: {valid_roles}")
        return value

    def validate(self, data):
        """Custom Object-Level Validation: Validate user existence."""
        user_id = data.get('user_id')
        if user_id:
            try:
                user = User.objects.get(id=user_id)
                data['user'] = user
            except User.DoesNotExist:
                raise serializers.ValidationError({"user_id": f"User with ID '{user_id}' does not exist."})
        return data


class WorkspaceSerializer(serializers.ModelSerializer):
    """
    Workspace serializer with:
    - SerializerMethodField for dynamic member count (Section 4.2).
    - Custom validation for workspace name and state (Section 4.2).
    """
    owner_details = UserSummarySerializer(source='owner', read_only=True)
    owner_id = serializers.UUIDField(write_only=True, required=False)
    members_count = serializers.SerializerMethodField()
    documents_count = serializers.SerializerMethodField()
    members = WorkspaceMemberSerializer(source='memberships', many=True, read_only=True)

    class Meta:
        model = Workspace
        fields = [
            'id', 'name', 'description', 'owner', 'owner_id', 'owner_details',
            'is_active', 'created_at', 'updated_at', 'members_count', 'documents_count', 'members'
        ]
        read_only_fields = ['id', 'owner', 'created_at', 'updated_at', 'members_count', 'documents_count', 'members']

    def get_members_count(self, obj) -> int:
        """Section 4.2: First SerializerMethodField usage."""
        if hasattr(obj, 'annotated_members_count'):
            return obj.annotated_members_count
        return obj.memberships.count()

    def get_documents_count(self, obj) -> int:
        """Dynamic documents count."""
        if hasattr(obj, 'annotated_documents_count'):
            return obj.annotated_documents_count
        return obj.documents.count()

    def validate_name(self, value):
        """Section 4.2: Custom Field-Level Validation for Workspace name."""
        trimmed = value.strip()
        if len(trimmed) < 3:
            raise serializers.ValidationError("Workspace name must be at least 3 characters long.")
        if trimmed.isdigit():
            raise serializers.ValidationError("Workspace name cannot consist solely of digits.")
        return trimmed

    def validate(self, data):
        """Section 4.2: Custom Object-Level Validation."""
        # Ensure owner is valid if provided in data
        owner_id = data.get('owner_id')
        if owner_id:
            try:
                owner = User.objects.get(id=owner_id)
                data['owner'] = owner
            except User.DoesNotExist:
                raise serializers.ValidationError({"owner_id": f"User with ID '{owner_id}' does not exist."})
        return data


class DocumentVersionSerializer(serializers.ModelSerializer):
    """Serializer for DocumentVersion snapshot model."""
    created_by_details = UserSummarySerializer(source='created_by', read_only=True)

    class Meta:
        model = DocumentVersion
        fields = [
            'id', 'document', 'version_number', 'title', 'content',
            'created_by', 'created_by_details', 'created_at'
        ]
        read_only_fields = fields


class DocumentSerializer(serializers.ModelSerializer):
    """
    Document serializer with:
    - SerializerMethodField for versions count and comments count (Section 4.2).
    - Custom validation for title and status-dependent content rules (Section 4.2).
    """
    workspace_id = serializers.UUIDField(write_only=True)
    workspace_name = serializers.CharField(source='workspace.name', read_only=True)
    created_by_id = serializers.UUIDField(write_only=True, required=False)
    created_by_details = UserSummarySerializer(source='created_by', read_only=True)
    tag_ids = serializers.ListField(
        child=serializers.UUIDField(),
        write_only=True,
        required=False
    )
    tags = TagSerializer(many=True, read_only=True)
    versions_count = serializers.SerializerMethodField()
    comments_count = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = [
            'id', 'workspace', 'workspace_id', 'workspace_name', 'title', 'content',
            'status', 'created_by', 'created_by_id', 'created_by_details', 'tags',
            'tag_ids', 'versions_count', 'comments_count', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'workspace', 'created_by', 'tags', 'versions_count',
            'comments_count', 'created_at', 'updated_at'
        ]

    def get_versions_count(self, obj) -> int:
        """Section 4.2: Second SerializerMethodField usage."""
        if hasattr(obj, 'annotated_versions_count'):
            return obj.annotated_versions_count
        return obj.versions.count()

    def get_comments_count(self, obj) -> int:
        """Section 4.2: Additional SerializerMethodField usage."""
        if hasattr(obj, 'annotated_comments_count'):
            return obj.annotated_comments_count
        return obj.comments.count()

    def validate_title(self, value):
        """Custom Field-Level Validation: Validate document title length."""
        trimmed = value.strip()
        if len(trimmed) < 2:
            raise serializers.ValidationError("Document title must be at least 2 characters long.")
        return trimmed

    def validate(self, data):
        """
        Custom Object-Level Validation:
        - If document status is 'published', content must not be empty.
        - Validate workspace existence.
        """
        content = data.get('content', getattr(self.instance, 'content', ''))
        status_val = data.get('status', getattr(self.instance, 'status', Document.Status.DRAFT))

        if status_val == Document.Status.PUBLISHED and (not content or not content.strip()):
            raise serializers.ValidationError({
                "content": "A document cannot be published with empty content. Please provide document content before publishing."
            })

        workspace_id = data.get('workspace_id')
        if workspace_id:
            try:
                data['workspace'] = Workspace.objects.get(id=workspace_id)
            except Workspace.DoesNotExist:
                raise serializers.ValidationError({"workspace_id": f"Workspace with ID '{workspace_id}' does not exist."})

        created_by_id = data.get('created_by_id')
        if created_by_id:
            try:
                data['created_by'] = User.objects.get(id=created_by_id)
            except User.DoesNotExist:
                raise serializers.ValidationError({"created_by_id": f"User with ID '{created_by_id}' does not exist."})

        return data


class CommentSerializer(serializers.ModelSerializer):
    """
    Comment serializer supporting threaded discussions.
    Includes custom validation to ensure parent comment belongs to the same document.
    """
    author_details = UserSummarySerializer(source='author', read_only=True)
    author_id = serializers.UUIDField(write_only=True, required=False)
    document_id = serializers.UUIDField(write_only=True)
    parent_id = serializers.UUIDField(write_only=True, required=False, allow_null=True)
    replies_count = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = [
            'id', 'document', 'document_id', 'author', 'author_id', 'author_details',
            'content', 'parent', 'parent_id', 'replies_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'document', 'author', 'parent', 'replies_count', 'created_at', 'updated_at']

    def get_replies_count(self, obj) -> int:
        """Calculate number of direct replies."""
        return obj.replies.count()

    def validate_content(self, value):
        trimmed = value.strip()
        if not trimmed:
            raise serializers.ValidationError("Comment content cannot be blank.")
        return trimmed

    def validate(self, data):
        """
        Custom Object-Level Validation:
        - Validate document existence.
        - Validate author existence.
        - Validate that parent comment belongs to the exact same document.
        """
        document_id = data.get('document_id')
        try:
            document = Document.objects.get(id=document_id)
            data['document'] = document
        except Document.DoesNotExist:
            raise serializers.ValidationError({"document_id": f"Document with ID '{document_id}' does not exist."})

        author_id = data.get('author_id')
        if author_id:
            try:
                data['author'] = User.objects.get(id=author_id)
            except User.DoesNotExist:
                raise serializers.ValidationError({"author_id": f"User with ID '{author_id}' does not exist."})

        parent_id = data.get('parent_id')
        if parent_id:
            try:
                parent = Comment.objects.get(id=parent_id)
                if parent.document_id != document.id:
                    raise serializers.ValidationError({
                        "parent_id": "Invalid parent comment: The parent comment belongs to a different document."
                    })
                data['parent'] = parent
            except Comment.DoesNotExist:
                raise serializers.ValidationError({"parent_id": f"Parent comment with ID '{parent_id}' does not exist."})
        else:
            data['parent'] = None

        return data


class AuditLogSerializer(serializers.ModelSerializer):
    """AuditLog serializer with nested actor summary."""
    actor_details = UserSummarySerializer(source='actor', read_only=True)

    class Meta:
        model = AuditLog
        fields = ['id', 'actor', 'actor_details', 'action', 'model_name', 'object_id', 'details', 'timestamp']
        read_only_fields = fields

