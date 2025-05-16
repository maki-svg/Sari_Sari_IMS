from django.shortcuts import render, redirect
from django.contrib.auth import logout
from django.contrib import messages
from .forms import CreateUserForm, UserUpdateForm, ProfileUpdateForm
import logging

logger = logging.getLogger(__name__)

# Logout view
def logout_view(request):
    logout(request)
    return redirect('user-login')  # Redirect to login page after logout

# Register view
def register(request):
    if request.method == 'POST':
        form = CreateUserForm(request.POST)
        try:
            if form.is_valid():
                user = form.save()
                username = form.cleaned_data.get('username')
                messages.success(request, f'Account created for {username}! You can now log in.')
                return redirect('user-login')
            else:
                # Log form errors for debugging
                logger.error(f"Form validation errors: {form.errors}")
                for field, errors in form.errors.items():
                    for error in errors:
                        messages.error(request, f"{field}: {error}")
        except Exception as e:
            logger.error(f"Error during registration: {str(e)}")
            messages.error(request, "An error occurred during registration. Please try again.")
    else:
        form = CreateUserForm()
    
    context = {
        'form': form
    }
    return render(request, 'user/register.html', context)

def profile(request):
    return render(request, 'user/profile.html')

def profile_update(request):
    if request.method == 'POST':
        user_form = UserUpdateForm(request.POST, instance=request.user)
        profile_form = ProfileUpdateForm(request.POST, request.FILES, instance=request.user.profile)
        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            return redirect('user-profile')  # Redirect after successful update
    else:
        user_form = UserUpdateForm(instance=request.user)
        profile_form = ProfileUpdateForm(instance=request.user.profile)
            
    context = {
        'user_form': user_form,
        'profile_form': profile_form,
    }
    return render(request, 'user/profile_update.html', context)