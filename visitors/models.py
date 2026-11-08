import uuid
from django.db import models
from django.utils import timezone


class Visitor(models.Model):
    GENDER_CHOICES = [("Male", "Male"), ("Female", "Female")]

    name = models.CharField(max_length=100)
    vehicle_plate = models.CharField(max_length=20)
    phone = models.CharField(max_length=20)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES)
    ic_number = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.vehicle_plate})"


class Blacklist(models.Model):
    vehicle_plate = models.CharField(max_length=20, blank=True)
    ic_number = models.CharField(max_length=20, blank=True)
    reason = models.CharField(max_length=255)
    blacklisted_at = models.DateTimeField(auto_now_add=True)
    added_by = models.CharField(max_length=150, blank=True, default="")
    name = models.CharField(max_length=100, blank=True, default="")

    def __str__(self):
        return f"{self.vehicle_plate or self.ic_number} - {self.reason}"


class VisitorPass(models.Model):
    visitor = models.ForeignKey(Visitor, on_delete=models.CASCADE)
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    issued_at = models.DateTimeField(auto_now_add=True)
    time_limit_minutes = models.PositiveIntegerField(default=30)

    def __str__(self):
        return f"Pass for {self.visitor.name}"


class Logbook(models.Model):
    STATUS_CHOICES = [
        ("Pending", "Pending"),
        ("Ongoing", "Ongoing"),
        ("Completed", "Completed"),
    ]

    visitor_pass = models.ForeignKey(VisitorPass, on_delete=models.CASCADE)
    entry_time = models.DateTimeField(null=True, blank=True)
    exit_time = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="Pending")
    exit_method = models.CharField(max_length=20, blank=True, default="")

    def elapsed_minutes(self):
        if not self.entry_time:
            return 0
        end = self.exit_time or timezone.now()
        return int((end - self.entry_time).total_seconds() // 60)

    def __str__(self):
        return f"{self.visitor_pass.visitor.name} - {self.status}"


class Notification(models.Model):
    logbook = models.ForeignKey(Logbook, on_delete=models.CASCADE)
    message = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    def __str__(self):
        return self.message