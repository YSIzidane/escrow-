from django import forms
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from django.core.validators import EmailValidator
import re

from allauth.account.adapter import get_adapter as get_account_adapter
from allauth.socialaccount.forms import SignupForm as SocialSignupForm


class RegisterForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'البريد الإلكتروني'
        })
    )
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'اسم المستخدم'
        })
    )
    password1 = forms.CharField(
        label='كلمة المرور',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'كلمة المرور'
        })
    )
    password2 = forms.CharField(
        label='تأكيد كلمة المرور',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'تأكيد كلمة المرور'
        })
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("هذا البريد الإلكتروني مستخدم بالفعل!")
        return email


class SimpleSocialSignupForm(SocialSignupForm):
    """
    Keep social signup intentionally small: the provider supplies the
    verified email, and the user only confirms a platform username.
    """

    field_order = ["username", "email"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "email" in self.fields:
            self.fields["email"].widget = forms.HiddenInput()
        if "username" in self.fields:
            self.fields["username"].help_text = ""

    def clean_email(self):
        email = (
            self.initial.get("email")
            or getattr(self.sociallogin.user, "email", "")
            or ""
        ).strip().lower()
        if not email:
            raise forms.ValidationError(
                "We could not read a verified email from your social account."
            )
        email = get_account_adapter().clean_email(email)
        if email:
            email = self.validate_unique_email(email)
        return email


class WithdrawalRequestForm(forms.Form):
    TRC20_ADDRESS_RE = re.compile(r"^T[a-zA-Z0-9]{33}$")

    def __init__(self, *args, max_balance=None, language="ar", **kwargs):
        self.max_balance = max_balance
        self.language = language
        super().__init__(*args, **kwargs)
        self.fields["amount"].widget.attrs.update(
            {
                "class": "pf-input",
                "placeholder": "0.00",
                "step": "0.01",
                "min": "0.01",
            }
        )
        if max_balance is not None:
            self.fields["amount"].widget.attrs["max"] = str(max_balance)

        self.fields["method"].widget.attrs.update({"class": "pf-input"})
        self.fields["method"].choices = [
            ("paypal", "حساب PayPal" if language == "ar" else "PayPal account"),
            ("bank", "التحويل البنكي" if language == "ar" else "Bank transfer"),
            ("crypto", "USDT (TRC20)"),
        ]
        self.fields["details"].widget.attrs.update(
            {
                "class": "pf-textarea",
                "rows": 4,
            }
        )

    amount = forms.DecimalField(max_digits=12, decimal_places=2)
    method = forms.ChoiceField(choices=())
    details = forms.CharField(widget=forms.Textarea)

    def _msg(self, ar, en):
        return ar if self.language == "ar" else en

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount <= 0:
            raise forms.ValidationError(
                self._msg(
                    "يجب أن يكون مبلغ السحب أكبر من صفر.",
                    "Withdrawal amount must be greater than zero.",
                )
            )
        if self.max_balance is not None and amount > self.max_balance:
            raise forms.ValidationError(
                self._msg(
                    "المبلغ المطلوب أكبر من الرصيد المتاح للسحب.",
                    "The requested amount is greater than your available balance.",
                )
            )
        return amount

    def clean_details(self):
        details = self.cleaned_data["details"].strip()
        method = self.cleaned_data.get("method")
        if not details:
            raise forms.ValidationError(
                self._msg(
                    "يرجى إدخال بيانات الاستلام الخاصة بطريقة السحب.",
                    "Please enter the recipient details for this withdrawal method.",
                )
            )

        if method == "paypal":
            try:
                EmailValidator()(details)
            except ValidationError:
                raise forms.ValidationError(
                    self._msg(
                        "أدخل بريد PayPal صحيحًا.",
                        "Enter a valid PayPal email address.",
                    )
                )
        elif method == "bank":
            if len(details) < 10:
                raise forms.ValidationError(
                    self._msg(
                        "أدخل تفاصيل بنكية أوضح مثل اسم البنك ورقم الحساب أو الـ IBAN.",
                        "Enter clearer bank details such as the bank name and account or IBAN.",
                    )
                )
        elif method == "crypto":
            if not self.TRC20_ADDRESS_RE.match(details):
                raise forms.ValidationError(
                    self._msg(
                        "أدخل عنوان محفظة USDT TRC20 صحيحًا يبدأ بالحرف T.",
                        "Enter a valid USDT TRC20 wallet address starting with T.",
                    )
                )

        return details
