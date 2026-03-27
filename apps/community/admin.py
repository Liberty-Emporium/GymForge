from django.contrib import admin
from django.utils.html import format_html

from .models import CommunityPost, PostReaction, GymChallenge, ChallengeEntry


class PostReactionInline(admin.TabularInline):
    model = PostReaction
    extra = 0
    fields = ('member', 'reaction_type', 'reacted_at')
    readonly_fields = ('reacted_at',)


@admin.register(CommunityPost)
class CommunityPostAdmin(admin.ModelAdmin):
    list_display = (
        'author', 'post_type', 'content_short', 'reaction_count',
        'is_pinned', 'is_visible', 'created_at',
    )
    list_filter = ('post_type', 'is_pinned', 'is_visible')
    search_fields = ('author__first_name', 'author__last_name', 'content')
    ordering = ('-is_pinned', '-created_at')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [PostReactionInline]

    fieldsets = (
        ('Post', {
            'fields': ('author', 'post_type', 'content', 'image'),
        }),
        ('Visibility', {
            'fields': ('is_pinned', 'is_visible'),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
        }),
    )

    def content_short(self, obj):
        return obj.content[:80] + '…' if len(obj.content) > 80 else obj.content
    content_short.short_description = 'Content'

    def reaction_count(self, obj):
        return obj.reaction_count
    reaction_count.short_description = 'Reactions'


@admin.register(PostReaction)
class PostReactionAdmin(admin.ModelAdmin):
    list_display = ('member', 'reaction_type', 'post', 'reacted_at')
    list_filter = ('reaction_type',)
    search_fields = ('member__first_name', 'member__last_name')
    ordering = ('-reacted_at',)
    readonly_fields = ('reacted_at',)


class ChallengeEntryInline(admin.TabularInline):
    model = ChallengeEntry
    extra = 0
    fields = ('member', 'current_value', 'is_completed', 'completed_at', 'joined_at')
    readonly_fields = ('joined_at',)


@admin.register(GymChallenge)
class GymChallengeAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'challenge_type', 'status_badge', 'target_value', 'unit',
        'start_date', 'end_date', 'participant_count',
    )
    list_filter = ('status', 'challenge_type')
    search_fields = ('title', 'description')
    ordering = ('-start_date',)
    readonly_fields = ('created_at',)
    inlines = [ChallengeEntryInline]

    fieldsets = (
        ('Challenge', {
            'fields': ('title', 'description', 'challenge_type', 'status', 'banner_image'),
        }),
        ('Target', {
            'fields': ('target_value', 'unit', 'prize_description'),
        }),
        ('Schedule', {
            'fields': ('start_date', 'end_date'),
        }),
        ('Meta', {
            'fields': ('created_by', 'created_at'),
        }),
    )

    def status_badge(self, obj):
        colours = {
            'upcoming': '#6b7280',
            'active': '#10b981',
            'completed': '#3b82f6',
            'cancelled': '#ef4444',
        }
        colour = colours.get(obj.status, '#6b7280')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:4px;font-size:11px;font-weight:600">{}</span>',
            colour, obj.get_status_display(),
        )
    status_badge.short_description = 'Status'

    def participant_count(self, obj):
        return obj.participant_count
    participant_count.short_description = 'Participants'


@admin.register(ChallengeEntry)
class ChallengeEntryAdmin(admin.ModelAdmin):
    list_display = (
        'member', 'challenge', 'current_value', 'progress_display',
        'is_completed', 'joined_at',
    )
    list_filter = ('is_completed', 'challenge')
    search_fields = ('member__first_name', 'member__last_name')
    ordering = ('-current_value',)
    readonly_fields = ('joined_at', 'last_updated')

    def progress_display(self, obj):
        pct = obj.progress_percent
        colour = '#10b981' if pct >= 100 else '#3b82f6' if pct >= 50 else '#f59e0b'
        return format_html(
            '<span style="color:{};font-weight:600">{}%</span>',
            colour, pct,
        )
    progress_display.short_description = 'Progress'
