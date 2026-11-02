from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction, IntegrityError
from django.db.models import Q, Count
from django.contrib.auth import get_user_model
from django.utils.dateparse import parse_datetime

from .models import (
    Workspace,
    WorkspaceMember,
    Tag,
    Document,
    DocumentVersion,
    Comment,
    AuditLog,
)
from .serializers import (
    UserSerializer,
    WorkspaceSerializer,
    WorkspaceMemberSerializer,
    TagSerializer,
    DocumentSerializer,
    DocumentVersionSerializer,
    CommentSerializer,
    AuditLogSerializer,
)

User = get_user_model()


class UserViewSet(viewsets.ModelViewSet):
    """
    ModelViewSet for User management (CRUD).
    Provides endpoints for listing, creating, retrieving, updating, and deleting users.
    """
    queryset = User.objects.all().order_by('username')
    serializer_class = UserSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(username__icontains=search) |
                Q(email__icontains=search) |
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search)
            )
        return queryset


class WorkspaceViewSet(viewsets.ModelViewSet):
    """
    ModelViewSet for Workspaces.
    Features:
    - select_related('owner') to optimize nested owner lookups (Section 4.3).
    - annotate(members_count=Count('memberships', distinct=True)) (Section 4.3).
    - Query parameter filtering with lookups: is_active, name__icontains, created_at__gte, created_at__lte (Section 4.3).
    - Atomic creation: Workspace + Owner as Admin WorkspaceMember in transaction.atomic() (Section 2.2 & 4.4).
    - Custom @action 'members': Adds collaborator, explicitly catches IntegrityError -> 409 Conflict (Section 4.4).
    - Custom @action 'stats': Aggregates document counts and active members (Section 4.3).
    """
    serializer_class = WorkspaceSerializer

    def get_queryset(self):
        # Section 4.3: select_related on nested owner data
        queryset = Workspace.objects.select_related('owner').annotate(
            annotated_members_count=Count('memberships', distinct=True),
            annotated_documents_count=Count('documents', distinct=True)
        ).order_by('-created_at')

        params = self.request.query_params

        # Section 4.3: Lookups (exact, icontains, gte, lte)
        is_active = params.get('is_active')
        if is_active is not None:
            active_bool = is_active.lower() in ('true', '1')
            queryset = queryset.filter(is_active=active_bool)

        name = params.get('name')
        if name:
            queryset = queryset.filter(name__icontains=name)

        created_gte = params.get('created_at__gte')
        if created_gte:
            dt = parse_datetime(created_gte)
            if dt:
                queryset = queryset.filter(created_at__gte=dt)

        created_lte = params.get('created_at__lte')
        if created_lte:
            dt = parse_datetime(created_lte)
            if dt:
                queryset = queryset.filter(created_at__lte=dt)

        owner_id = params.get('owner')
        if owner_id:
            queryset = queryset.filter(owner_id=owner_id)

        return queryset

    def create(self, request, *args, **kwargs):
        """
        Section 2.2 & 4.4:
        Workspace creation wrapped in transaction.atomic().
        Owner is automatically added as WorkspaceMember with role=admin.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        owner = serializer.validated_data.get('owner')
        if not owner:
            if request.user.is_authenticated:
                owner = request.user
            else:
                first_user = User.objects.first()
                if not first_user:
                    return Response(
                        {"error": "No user available to assign as workspace owner. Please create a user first."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                owner = first_user

        # Atomic transaction wrapping workspace creation + admin membership creation
        with transaction.atomic():
            workspace = serializer.save(owner=owner)
            WorkspaceMember.objects.create(
                workspace=workspace,
                user=owner,
                role=WorkspaceMember.Role.ADMIN
            )

        headers = self.get_success_headers(serializer.data)
        return Response(WorkspaceSerializer(workspace).data, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=True, methods=['post'], url_path='members')
    def add_member(self, request, pk=None):
        """
        Section 3 & 4.4:
        Custom endpoint to add a collaborator to a workspace.
        Explicitly handles:
        - DoesNotExist -> 404 NOT FOUND
        - IntegrityError -> 409 CONFLICT (Section 4.4)
        """
        workspace = self.get_object()
        user_id = request.data.get('user_id')
        role = request.data.get('role', WorkspaceMember.Role.VIEWER)

        if not user_id:
            return Response(
                {"error": "Field 'user_id' is required to add a member."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if role not in WorkspaceMember.Role.values:
            valid_roles = ", ".join(WorkspaceMember.Role.values)
            return Response(
                {"error": f"Invalid role '{role}'. Valid choices: {valid_roles}."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Handle User.DoesNotExist explicitly (Section 4.4)
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {"error": f"User with ID '{user_id}' does not exist."},
                status=status.HTTP_404_NOT_FOUND
            )

        # Wrap in atomic block and catch IntegrityError explicitly to return 409
        try:
            with transaction.atomic():
                member = WorkspaceMember.objects.create(
                    workspace=workspace,
                    user=user,
                    role=role
                )
                serializer = WorkspaceMemberSerializer(member)
                return Response(serializer.data, status=status.HTTP_201_CREATED)
        except IntegrityError:
            # Section 4.4: Catch IntegrityError on WorkspaceMember creation to return a 409
            return Response(
                {
                    "error": f"Conflict: User '{user.username}' is already a member of workspace '{workspace.name}'."
                },
                status=status.HTTP_409_CONFLICT
            )

    @action(detail=True, methods=['get'], url_path='stats')
    def stats(self, request, pk=None):
        """
        Section 4.2 & 4.3:
        Workspace statistics endpoint utilizing aggregate() and annotate() with Count.
        Uses values_list() where only IDs are needed.
        """
        workspace = self.get_object()

        # Section 4.3: Use values_list() where only IDs are needed
        member_ids = list(workspace.memberships.values_list('user_id', flat=True))

        # Section 4.3: aggregate() with Count
        stats_data = workspace.documents.aggregate(
            total_documents=Count('id'),
            draft_count=Count('id', filter=Q(status=Document.Status.DRAFT)),
            review_count=Count('id', filter=Q(status=Document.Status.REVIEW)),
            published_count=Count('id', filter=Q(status=Document.Status.PUBLISHED)),
            archived_count=Count('id', filter=Q(status=Document.Status.ARCHIVED)),
        )

        total_members = workspace.memberships.count()

        return Response({
            "workspace_id": str(workspace.id),
            "workspace_name": workspace.name,
            "is_active": workspace.is_active,
            "total_members": total_members,
            "member_user_ids": [str(uid) for uid in member_ids],
            "document_statistics": stats_data
        }, status=status.HTTP_200_OK)


class DocumentViewSet(viewsets.ModelViewSet):
    """
    ModelViewSet for Documents.
    Features:
    - select_related('workspace', 'created_by') & prefetch_related('tags') (Section 4.3).
    - filter() with lookups: gte, lte, in, __icontains (Section 4.3).
    - Q objects for OR filtering across title and content (Section 4.3).
    - Atomic document save + version creation in transaction.atomic() (Section 2.1 & 4.4).
    - Per-document version numbering computed as Document.versions.count() + 1 (Section 2.1).
    - AuditLog automatically recorded via post_save signal inside the same atomic block (Section 4.5).
    - Custom @action 'versions': Lists all historical versions of a document.
    - Custom @action 'summary': Aggregation metrics for document.
    - Custom @action 'tags': Add/remove tags using values_list() (Section 4.3).
    """
    serializer_class = DocumentSerializer

    def get_queryset(self):
        # Section 4.3: select_related on nested workspace & created_by data
        queryset = Document.objects.select_related('workspace', 'created_by').prefetch_related('tags').annotate(
            annotated_versions_count=Count('versions', distinct=True),
            annotated_comments_count=Count('comments', distinct=True)
        ).order_by('-updated_at')

        params = self.request.query_params

        # Section 4.3: Q objects for OR filtering across title and content
        search = params.get('search')
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) | Q(content__icontains=search)
            )

        # Section 4.3: Lookups (__icontains, in, gte, lte)
        title = params.get('title')
        if title:
            queryset = queryset.filter(title__icontains=title)

        status_in = params.get('status__in')
        if status_in:
            statuses = [s.strip().lower() for s in status_in.split(',') if s.strip()]
            queryset = queryset.filter(status__in=statuses)
        elif params.get('status'):
            queryset = queryset.filter(status=params.get('status').lower())

        workspace_id = params.get('workspace')
        if workspace_id:
            queryset = queryset.filter(workspace_id=workspace_id)

        tag_name = params.get('tag')
        if tag_name:
            queryset = queryset.filter(tags__name__iexact=tag_name)

        created_gte = params.get('created_at__gte')
        if created_gte:
            dt = parse_datetime(created_gte)
            if dt:
                queryset = queryset.filter(created_at__gte=dt)

        created_lte = params.get('created_at__lte')
        if created_lte:
            dt = parse_datetime(created_lte)
            if dt:
                queryset = queryset.filter(created_at__lte=dt)

        return queryset

    def create(self, request, *args, **kwargs):
        """
        Section 2.1 & 4.4:
        Document save + version creation wrapped in transaction.atomic().
        Computes version_number as Document.versions.count() + 1.
        AuditLog written inside the same atomic block via post_save signal.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        created_by = serializer.validated_data.get('created_by')
        if not created_by:
            if request.user.is_authenticated:
                created_by = request.user
            else:
                first_user = User.objects.first()
                if not first_user:
                    return Response(
                        {"error": "No user available as creator. Please create a user first."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                created_by = first_user

        tag_ids = serializer.validated_data.pop('tag_ids', [])

        # Section 4.4: Wrap document save + version creation in a single transaction.atomic()
        with transaction.atomic():
            document = serializer.save(created_by=created_by)

            if tag_ids:
                tags = Tag.objects.filter(id__in=tag_ids)
                document.tags.set(tags)

            # Section 2.1: Compute version_number as Document.versions.count() + 1
            version_number = document.versions.count() + 1

            DocumentVersion.objects.create(
                document=document,
                version_number=version_number,
                title=document.title,
                content=document.content,
                created_by=created_by
            )

        headers = self.get_success_headers(serializer.data)
        return Response(DocumentSerializer(document).data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        """
        Section 2.1 & 4.4:
        Document update + version creation wrapped in transaction.atomic().
        Every save creates a new DocumentVersion with version_number = versions.count() + 1.
        """
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        tag_ids = serializer.validated_data.pop('tag_ids', None)

        actor = request.user if request.user.is_authenticated else instance.created_by

        with transaction.atomic():
            document = serializer.save()

            if tag_ids is not None:
                tags = Tag.objects.filter(id__in=tag_ids)
                document.tags.set(tags)

            # Section 2.1: version_number computed inside atomic block
            version_number = document.versions.count() + 1

            DocumentVersion.objects.create(
                document=document,
                version_number=version_number,
                title=document.title,
                content=document.content,
                created_by=actor
            )

        return Response(DocumentSerializer(document).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], url_path='versions')
    def versions(self, request, pk=None):
        """
        Section 4.2:
        Lists all versions belonging to this document.
        Uses select_related('created_by') for query optimization.
        """
        document = self.get_object()
        versions = document.versions.select_related('created_by').order_by('-version_number')
        serializer = DocumentVersionSerializer(versions, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], url_path='summary')
    def summary(self, request, pk=None):
        """
        Section 4.2 & 4.3:
        Document summary endpoint with aggregate() and Count annotations.
        """
        document = self.get_object()

        summary_metrics = Document.objects.filter(id=document.id).aggregate(
            versions_count=Count('versions', distinct=True),
            comments_count=Count('comments', distinct=True),
            tags_count=Count('tags', distinct=True)
        )

        words = len(document.content.split()) if document.content else 0

        # Section 4.3: values_list() for tag names
        tag_names = list(document.tags.values_list('name', flat=True))

        return Response({
            "document_id": str(document.id),
            "title": document.title,
            "status": document.status,
            "workspace_id": str(document.workspace_id),
            "workspace_name": document.workspace.name,
            "word_count": words,
            "character_count": len(document.content),
            "metrics": summary_metrics,
            "tags": tag_names,
            "created_at": document.created_at,
            "updated_at": document.updated_at
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='tags')
    def manage_tags(self, request, pk=None):
        """
        Section 2.1 & 4.3:
        Add or remove tags on document.
        Demonstrates doc.tags.add() and values_list() usage.
        """
        document = self.get_object()
        tag_names = request.data.get('tags', [])

        if not isinstance(tag_names, list) or not tag_names:
            return Response(
                {"error": "Please provide a non-empty list of tag names under 'tags'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            for name in tag_names:
                cleaned = name.strip()
                if cleaned:
                    tag, _ = Tag.objects.get_or_create(name=cleaned)
                    document.tags.add(tag)

        # Section 4.3: values_list() where only IDs are needed
        current_tag_ids = list(document.tags.values_list('id', flat=True))
        current_tag_names = list(document.tags.values_list('name', flat=True))

        return Response({
            "document_id": str(document.id),
            "tag_ids": [str(tid) for tid in current_tag_ids],
            "tags": current_tag_names
        }, status=status.HTTP_200_OK)


class CommentViewSet(viewsets.ModelViewSet):
    """
    ModelViewSet for threaded Comments.
    Features:
    - select_related('author', 'document', 'parent') (Section 4.3).
    - Self-referential FK: parent for threaded replies (Section 2.1).
    - Filtering by document, author, parent (top_level), and content__icontains (Section 4.3).
    """
    serializer_class = CommentSerializer

    def get_queryset(self):
        # Section 4.3: select_related on author, document, parent
        queryset = Comment.objects.select_related('author', 'document', 'parent')

        params = self.request.query_params

        document_id = params.get('document')
        if document_id:
            queryset = queryset.filter(document_id=document_id)

        author_id = params.get('author')
        if author_id:
            queryset = queryset.filter(author_id=author_id)

        # Filter top-level comments (parent is null) vs replies
        top_level = params.get('top_level')
        if top_level is not None:
            if top_level.lower() in ('true', '1'):
                queryset = queryset.filter(parent__isnull=True)
            else:
                queryset = queryset.filter(parent__isnull=False)

        content = params.get('content')
        if content:
            queryset = queryset.filter(content__icontains=content)

        created_gte = params.get('created_at__gte')
        if created_gte:
            dt = parse_datetime(created_gte)
            if dt:
                queryset = queryset.filter(created_at__gte=dt)

        created_lte = params.get('created_at__lte')
        if created_lte:
            dt = parse_datetime(created_lte)
            if dt:
                queryset = queryset.filter(created_at__lte=dt)

        return queryset

    def perform_create(self, serializer):
        author = serializer.validated_data.get('author')
        if not author:
            if self.request.user.is_authenticated:
                author = self.request.user
            else:
                author = User.objects.first()
        serializer.save(author=author)


class TagViewSet(viewsets.ModelViewSet):
    """
    ModelViewSet for Tags.
    Features:
    - annotate(document_count=Count('documents')) (Section 4.3).
    - filter by name__icontains (Section 4.3).
    """
    serializer_class = TagSerializer

    def get_queryset(self):
        # Section 4.3: annotate with Count
        queryset = Tag.objects.annotate(document_count=Count('documents')).order_by('name')

        name = self.request.query_params.get('name')
        if name:
            queryset = queryset.filter(name__icontains=name)

        return queryset


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ReadOnlyModelViewSet for Audit Logs.
    Features:
    - select_related('actor') for optimized actor lookup (Section 4.3).
    - filter by model_name, action, object_id, timestamp__gte, timestamp__lte (Section 4.3).
    """
    serializer_class = AuditLogSerializer

    def get_queryset(self):
        # Section 4.3: select_related on actor
        queryset = AuditLog.objects.select_related('actor')

        params = self.request.query_params

        action_name = params.get('action')
        if action_name:
            queryset = queryset.filter(action__iexact=action_name)

        model_name = params.get('model_name')
        if model_name:
            queryset = queryset.filter(model_name__iexact=model_name)

        object_id = params.get('object_id')
        if object_id:
            queryset = queryset.filter(object_id=object_id)

        timestamp_gte = params.get('timestamp__gte')
        if timestamp_gte:
            dt = parse_datetime(timestamp_gte)
            if dt:
                queryset = queryset.filter(timestamp__gte=dt)

        timestamp_lte = params.get('timestamp__lte')
        if timestamp_lte:
            dt = parse_datetime(timestamp_lte)
            if dt:
                queryset = queryset.filter(timestamp__lte=dt)

        return queryset
