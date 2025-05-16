from django.db import models
from django.contrib.auth.models import User

# Create your models here.

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True)
    email = models.EmailField(null=True)
    address = models.CharField(max_length=200, null=True)
    bio = models.TextField(blank=True)
    image = models.ImageField(default='avatar.jpg', upload_to='profile_pics')
    

    def __str__(self):
        return f'{self.user.username} Profile'

    class Meta:
        verbose_name_plural = 'Profiles'
        verbose_name = 'Profile'
        ordering = ['user']