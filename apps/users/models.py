import json
from django.db import models
from django.contrib.auth.models import User
from django_quill.fields import QuillField
from rest_framework.authtoken.models import Token
from core.storage import SecureFileStorage

# Create avatar storage
avatar_storage = SecureFileStorage(
    private=True,
    collection='user_avatars'
)

# Create your models here.

ROLE_CHOICES = (
    ('admin'  , 'Admin'),
    ('user'  , 'User'),
)

def avatar_with_id(instance, filename):
    # Return a path that includes the user ID to ensure uniqueness
    # but still keep it within the user_avatars collection
    return f"{instance.user.id}/{filename}"

def convert_to_quill():
    converted_data = {
        "delta": "",
        "html": "Write something #cool about you.",
    }
    return json.dumps(converted_data)


class Profile(models.Model):
    user      = models.OneToOneField(User, on_delete=models.CASCADE)
    role      = models.CharField(max_length=20, choices=ROLE_CHOICES, default='user')
    full_name = models.CharField(max_length=255, null=True, blank=True)
    country   = models.CharField(max_length=255, null=True, blank=True)
    city      = models.CharField(max_length=255, null=True, blank=True)
    zip_code  = models.CharField(max_length=255, null=True, blank=True)
    address   = models.CharField(max_length=255, null=True, blank=True)
    phone     = models.CharField(max_length=255, null=True, blank=True)
    avatar    = models.ImageField(upload_to=avatar_with_id, storage=avatar_storage, null=True, blank=True)
    bio       = QuillField(default=convert_to_quill())
    dark_mode = models.BooleanField(default=False)


    def __str__(self):
        return self.user.username
        
    def get_token(self):
        """Get the user's current token"""
        return Token.objects.get_or_create(user=self.user)[0]
        
    def regenerate_token(self):
        """Delete existing token and create a new one"""
        Token.objects.filter(user=self.user).delete()
        return Token.objects.create(user=self.user)