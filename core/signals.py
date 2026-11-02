from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from .models import Document, AuditLog


@receiver(pre_save, sender=Document)
def document_pre_save_receiver(sender, instance, **kwargs):
    """
    Pre-save receiver to cache instance._state.adding.
    In Django's lifecycle, instance._state.adding is True for new records before DB write,
    and False for existing records. We capture this to distinguish created vs updated.
    """
    instance._was_adding = getattr(instance._state, 'adding', False)


@receiver(post_save, sender=Document)
def document_post_save_audit_handler(sender, instance, created, **kwargs):
    """
    Section 4.5 Requirement:
    - post_save signal on Document, written in signals.py, connected in AppConfig.ready().
    - Uses instance._state.adding to distinguish created vs updated.
    - Writes an AuditLog entry for each save inside the active transaction block.
    - Records: actor (created_by), action ('created' or 'updated'), model_name ('Document'), object_id.
    """
    # Check instance._state.adding / cached pre-save state
    is_created = getattr(instance, '_was_adding', None)
    if is_created is None:
        is_created = created or getattr(instance._state, 'adding', False)

    action = 'created' if is_created else 'updated'

    # Create the AuditLog record inside the active transaction block
    AuditLog.objects.create(
        actor=instance.created_by,
        action=action,
        model_name='Document',
        object_id=str(instance.id),
        details={
            'title': instance.title,
            'status': instance.status,
            'workspace_id': str(instance.workspace_id) if instance.workspace_id else None
        }
    )

