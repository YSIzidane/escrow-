# ==================== Auth Views ====================
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.utils.http import url_has_allowed_host_and_scheme
from django.urls import reverse

from ..forms import RegisterForm
from ..i18n import get_request_language, get_translation


def login_page(request):
    """صفحة تسجيل الدخول"""
    if request.user.is_authenticated:
        return redirect('home')
    language = get_request_language(request)
    if request.method == "POST":
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        if not username or not password:
            return render(request, "account/login.html", {"error": get_translation("login.invalid_credentials", language)})
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            next_url = request.GET.get('next', 'home')
            if not url_has_allowed_host_and_scheme(
                url=next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                next_url = 'home'
            return redirect(next_url)
        else:
            return render(request, "account/login.html", {"error": get_translation("login.invalid_credentials", language)})
    return render(request, "account/login.html")


def register_page(request):
    """صفحة التسجيل الجديد"""
    if request.user.is_authenticated:
        return redirect('home')
    language = get_request_language(request)
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f"Welcome {user.username}! Your account was created successfully." if language == "en" else f"مرحبًا {user.username}! تم إنشاء حسابك بنجاح")
            return redirect('home')
    else:
        form = RegisterForm()
    return render(request, "account/signup.html", {"form": form})


def logout_page(request):
    """تسجيل الخروج — POST فقط"""
    if request.method == "POST":
        logout(request)
        messages.success(request, "تم تسجيل الخروج بنجاح!")
    return redirect('home')


def _redirect_with_query(request, target_name):
    target = reverse(target_name)
    query = request.GET.urlencode()
    return redirect(f"{target}?{query}" if query else target)


def legacy_login_redirect(request):
    return _redirect_with_query(request, "account_login")


def legacy_register_redirect(request):
    return _redirect_with_query(request, "account_signup")


def legacy_logout_redirect(request):
    return _redirect_with_query(request, "account_logout")
