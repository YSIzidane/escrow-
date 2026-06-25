import os
from io import BytesIO
from django.apps import apps
from django.db import connection
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.templatetags.static import static
from PIL import Image

# الحماية من هجمات Decompression Bomb عن طريق تحديد أقصى عدد من البكسلات (حوالي 100 ميجابكسل)
Image.MAX_IMAGE_PIXELS = 100_000_000


def safe_file_url(file_field, fallback="images/default_avatar.jpg"):
    """Return a URL for optional file fields without raising on empty files."""
    try:
        if file_field and getattr(file_field, "url", None):
            return file_field.url
    except (ValueError, AttributeError):
        pass
    return static(fallback)

def compress_image(image_field, max_width=800, max_height=800, quality=80):
    """
    دالة مساعدة لضغط وتصغير الصور المرفوعة 
    وتحويلها تلقائياً إلى صيغة WebP الخفيفة للحفاظ على أداء الموقع
    """
    if not image_field:
        return image_field

    try:
        # فتح الصورة باستخدام مكتبة Pillow
        img = Image.open(image_field)
        
        # تحويل الصورة إلى RGB في حال كانت بصيغة أخرى (شفافة RGBA أو P)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        # تصغير الصورة إذا تجاوزت الأبعاد المحددة مع الحفاظ على التناسب
        img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
        
        # حفظ الصورة المضغوطة في الذاكرة المؤقتة (Buffer) كملف WebP
        output = BytesIO()
        img.save(output, format='WEBP', quality=quality)
        output.seek(0)
        
        # استبدال الامتداد الأصلي للصورة بـ .webp
        filename = os.path.splitext(image_field.name)[0] + '.webp'
        
        # إعادة كائن InMemoryUploadedFile يقبله Django كملف جديد
        return InMemoryUploadedFile(
            output,
            'ImageField',
            filename,
            'image/webp',
            output.getbuffer().nbytes,
            None
        )
    except Exception as e:
        # في حال حدوث أي خطأ، نعيد الصورة الأصلية كما هي لمنع توقف النظام
        return image_field


def model_table_exists(model_or_label):
    if isinstance(model_or_label, str):
        model = apps.get_model(model_or_label)
    else:
        model = model_or_label

    try:
        return model._meta.db_table in connection.introspection.table_names()
    except Exception:
        return False
