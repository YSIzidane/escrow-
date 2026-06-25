from email.mime.image import MIMEImage
from mimetypes import guess_type
from pathlib import Path

from allauth.account import app_settings
from allauth.account.adapter import DefaultAccountAdapter
from allauth.core import context as allauth_context
from django.conf import settings
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.template import TemplateDoesNotExist
from django.template.loader import render_to_string


class BrandedAccountAdapter(DefaultAccountAdapter):
    INLINE_IMAGES = {
        "brand-logo": Path(settings.BASE_DIR) / "static" / "images" / "brand" / "logo-primary.png",
        "brand-hero": Path(settings.BASE_DIR) / "static" / "images" / "brand" / "og-card.png",
    }

    def _build_inline_images(self):
        attachments = []
        for content_id, path in self.INLINE_IMAGES.items():
            if not path.exists():
                continue
            mime_type = guess_type(path.name)[0] or "image/png"
            subtype = mime_type.split("/", 1)[1]
            attachments.append(
                {
                    "cid": content_id,
                    "path": path,
                    "filename": path.name,
                    "subtype": subtype,
                }
            )
        return attachments

    def _attach_inline_images(self, message, attachments):
        if not attachments:
            return

        message.mixed_subtype = "related"
        for attachment in attachments:
            image = MIMEImage(
                attachment["path"].read_bytes(),
                _subtype=attachment["subtype"],
            )
            image.add_header("Content-ID", f"<{attachment['cid']}>")
            image.add_header("Content-Disposition", "inline", filename=attachment["filename"])
            message.attach(image)

    def render_mail(self, template_prefix, email, context, headers=None):
        to = [email] if isinstance(email, str) else email
        subject = render_to_string(f"{template_prefix}_subject.txt", context)
        subject = " ".join(subject.splitlines()).strip()
        subject = self.format_email_subject(subject)

        from_email = self.get_from_email()

        inline_images = self._build_inline_images()
        render_context = dict(context)
        render_context.setdefault(
            "brand_logo_email_src",
            "cid:brand-logo" if any(item["cid"] == "brand-logo" for item in inline_images) else "",
        )
        render_context.setdefault(
            "brand_hero_email_src",
            "cid:brand-hero" if any(item["cid"] == "brand-hero" for item in inline_images) else "",
        )

        bodies = {}
        html_ext = app_settings.TEMPLATE_EXTENSION
        for ext in [html_ext, "txt"]:
            try:
                template_name = f"{template_prefix}_message.{ext}"
                bodies[ext] = render_to_string(
                    template_name,
                    render_context,
                    allauth_context.request,
                ).strip()
            except TemplateDoesNotExist:
                if ext == "txt" and not bodies:
                    raise

        if "txt" in bodies:
            msg = EmailMultiAlternatives(
                subject, bodies["txt"], from_email, to, headers=headers
            )
            if html_ext in bodies:
                msg.attach_alternative(bodies[html_ext], "text/html")
                self._attach_inline_images(msg, inline_images)
        else:
            msg = EmailMessage(
                subject, bodies[html_ext], from_email, to, headers=headers
            )
            msg.content_subtype = "html"
            self._attach_inline_images(msg, inline_images)
        return msg
