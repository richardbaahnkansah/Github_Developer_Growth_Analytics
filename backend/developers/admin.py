from django.contrib import admin
from .models import Developer, Repository, DailyActivity, FollowerSnapshot

admin.site.register(Developer)
admin.site.register(Repository)
admin.site.register(DailyActivity)
admin.site.register(FollowerSnapshot)
