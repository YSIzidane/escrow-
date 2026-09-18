# تقرير الفحص الشامل للمشروع (Audit Report)

**المشروع:** SafouaneEscrow — منصة ضمان الصفقات (Escrow)
**تاريخ الفحص:** 2026-07-15
**النطاق:** كامل الكود (Nماذج، عروض، خدمات، middleware، استهلاكات WebSocket، إعدادات، Docker، اختبارات، قوالب)

---

## 1. ملخص تنفيذي

المشروع مبني على Django 4.2 مع Channels (WebSocket)، Celery، Stripe، ومنطق deal engine مخصص. عموماً المعمارية منظمة بشكل معقول مع فصل للنماذج والعروض والخدمات، وهناك طبقة deal engine بحالة محدودة (state machine). مع ذلك، يوجد عدد من المشاكل الأمنية ومنطقية وأدائية يجب معالجتها قبل الإطلاق الرسمي.

### تصنيف المخاطر
- 🔴 حرجة (Critical): مشاكل قد تؤدي لفقد أموال أو اختراق بيانات.
- 🟠 عالية (High): ثغرات أمنية أو أخطاء منطقية خطيرة.
- 🟡 متوسطة (Medium): مشاكل أداء/جودة/صيانة.
- 🟢 منخفضة (Low): ملاحظات وممارسات جيدة.

---

## 2. المشاكل الحرجة 🔴

### 2.1 تعارض بين حالة الدفع وحالة الصفقة في `refund_payment_for_deal`
**الملف:** `main/views/payments.py` (الأسطر ~300–330)

عند تنفيذ الاسترداد يتم استدعاء `execute_deal_command("refund", deal=..., save=False)` ثم التلاعب يدوياً بالحقول:
```python
locked_deal.status = "new"
locked_deal.buyer = None
...
locked_deal.save()
```
المشكلة:
- `execute_deal_command` مع `save=False` لا يحدّث حالة الصفقة، لكن الـ deal engine expects `refund` ← `refunded`، ثم الكود يعيدها قسراً إلى `new`. هذا يتجاوز منطق الـ state machine ويسجل حدثاً بمصدر "refund" بينما الحالة الفعلية تصبح `new`، مما يكسر اتساق سجل `DealEvent`/`DealTransitionLog`.
- انتقال `STATE_REFUNDED → STATE_OPEN` مسموح في الـ transitions، لكن `legacy_status_for(STATE_REFUNDED)` = `"new"`، فالتعيين اليدوي إلى `"new"` قد يبدو متسقاً، لكنه يتجاوز القناة الرسمية ويزيد خطر عدم التزامن بين `Payment.status` و `Deal.status`.

**التوصية:** استخدام `execute_deal_command("reopen" أو "cancel")` لضبط الحالة بدلاً من التلاعب اليدوي، أو على الأقل حفظ الحالة عبر `legacy_status_for`.

### 2.2 معالجة Stripe Webhook دون ضمان Idempotency كافٍ
**الملف:** `main/views/payments.py` (`stripe_webhook` ~703–757) و `main/services/payment_service.py` (`process_successful_payment`)

رغم وجود `select_for_update` وحالات تخطّي عند `escrow_held/released/refunded`، إلا أن:
- خطأ `stripe.Webhook.construct_event` مع tolerance افتراضي قد يفشل عند التأخير الزمني ( replay attacks ).
- لا يوجد تسجيل صريح لـ `event["id"]` لمنع معالجة نفس الحدث مرتين (idempotency key غير مخزّن). إذا أعاد Stripe إرسال الحدث (وهو شائع)، قد تتم معالجته عدة مرات. الحالي يعتمد فقط على حالة الدفع، لكن في حالة سباقات التزامن (race conditions) محتمل تسجيل رسائل/إشعارات مكررة.
- يتم تجاهل أحداث Stripe الأخرى (مثل `payment_intent.payment_failed`) تماماً مع إرجاع 200 دون أي سجل، مما يعمّي المراقبة.

**التوصية:** تخزين `event.id` في جدول مخصص (ProcessedEvent) مع unique constraint، وتسجيل الأحداث غير المعروفة بدلاً من تجاهلها.

### 2.3 `transaction.atomic` غير مغلق بشكل صحيح في `release_payment_for_deal` عند فشل `execute_deal_command`
**الملف:** `main/views/payments.py` (~182–197)

```python
try:
    execute_deal_command("complete", ..., raise_on_error=True)
except DealEngineError as exc:
    raise PaymentStateError(exc.reason) from exc
```
الـ `raise` يخرج من الـ atomic block ويفيض الـ transaction — هذا صحيح. لكن `locked_payment.status = "released"` وخصم الرصيد يحدثان بعد التحويل. لو نجح `execute_deal_command` ثم فشل `Profile.objects.get(...)` (مثلاً لغياب profile للبائع)، سيتم rollback كل التغييرات بما فيها حالة الصفقة. هذا مقبول، لكن ملاحظة: الـ deal event سيُسجل ثم يُلغى — قد ينتج عنه سجل event بدون transition فعلي. عموماً الاتساق محفوظ، لكن **غياب `Profile` للبائع** (رغم وجود signal `create_profile`) ينسف العملية برمّتها. يجب ضمان وجود Profile دائماً.

### 2.4 CSRF معطّل على Stripe Webhook لكن دون تجاوز آمن لـ request.body
**الملف:** `main/views/payments.py` (`stripe_webhook` @csrf_exempt)

`request.body` يُقرأ مرة واحدة لتمريره لـ `construct_event`. هذا صحيح، لكن **لا يتم التحقق من حجم payload**. قد يستغل مهاجم إرسال body ضخم قبل التحقق من التوقيع. (Heartbleed-like DoS). يُنصح بالتحقق من `Content-Length` قبل قراءة body، أو استخدام `length ≤ N`.

### 2.5 لا يتم حذف `adjacent fields` (الطرف الآخر) عند قبول العرض (`accept_bid`)
**الملف:** `main/views/deals.py` (`accept_bid` ~623)

```python
deal.buyer = bid.bidder
deal.price = bid.amount
deal.status = "reserved"
deal.save()
```
- يتم التغيير المباشر لحالة الصفقة دون المرور بـ `execute_deal_command("reserve_deal")`.
- لا يتم التحقق أن العرض المقبول لا يزال صالحاً (الصفقة لم تُلغَ بين 350 و 400).
- `deal.bids.exclude(id=bid_id).update(is_rejected=True)` يتم بعد إنشاء الإشعار — يُفضل تسلسله.
- لا يوجد تأمين قفل `select_for_update` على الـ deal قبل التغيير — سباقات محتملة مع `finalize_expired_auctions` (والذي يلغي الصفقات منتهية المزايدة).

---

## 3. المشاكل عالية الخطورة 🟠

### 3.1 تعارض منطق المزادات (`tasks.py` يعتمد على `status="new"` دائماً)
**الملف:** `main/tasks.py` (`finalize_expired_auctions`)

- `Deal.objects.filter(is_auction=True, status="new", auction_ends_at__isnull=False, ...)`
لكن الـ deal engine يستنتج الحالة من الدفع أيضاً. إذا كانت الصفقة `status="new"` لكن تم حجزها عبر `reserve_deal` (دون تغيير status لأن `legacy_status_for("matched")="reserved"`)... في الواقع `reserve_deal` يضع `status="reserved"` فالشرط `status="new"` ينفيها. لكن إذا فشل التحويل midway، قد يبقى `status="new"` رغم وجود buyer. الحالي قد يلغي مزاداً له buyer معلق (pending payment) ويضعه في `expired`.
- `deal.save()` بدون `update_fields` يكتب كل الأعمدة.
- "بدون عروض" → `cancelled`، "مع عروض" → `expired`، لكن **لا يتم اختيار/تحديد فائز** ولا تغيير buyer، فقط إشعار. منطق "expired" هنا يعني انتظار اختيار البائع، لكن الحالة `expired` قد تُفهم كمنتهية نهائياً في الواجهة.

### 3.2 ضعف في غرف المستخدم عبر WebSocket (`EscrowChatConsumer`)
**الملف:** `main/consumers.py`

- لا يتم التحقق من عدم حظر/تعليق المستخدم (is_active) — حتى المستخدمون المعلّقون يمكنهم قراءة الرسائل إن كانوا طرفاً في الصفقة قديماً.
- `database_sync_to_async` لكل رسالة — استعلام 3-4 جداول لكل رسالة. على نطاق واسع سيؤدي إلى ضغط DB.
- لا يوجد حد أقصى لطول النص قبل الحفظ (`text = data.get("text", "").strip()`) — مستخدم سيء قد يرسل Python str ضخمة.
- `json.loads(text_data)` بدون try/except — payload غير صالح يكسر الاتصال.

### 3.3 `PrivateChatConsumer` لا يتعامل مع المرفقات
**الملف:** `main/consumers.py` (~173–234)

الكود يقبل فقط `text`. لكن `PrivateMessage` له حقل `file`. العميل قد يرسل `file_url` لكنه يُهمل. كما أنه لا يتم التحقق من content_type/size عند أي مسار رفع بديل.

### 3.4 كود ميت (Dead Code) في `confirm_deal`
**الملف:** `main/views/deals.py` (~450–478)

```python
def confirm_deal(request, deal_id):
    return _secure_confirm_deal(request, deal_id)
    """تأكيد الصفقة من كلا الطرفين."""
    deal = get_object_or_404(Deal, id=deal_id)
    ...
```
كل ما بعد `return` غير قابل للوصول (unreachable). يُبقي منطقاً قديماً م duplicado.

### 3.5 كود ميت ومحذوف في `confirm_delivery`
**الملف:** `main/views/deals.py` (~371–375)

```python
else:
    return _escrow_required_response(request, deal)
    messages.success(request, "تم تأكيد الاستلام.")  # unreachable
    if _is_ajax(request):
        return _ajax_response(request, "تم تأكيد الاستلام.")
```
عبارات بعد `return` غير قابلة للتنفيذ — قد يربك القراء ويُخفي قصداً غير منفذ.

### 3.6 `delete_comment` لا يتحقق من staff/admin
**الملف:** `main/views/deals.py` (~649–658)

المشرف المالي/العملياتي لا يستطيع حذف تعليق مسيء، فقط صاحب التعليق. أداة إشرافية ناقصة.

### 3.7 `deal_detail` POST handler ضخم جداً ومتعدد المسؤوليات
**الملف:** `main/views/deals.py` (~169–445)

العَرْض `deal_detail` يعالج: تعليق، رسالة، حجز، شحن، استلام، نزاع... في دالة واحدة بطول ~280 سطر. صعب الاختبار والصيانة. كما أن **التحقق من الصلاحيات متكرر وغير موحّد** (مثلاً `is_party` يحسب من المتغيرات بدلاً من helper مشترك).

### 3.8 `create_deal` يستثني بعض الحقول من validation في النموذج
**الملف:** `main/views/deals.py` (`create_deal`)

- `Deal.objects.create(...)` لا يستدعي `full_clean()` (الـ model لديه `save()` يستدعيها، لكن `objects.create` يستدعي `save`، فالتحقق يحدث). حسناً.
- لكن `delivery_time_val` يُقصّر بصمت إلى `None` عند الأرقام > 365. يجب مناداة المستخدم بدلاً من الإسكات.
- `platform` يُقص إلى 100 حرف بصمت — يجب رسالة خطأ.
- `try/except Exception` واسع جداً يلتقط كل الأخطاء ويعرض رسالة عامة، ما يُخفي الأخطاء الفعلية (سواء validator أو DB).

### 3.9 `compress_image` يحوّل كل الصور إلى WebP بصمت
**الملف:** `main/utils.py`

- تحويل `image/webp` للصور الرمزية/الصفقات قد يكون جيداً للأداء، لكنه **يُتلف الأسماء الأصلية** (يستبدل الامتداد) وقد يكسر أنظمة تتوقع png/jpeg.
- `except Exception: return image_field` يخفي أخطاء معالجة الصور بصمت.
- لا توجد حماية ضد الصور المشفّرة المعقدة، رغم `MAX_IMAGE_PIXELS` (هذا جيد). لكن قد تعلق أجزاء صغيرة من الصور الضارة.

### 3.10 `RateLimitMiddleware` غير فعّال على مستوى الإنتاج
**الملف:** `main/middleware.py` (~81–111)

- يخزّن قائمة timestamps في الـ Django cache. إذا كان cache = locmem (افتراضي)، فلا يتشارك بين workers → فعالية منخفضة.
- الحد 15 POST/دقيقة لطرف واحد فقط؛ IP واحد خلف NAT يمكن أن يُغرق ويعمّي مستخدمين.
- لا يوجد فصل بين endpoints حساسة (login, withdrawal) و غير حساسة.
- هيكل البيانات list grows بلا حد أقصى (رغم التنظيف كل 60s).

### 3.11 `SecurityHeadersMiddleware` يكرر ما تفعله Django settings
**الملف:** `main/middleware.py` + `core/settings.py`

- `X-Frame-Options`, `Referrer-Policy`, `X-Content-Type-Options` مضبوطة في settings عبر Django's security middleware/settings. إعادة تعيينها في الميدلوير زائدة، وقد تتسبب في ظهور رأسين أحياناً.
- `SECURE_BROWSER_XSS_FILTER = True` مهمل في Django 4 (X-XSS-Protection أزيل من المتصفحات الحديثة).
- تعليق HSTS يبرز إمكانية تفعيله عبر `SECURE_HSTS_SECONDS` (وهو مفعّل في settings) — ازدواجية محيرة.

---

## 4. المشاكل متوسطة الخطورة 🟡

### 4.1 إعدادات `requirements.txt` بدون تثبيت الإصدارات (Pinning)
**الملف:** `requirements.txt`

استخدام `>=4.2` و بدون قفل دقيق. هذا يُعرّض الإنتاج لكسور عند تحديث Django/Stripe. يُنصح بـ `pip freeze` إلى `requirements.lock` أو استخدام pip-tools.

### 4.2 قيم Stripe افتراضية كاشرة في كود
**الملف:** `core/settings.py` (~509–511)

```python
STRIPE_PUBLIC_KEY = os.getenv("STRIPE_PUBLIC_KEY", "pk_test_...")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "sk_test_...")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_...")
```
رغم وجود validation على `not DEBUG`، لكن القيم الافتراضية تكشف اختبارها في حال نسيان الضبط في Dev. يُستحسن رفع خطأ واضح حتى في Dev عند غيابها بدلاً من وضع placeholders.

### 4.3 استخدام `dict.fromkeys` ل تنظيف hosts/origins صحيح لكن غير موثّق
عموماً ممارسة جيدة، لكن يُفضّل استخدام `set` مع ترتيب صريح للقراءة.

### 4.4 `Model.save()` يستدعي `full_clean()` بشكل متكرر وثقيل
**الملفات:** كل النماذج في `main/models/deals.py` (Deal, DealMessage, DealFile, Bid)

في كل `save()` يُستدعى `full_clean()` الذي يفحص كل الحقول. عند التحديث الجزئي عبر `update_fields` لا تكون هذه مشكلة، لكن في عمليات الحفظ الكاملة (مثل `accept_bid` يفعل `deal.save()`) تتم إعادة الفحص — عبء غير ضروري.

### 4.5 `signals.py` لـ `create_profile` لا يتعامل مع تحديث User
**الملف:** `main/models/user.py` (~198–201)

```python
@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)
```
لا يوجد `save_profile`، لذلك **عند update User لا يُضمن وجود Profile**. إذا حُذف Profile يدوياً، فإن الكود يعتمد على `get_or_create` في العروض (وهذا يحدث)، لكن ليس مضموناً في كل المسارات.

### 4.6 `validate_kyc_file` wrapper زائد
**الملف:** `main/models/user.py` (~17–19)

```python
def validate_kyc_file(value):
    shared_validate_kyc_file(value)
```
مجرد wrapper بنفس الاسم. زائد تماماً، يمكن استيراد المشترك مباشرة.

### 4.7 `payment_state_for(deal)` يلتقط `Exception` عام
**الملف:** `main/deal_engine/states.py` (~67–71)

```python
try:
    return deal.payment.status
except Exception:
    return ""
```
`deal.payment` OneToOneField يثير `DoesNotExist` (لا `AttributeError`)؛ التقاط `Exception` يخفي أخطاء برمجية. الأصح `Payment.DoesNotExist`.

### 4.8 `deal_detail` يعيد `messages_list` فقط لـ `is_party`، لكن `is_party` يُحسب قبل معرفة auth
**الملف:** `main/views/deals.py` (~179–183)

تماماً: `request.user.is_authenticated and (...)`. حسناً. لكن إذا لم يكن party، تُعرض الصفقة دون رسائل — منطقي. ملاحظة فقط على التعقيد.

### 4.9 `OrderedDict` نوع الحقل `deal.deadlines` لا يُستخدم Geek
ملاحظة إيجابية: indexes مكتوبة جيداً. لكن `deadline.complete()` يستخدم `update_fields` — جيد.

### 4.10 التحقق من `content_type` غير موثوق في `create_deal` لرفع الصور
**الملف:** `main/views/deals.py` (~810–813)

```python
allowed_types = ["image/jpeg", "image/png", "image/gif", "image/webp"]
for image in images:
    if image.content_type in allowed_types:
        DealImage.objects.create(deal=deal, image=image)
```
- `content_type` يأتي من العميل وغير موثوق (يُstrebttuk).
- **لا يتم التحقق من امتداد الملف** (مثلاً `evil.exe` بـ content_type `image/jpeg`).
- الصور المرفوعة تُضغط لـ WebP تلقائياً في `DealImage.save()`، وهذا يخفف الخطأ، لكن الملف الخام قد يكون خبيثاً يُستهلك عند المعالجة.
- لا يوجد حد لعدد الصور إلا 10 — حسناً.

### 4.11 `payments.py` يستخدم `User.objects.filter(is_staff=True)` لإشعار كل المشرفين
**الملف:** `main/views/payments.py` (~500–507)

في Websocket/notifications، الإشعار لكل `is_staff=True` يشمل المشرفين غير المعنيين بالـ CCP. يُنصح الإشعار فقط لمجموعة `finance_admin`.

### 4.12 `Dockerfile` لا يقوم بـ collectstatic ولا يهيّئ `.env`
**الملف:** `Dockerfile`

- لا يوجد `RUN python manage.py collectstatic` — يجب تنفيذه في entrypoint أو مرحلة build.
- لا توجد `.env.production` مثال، بالرغم من `docker-compose.prod.yml` يطلبها.
- لا توجد stage متعددة (multi-stage build) لتقليل الحجم.
- `build-essential libpq-dev` يُثبّت لكن لا يحذف — حجم الصورة أكبر.

### 4.13 `WHITENOISE_ALLOW_ALL_ORIGINS = True` حتى في الإنتاج
**الملف:** `core/settings.py` (~419)

`True` يسمح بأي Origin للملفات الثابتة. رغم أن static files ليست حساسة عادةً، إلا أن تقييد الأصول هو ممارسة جيدة، خصوصاً ملفات الخطوط.

### 4.14 `CSRF_COOKIE_HTTPONLY = False`
**الملف:** `core/settings.py` (~610)

`False` ضروري لتجهيز CSRF لطلبات JS، لكنه يُكشف cookie للـ JS (XSS). في حال لا يوجد client JS يقرأ CSRF من cookie، يُفضّل تعيين الـ token عبر علامة meta في الـ template.

### 4.15 `SESSION_COOKIE_SAMESITE` configurable لكن قد يُكسر OAuth
**الملف:** `core/settings.py` (~611)

`Lax` الافتراضي جيد، لكن allauth (google OAuth) قد يحتاج `None` أو توجيه إضافي. ملاحظة فقط.

---

## 5. المشاكل منخفضة الخطورة / ملاحظات 🟢

### 5.1 `def validate_kyc_file(value):` بدون `# noqa`
مجرد تكرار، ضئيل.

### 5.2 استخدام `getattr(settings, "ESCROW_FEE_PERCENTAGE", 0.05)` و `Decimal(str(...))`
**الملف:** `main/views/payments.py` (~137–138)

```python
return int(Decimal(str(getattr(settings, "ESCROW_FEE_PERCENTAGE", 0.05))) * 100)
```
- `ESCROW_FEE_PERCENTAGE` ليس configurable عبر env (مكتوب hardcoded في settings).
- ضرب قيمة decimals بـ 100 قد يولّد دقة غير متوقعة. يجب ضبط السياسات صراحةً.

### 5.3 `payment_success` و `payment_cancel` تستخدم `login_required` بشكل غير متناسق
**الملف:** `main/views/payments.py` (~689–700)

`payment_cancel` لديها `@login_required`، `payment_success` لا. هذا المنطقد قد يكون مقصوداً (لأن Stripe قد يعيد توجيه بدون جلسة)، لكن `payment_success` يقرأ `deal_id` من `request.GET` بدون تحقق — قد يُستثمر لـopen redirect. عموماً محمي بـ`reverse`، لكن يُفضّل sanitize.

### 5.4 `core/asgi.py` يدعو `django.setup()` قبل استيراد `AuthMiddlewareStack`
هذا قد يثير تحذيرات حول الـ app registry. عموماً يحتاجه channels. صحيح.

### 5.5 الاختبارات شاملة قدر الإمكان لكن قد لا تغطي حالة `save=False` في `refund`
قائمة الاختبارات ممتازة وتشمل (`test_escrow_state_transitions`, `test_ccp_review`, `test_payments`, `test_permissions`...). ملاحظة: لا يوجد اختبار واضح لـ `stripe_webhook` idempotency.

### 5.6 `Buying/selling stats` في `deal_room` تنفّذ 8 استعلامات count
**الملف:** `main/views/deals.py` (~149–159)

كل `count()` يستعلم منفصلاً. يمكن استخدام `aggregate` واحد لتقليل الاستعلامات.

### 5.7 `templates/base.html` قد يحمل إشارات المرجع غير محمية
لم يُفحص عميقاً، لكن مع `X-Frame-Options=DENY` ينبغي ألا تكون الصفحة embeddable. حسناً.

### 5.8 `PAYMENT_METHOD_CHOICES` تشمل "ccp" فقط خيارين
يُفضّل قابلية التوسعة لطرق أخرى لاحقاً (مثلاً paypal مباشر).

### 5.9 `docker-compose.prod.yml` يضع `static_files` volume لكن لا يخدمها
الـ web container على 8000 فقط، ولا يوجد nginx revers proxy. يجب إضافة خدمة nginx أو caddy لخدمة static/media وتوسيع HTTPS.

### 5.10 لا توجد `gunicorn` في `requirements.txt`
**الملف:** `requirements.txt`

لا يوجد خادم WSGI/ASGI إنتاجي مدرج (gunicorn, uvicorn). يتم الاعتماد على داخنة `daphne` لـ channels، لكنها غالباً مؤجل للـ ports. يُنصح إضافة `uvicorn[standard]` أو `gunicorn` تحديداً.

### 5.11 `MIDDLEWARE` tidak menyertakan `django.middleware.security.SecurityMiddleware`... صح يوجد.
الميدلوير الأول `SecurityMiddleware`، لكن `WhiteNoiseMiddleware` يُدخل في index 1 فقط إذا `not USE_S3_STORAGE`. ترتيب صحيح.

### 5.12 تفاوت بين المنطق القديم (status) والـ deal engine
بشكل عام، التعيين `legacy_status_for` يخلق ازدواجاً بين حقل `Deal.status` (نص قديم) والحالة المستنتجة من engine. هذا يُصعّب التتبع. يُنصح على المدى البعيد التmigration إلى حقل `engine_state` واحد.

---

## 6. أخطاء محتملة أخرى

### 6.1 `EscrowChatConsumer.receive` لا يتعامل مع `TypeError` لو `json.loads` فشل
**الملف:** `main/consumers.py` (~69)

سيتسبب في إغلاق الاتصال بشكل صامت من جانب الخادم. يُنصح:
```python
try:
    data = json.loads(text_data)
except json.JSONDecodeError:
    return
```

### 6.2 `submit_bid` لا يتأكد من أن `min_bid_amount` يحقق زيادة `min_bid_increment`
عموماً صحيح: `min_amount = highest_bid.amount + deal.min_bid_increment if highest_bid else deal.starting_price`. لكن `Bid.save()` يستدعي `full_clean()` الذي لا يفحص علاقة بالـ deal — منطق العمل يتم في العَرْض فقط.

### 6.3 `delete_deal` يسمح بالحذف فقط إذا `status="new"`
ولكن لا يتحقق من وجود معلقات (bids, payment pending). حذف صفقة لها bids يحذف الـ bids ضمنياً (CASCADE) دون إشعار المزاودين. يجب إشعارهم أو حفظ حسابهم.

### 6.4 `Profile.save()` يستدعي `compress_image` لكن يقارن `old_profile.avatar != self.avatar`
**الملف:** `main/models/user.py` (~67–78)

مقارنة `FileField` تُقارن names. إذا أُعيد رفع نفس الملف (نفس الاسم)، فلن يُعاد ضغط الصورة. لكن إذا تغير اسم الـ file فقط، قد يُعالَج بشكل صحيح. منطق معقول لكنه قد يتجاهل صورة جديدة بنفس الاسم.

### 6.5 `payments.py`: `_resolve_platform_owner_profile` يلتقط أي superuser
**الملف:** `main/views/payments.py` (~127–134)

إذا لم يُحدد `PLATFORM_OWNER_USERNAME`، يتم اختيار أقدم superuser كمالك. هذا قد يكون خطيراً لو حُذف صاحب المنصة وأصبح superuser آخر يتلقى الرسوم عنوة. يجب فرض `PLATFORM_OWNER_USERNAME` في الإنتاج.

### 6.6 `admin_withdrawals_list` عند الرفض يُعيد المبلغ للرصيد لكن لا يلغي `admin_note`
**الملف:** `main/views/staff.py` (~948–968)

عند `reject`، يتم `profile.balance += w_req.amount`. لكن لا توجد حماية من **الرفض المتكرر** (status يصبح `rejected`، فلن يُعالج ثانية — حسناً). لكن **لا يوجد تسجيل** (`_log_admin_action`) لعملية الرفض. يُفضّل إضافة audit log.

### 6.7 `staff_ticket_detail` "delete_ticket" لا يحذف فعلياً — يضع status=closed
**الملف:** `main/views/staff.py` (~625–629)

```python
elif action == 'delete_ticket':
    ticket.status = 'closed'
    ticket.save(update_fields=['status'])
    messages.success(request, "تم حذف التذكرة نهائياً.")
```
العنوان يقول "حذف نهائياً" لكنه مجرد إغلاق — تضليل للمشرف.

---

## 7. توصيات الإصلاح حسب الأولوية

### فوري (قبل أي إطلاق)
1. **إصلاح `refund_payment_for_deal`** لاستخدام engine بشكل صحيح (`#2.1`).
2. **إضافة Idempotency لـ Stripe Webhook** (`#2.2`).
3. **تأمين `accept_bid`** مع `select_for_update` و `execute_deal_command` (`#2.5`).
4. **إضافة `PLATFORM_OWNER_USERNAME` إلزامي في الإنتاج** (`#6.5`).

### قصير المدى
5. **حذف الكود الميت** في `confirm_deal` و `confirm_delivery` (`#3.4`, `#3.5`).
6. **تحقق موثوق من امتداد الصور** في `create_deal` (`#4.10`).
7. **تقسيم `deal_detail` POST** إلى عدة عروض صغيرة (`#3.7`).
8. **تحسين `RateLimitMiddleware`** باستخدام Redis corpus counters وتمييز endpoints (`#3.10`).
9. **إضافة حماية WebSocket** لطول النص و payload صالح (`#3.2`, `#6.1`).

### متوسط المدى
10. **قفل نسخ dependencies** (`#4.1`).
11. **إضافة gunicorn/uvicorn** لـ requirements (`#5.10`).
12. **خدمة nginx لـ static/media** في docker prod (`#5.9`, `#4.12`).
13. **توحيد الحالة**: حقل `engine_state` واحد في Deal، التخلص من `legacy_status_for` (`#5.12`).
14. **إزالة تكرار security headers** بين middleware وsettings (`#3.11`).
15. **توسعة الاختبارات** لتشمل idempotency لـ webhook ومنطق المزادات المتزامن (`#5.5`).

### طويل المدى
16. **فصل منطق الضغط (compress_image)** بشكل أفضل وعدم إتلاف الأسماء (`#3.9`).
17. **استخدام Django's `Permission` و`Group` بشكل أفضل** في `admin_roles` بدلاً من إعادة إنشاء العجلة.
18. **مراجعة شاملة لكل `except Exception`** والاستبدال بـ exceptions محددة.
19. **تدقيق القوالب** بحثاً عن XSS (طالما لم يُفحص عميقاً في هذا التقرير).

---

## 8. ملاحظات إيجابية

- **فصل النماذج** في `main/models/` حسب النطاق (deals, payments, user...) — ممارسة ممتازة.
- **وجود state machine** (`deal_engine`) و سجلات انتقال (`DealEvent`, `DealTransitionLog`) — أساس جيد للتدقيق.
- **استخدام `select_for_update`** في المسارات المالية الحرجة — يقلل سباقات البيانات.
- **وجود layer تحقق الملفات** (`validators.py` مركزي) — جيد.
- **مجموعة اختبارات شاملة** (~24 ملف) تغطي محاور متعددة — استثمار جيد في الجودة.
- **تطبيق security headers و HTTPS/HSTS** في settings — ممارسة إنتاجية سليمة.
- **جهد في i18n** (ar/en) عبر `main/i18n/` — يدعم التجربة.

---

## 9. خاتمة

المشروع في حالة جيدة من حيث التنظيم الأساسي، لكن **المسارات المالية ومنطق الحالة** بحاجة لتدقيق أعمق وإصلاحات فورية قبل أي إنتاج. الكود الميت ومستوى الـ dead duplication يشيرون لمراحل refactor ناقصة. النشر في الإنتاج يتطلب إضافة nginx/ASGI server production-grade وضبط أكثر صرامة للتكوين.

**التقييم العام:** 🟠 جيد لكن يحتاج إصلاحات قبل الإطلاق.

---
*تم إعداد هذا التقرير بناءً على فحص ثابت (static review) للكود. يُنصح بإجراء اختبارات اختراق (penetration test) ومراجعة runtime قبل الإطلاق الرسمي.*