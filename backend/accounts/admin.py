from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DefaultUserAdmin
from django.contrib.auth.models import User

from .models import AccountAuditLogEntry, Profile


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    verbose_name_plural = 'Rol'


class UserAdmin(DefaultUserAdmin):
    inlines = [ProfileInline]
    list_display = DefaultUserAdmin.list_display + ('role',)

    @admin.display(description='Rol')
    def role(self, obj):
        return obj.profile.get_role_display()


admin.site.unregister(User)
admin.site.register(User, UserAdmin)


@admin.register(AccountAuditLogEntry)
class AccountAuditLogEntryAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'actor_username', 'action', 'target_username', 'detail']
    list_filter = ['action']
    search_fields = ['actor_username', 'target_username']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
