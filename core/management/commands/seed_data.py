from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import (
    User, Workspace, WorkspaceMember, Tag,
    Document, DocumentVersion, Comment, AuditLog
)


class Command(BaseCommand):
    help = "Seeds the database with rich demo data for CollabDocs testing and video demonstration."

    def handle(self, *args, **options):
        self.stdout.write("Starting database seeding for CollabDocs...")

        with transaction.atomic():
            # 1. Create Demo Users
            alice, _ = User.objects.get_or_create(
                username='alice',
                defaults={
                    'email': 'alice@collabdocs.internal',
                    'first_name': 'Alice',
                    'last_name': 'Architect'
                }
            )
            if not alice.has_usable_password():
                alice.set_password('AdminPass123!')
                alice.save()

            bob, _ = User.objects.get_or_create(
                username='bob',
                defaults={
                    'email': 'bob@collabdocs.internal',
                    'first_name': 'Bob',
                    'last_name': 'Builder'
                }
            )
            if not bob.has_usable_password():
                bob.set_password('EditorPass123!')
                bob.save()

            carol, _ = User.objects.get_or_create(
                username='carol',
                defaults={
                    'email': 'carol@collabdocs.internal',
                    'first_name': 'Carol',
                    'last_name': 'Reviewer'
                }
            )
            if not carol.has_usable_password():
                carol.set_password('ViewerPass123!')
                carol.save()

            self.stdout.write(self.style.SUCCESS(f"Created/verified users: {alice.username}, {bob.username}, {carol.username}"))

            # 2. Create Tags
            tags_list = ['python', 'django', 'rest-api', 'architecture', 'database', 'performance']
            tags_map = {}
            for tag_name in tags_list:
                tag, _ = Tag.objects.get_or_create(name=tag_name)
                tags_map[tag_name] = tag

            self.stdout.write(self.style.SUCCESS(f"Created/verified tags: {', '.join(tags_list)}"))

            # 3. Create Workspaces
            ws_eng, _ = Workspace.objects.get_or_create(
                name='Core Engineering',
                defaults={
                    'description': 'Backend systems, high-throughput microservices, and databases.',
                    'owner': alice,
                    'is_active': True
                }
            )

            ws_product, _ = Workspace.objects.get_or_create(
                name='Product & Design',
                defaults={
                    'description': 'Product roadmaps, UX wireframes, and customer feedback.',
                    'owner': bob,
                    'is_active': True
                }
            )

            # Ensure Memberships
            WorkspaceMember.objects.get_or_create(
                workspace=ws_eng,
                user=alice,
                defaults={'role': WorkspaceMember.Role.ADMIN}
            )
            WorkspaceMember.objects.get_or_create(
                workspace=ws_eng,
                user=bob,
                defaults={'role': WorkspaceMember.Role.EDITOR}
            )
            WorkspaceMember.objects.get_or_create(
                workspace=ws_eng,
                user=carol,
                defaults={'role': WorkspaceMember.Role.VIEWER}
            )

            # 4. Create Documents & Versions
            doc1, created = Document.objects.get_or_create(
                workspace=ws_eng,
                title='System Architecture Specification',
                defaults={
                    'content': 'This document details the architectural blueprint for CollabDocs backend API.',
                    'status': Document.Status.PUBLISHED,
                    'created_by': alice
                }
            )
            if created:
                doc1.tags.set([tags_map['django'], tags_map['architecture'], tags_map['performance']])
                DocumentVersion.objects.create(
                    document=doc1,
                    version_number=1,
                    title='System Architecture Draft',
                    content='Initial thoughts on architecture.',
                    created_by=alice
                )
                DocumentVersion.objects.create(
                    document=doc1,
                    version_number=2,
                    title=doc1.title,
                    content=doc1.content,
                    created_by=alice
                )

            doc2, created2 = Document.objects.get_or_create(
                workspace=ws_eng,
                title='Database Indexing & Query Optimisation',
                defaults={
                    'content': 'Strategies for eliminating N+1 queries using select_related and prefetch_related.',
                    'status': Document.Status.REVIEW,
                    'created_by': bob
                }
            )
            if created2:
                doc2.tags.set([tags_map['database'], tags_map['performance'], tags_map['python']])
                DocumentVersion.objects.create(
                    document=doc2,
                    version_number=1,
                    title=doc2.title,
                    content=doc2.content,
                    created_by=bob
                )

            # 5. Create Threaded Comments
            c1, c1_created = Comment.objects.get_or_create(
                document=doc1,
                author=bob,
                content='Did we consider connection pooling with PgBouncer for PostgreSQL?',
                parent=None
            )
            if c1_created:
                Comment.objects.create(
                    document=doc1,
                    author=alice,
                    content='Yes! PgBouncer in transaction pooling mode will be configured.',
                    parent=c1
                )

        self.stdout.write(self.style.SUCCESS("Database seeding completed successfully!"))

