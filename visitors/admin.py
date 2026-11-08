from django.contrib import admin
from .models import Visitor, Blacklist, VisitorPass, Logbook, Notification


class VisitorPassAdmin(admin.ModelAdmin):
    list_display = ("visitor", "token", "issued_at", "time_limit_minutes")
    readonly_fields = ("token",)


admin.site.register(Visitor)
admin.site.register(Blacklist)
admin.site.register(VisitorPass, VisitorPassAdmin)
admin.site.register(Logbook)
admin.site.register(Notification)