from django.db import models
from django.conf import settings


class CommunityPost(models.Model):
    POST_TYPE_CHOICES = [
        ('general', 'General'),
        ('achievement', 'Achievement'),
        ('workout', 'Workout Share'),
        ('challenge', 'Challenge Update'),
        ('announcement', 'Announcement'),
    ]

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='community_posts',
    )
    post_type = models.CharField(max_length=20, choices=POST_TYPE_CHOICES, default='general')
    content = models.TextField()
    image = models.ImageField(upload_to='community/posts/', blank=True, null=True)
    is_pinned = models.BooleanField(default=False)
    is_visible = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_pinned', '-created_at']

    def __str__(self):
        return f'{self.author.get_full_name() or self.author.username}: {self.content[:60]}'

    @property
    def reaction_count(self):
        return self.reactions.count()


class PostReaction(models.Model):
    REACTION_CHOICES = [
        ('like', 'Like'),
        ('fire', 'Fire'),
        ('strong', 'Strong'),
        ('clap', 'Clap'),
        ('heart', 'Heart'),
    ]

    post = models.ForeignKey(CommunityPost, on_delete=models.CASCADE, related_name='reactions')
    member = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='post_reactions',
    )
    reaction_type = models.CharField(max_length=10, choices=REACTION_CHOICES, default='like')
    reacted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('post', 'member')
        ordering = ['-reacted_at']

    def __str__(self):
        return f'{self.member} reacted {self.reaction_type} to post {self.post_id}'


class GymChallenge(models.Model):
    STATUS_CHOICES = [
        ('upcoming', 'Upcoming'),
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    CHALLENGE_TYPE_CHOICES = [
        ('steps', 'Steps'),
        ('workouts', 'Workouts'),
        ('weight_loss', 'Weight Loss'),
        ('checkins', 'Check-ins'),
        ('custom', 'Custom'),
    ]

    title = models.CharField(max_length=200)
    description = models.TextField()
    challenge_type = models.CharField(
        max_length=20, choices=CHALLENGE_TYPE_CHOICES, default='workouts'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='upcoming')
    target_value = models.PositiveIntegerField(help_text='Target number to reach (e.g. 20 workouts)')
    unit = models.CharField(max_length=50, default='workouts', help_text='Unit label, e.g. workouts, steps, kg')
    start_date = models.DateField()
    end_date = models.DateField()
    banner_image = models.ImageField(upload_to='community/challenges/', blank=True, null=True)
    prize_description = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_challenges',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-start_date']

    def __str__(self):
        return f'{self.title} ({self.get_status_display()})'

    @property
    def participant_count(self):
        return self.entries.values('member').distinct().count()


class ChallengeEntry(models.Model):
    challenge = models.ForeignKey(GymChallenge, on_delete=models.CASCADE, related_name='entries')
    member = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='challenge_entries',
    )
    current_value = models.PositiveIntegerField(default=0)
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    joined_at = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('challenge', 'member')
        ordering = ['-current_value']

    def __str__(self):
        return f'{self.member} — {self.challenge.title}: {self.current_value}/{self.challenge.target_value}'

    @property
    def progress_percent(self):
        if not self.challenge.target_value:
            return 0
        return min(100, int(self.current_value / self.challenge.target_value * 100))
