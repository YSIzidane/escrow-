# تقرير تحليل شامل لمشروع SafouaneEscrow

تاريخ المراجعة: 2026-05-14  
النطاق: Backend، Frontend، الأمان، الدفع، الضمان Escrow، السحب، الغرف، المحادثة، الملفات، النشر، والاختبارات.

## 1. الخلاصة التنفيذية

المشروع مبني على Django + Channels + Celery + PostgreSQL/Redis + Stripe، وفيه بنية جيدة نسبيًا لمنصة سوق بضمان: نماذج واضحة، فصل جزئي لمنطق الدفع في service layer، اختبارات كثيرة، تحقق من إعدادات الإنتاج، حماية للملفات الحساسة، وسجلات تدقيق لعمليات الدفع.

لكن المشروع غير جاهز للإطلاق الحقيقي قبل معالجة عدة نقاط عالية الخطورة:

1. صفحات الغرف والـ escrow مكسورة حاليًا بسبب أخطاء Template syntax.
2. منطق الصفقة يسمح بإكمال صفقة أو تغيير حالتها بعد إنشاء Payment معلّق، حتى لو لم يتم احتجاز المال فعليًا.
3. الدفع اليدوي CCP يمكن أن يحجز الصفقة لمستخدم بإثبات مزيف، والرفض لا يعيد الصفقة لحالة متاحة.
4. "تحرير الأموال" حاليًا تحديث داخلي لرصيد البائع فقط، وليس تحويلًا ماليًا حقيقيًا عبر Stripe Connect أو بوابة payout.
5. التحقق من الملفات يعتمد على الامتداد والحجم فقط، وليس MIME/magic bytes أو فحص محتوى.
6. لا يوجد Content Security Policy، والـ rate limiting ضعيف في بيئة متعددة العمليات.

التقييم العام:

- جودة الهيكل: جيدة.
- جاهزية MVP خاص/تجريبي: متوسطة بعد إصلاح أخطاء القوالب.
- جاهزية إطلاق عام بأموال حقيقية: غير كافية حاليًا.
- أكبر خطر: منطق حالة الصفقة والدفع، لا البنية العامة.

## 2. نتائج الفحص والتشغيل

الأوامر التي تم تشغيلها:

- `.\venv\Scripts\python.exe manage.py check`
  - النتيجة: ناجح، لا توجد مشاكل نظامية.

- `.\venv\Scripts\python.exe manage.py check --deploy`
  - النتيجة: 6 تحذيرات بسبب إعدادات التطوير الحالية: `DEBUG=True`، عدم تفعيل HTTPS redirect، secure cookies، HSTS include subdomains/preload.
  - ملاحظة: هذه التحذيرات متوقعة محليًا، لكن يجب أن تختفي في الإنتاج عبر `.env.production`.

- اختبارات الدفع/السحب/الصلاحيات/الملفات:
  - `68 tests`
  - النتيجة: ناجحة.

- مجموعة بقية الاختبارات:
  - `68 tests`
  - النتيجة: فشلت بـ 12 خطأ بسبب قوالب `room.html` و`escrow_room.html`.

الأخطاء المؤكدة:

- `templates/room.html:8`
  - يستخدم `{% static %}` بدون `{% load static %}`.

- `templates/room.html:8` و`templates/escrow_room.html:285`
  - توجد صيغة غير صحيحة داخل `{% static \'images/brand/room-bg.png\' %}`.
  - الصيغة الصحيحة يجب أن تكون مثل:
    - `{% static 'images/brand/room-bg.png' %}`

## 3. نقاط القوة

### Backend

- استخدام Django ORM وقيود علاقات واضحة.
- وجود `transaction.atomic()` و`select_for_update()` في مسارات مالية مهمة مثل release/refund والسحب.
- فصل منطق الدفع الناجح في `main/services/payment_service.py`.
- وجود audit logs لعمليات الدفع اليدوي والتحرير والاسترداد.
- وجود اختبارات كثيرة تغطي الدفع، السحب، الصلاحيات، الملفات الحساسة، الإعدادات، والغرف.

### الأمان

- تفعيل CSRF middleware.
- معظم النماذج تحتوي `{% csrf_token %}`.
- حماية ملفات KYC وCCP والمرفقات الخاصة عبر views مخصصة بدل فتح `/media` بالكامل.
- تحقق production runtime يمنع SQLite/غياب Redis/غياب Celery في الإنتاج.
- Stripe webhook يتحقق من التوقيع.

### التشغيل والنشر

- Dockerfile وdocker-compose للإنتاج والتطوير.
- health endpoint.
- Celery worker وbeat موجودان.
- إعدادات Redis/Channels موجودة.

## 4. عيوب حرجة وعالية الأولوية

### A. صفحات الغرف مكسورة حاليًا

المواقع:

- `templates/room.html:8`
- `templates/escrow_room.html:285`

الأثر:

- صفحة الغرفة العادية لا تعمل.
- صفحة غرفة الضمان يمكن أن تفشل عند render.
- عدة اختبارات تفشل بسبب ذلك.
- هذا كسر مباشر في UX وفي تدفق escrow/chat.

الإصلاح:

- إضافة `{% load static site_i18n %}` في `room.html`.
- استبدال الصيغة الخاطئة:
  - `{% static \'images/brand/room-bg.png\' %}`
  - بـ `{% static 'images/brand/room-bg.png' %}`.

الأولوية: P0.

### B. يمكن إكمال صفقة بدون احتجاز مال فعلي

المواقع:

- `main/views/payments.py:276` إنشاء Payment بحالة `pending`.
- `main/views/payments.py:441` إنشاء Stripe Checkout.
- `main/views/deals.py:235` مسار `confirm_delivery`.
- `main/views/deals.py:325` مسار `confirm_deal`.

المشكلة:

عند بدء الدفع، يتم إنشاء `Payment` بحالة `pending` وربط المستخدم كـ buyer. بعد ذلك، بعض مسارات الصفقة تسمح بتغيير الحالة إلى completed إذا لم تكن حالة الدفع `escrow_held`.

الخطر:

- مشتري يبدأ checkout ولا يدفع.
- يصبح buyer أو يملك Payment pending.
- قد يصل لمسارات تأكيد/إكمال تجعل الصفقة completed بدون مال محجوز.
- هذا يناقض فكرة escrow-first.

الإصلاح:

- لا تسمح بأي `confirm_delivery` أو `confirm_deal` يؤدي إلى completed إلا إذا:
  - `payment.status == "escrow_held"`، أو
  - نوع الصفقة لا يحتاج مالًا ويكون هذا موثقًا في نموذج منفصل.
- اجعل حالة الصفقة بعد بدء checkout مثل `payment_pending` لا `reserved`.
- اربط زر/endpoint التسليم بشرط payment held من السيرفر، وليس الواجهة فقط.

الأولوية: P0.

### C. الدفع اليدوي CCP يمكن أن يحجز الصفقة بإثبات غير مقبول

المواقع:

- `main/views/payments.py:366`
- `main/views/payments.py:420`
- `main/views/staff.py:1058`

المشكلة:

عند رفع إثبات CCP، يتم تعيين `deal.buyer = request.user` قبل موافقة الإدارة. عند الرفض، يتم إرجاع الدفع إلى `pending` أو `failed_max_retries`، لكن لا يظهر أن الصفقة تعود لحالة متاحة أو أن `buyer` يُمسح.

الخطر:

- مستخدم سيئ يرفع إثباتًا مزيفًا.
- الصفقة تصبح محجوزة له.
- حتى بعد الرفض، يمكن أن تبقى الصفقة مقفلة عمليًا أمام مشترين آخرين.

الإصلاح:

- لا تجعل `deal.buyer` نهائيًا إلا بعد موافقة الدفع.
- استخدم حقل منفصل مثل `pending_buyer`.
- عند رفض CCP، أعد الصفقة إلى `new` وامسح buyer إذا لم يكن الدفع held.
- عند `failed_max_retries`، يجب تحرير الصفقة تلقائيًا.

الأولوية: P0.

### D. تحرير الأموال ليس تحويلًا ماليًا حقيقيًا

الموقع:

- `main/views/payments.py:129`

المشكلة:

`release_payment_for_deal` يضيف الرصيد إلى `Profile.balance` ويحسب fee/net داخليًا، لكنه لا ينفذ تحويلًا فعليًا للبائع. Stripe Checkout عادة يضع المال في حساب المنصة، وليس في حساب البائع.

الخطر:

- المنتج قد يوحي بأن المال أُرسل للبائع، بينما هو مجرد رصيد داخلي.
- يتطلب ذلك عملية سحب لاحقة يدوية أو Stripe Connect.
- في إطلاق حقيقي، هذا خطر تشغيلي وقانوني ومحاسبي.

الإصلاح:

- توضيح المنتج: release = نقل إلى رصيد داخلي قابل للسحب.
- أو تنفيذ Stripe Connect transfers/payouts.
- إضافة Ledger منفصل immutable بدل الاعتماد على `Profile.balance` فقط.
- تسجيل كل حركة مالية في جدول ledger: hold, release, fee, withdrawal_request, withdrawal_processed, refund.

الأولوية: P0 قبل المال الحقيقي.

### E. التحقق من الملفات ضعيف

المواقع:

- `main/validators.py:42`
- `main/views/staff.py:116`
- `main/views/core.py:326`

المشكلة:

التحقق يعتمد على الامتداد والحجم. يمكن رفع ملف باسم `.jpg` أو `.pdf` لا يحتوي النوع الحقيقي المتوقع. يتم تقديم بعض الملفات باستخدام MIME حسب الاسم.

الخطر:

- رفع محتوى خبيث أو ملف polyglot.
- خطر XSS أو تسريب/تنفيذ عبر متصفح حسب content type.
- خطر تخزين مستندات KYC غير آمنة.

الإصلاح:

- استخدام `python-magic` أو Pillow verification للصور.
- إعادة ترميز الصور بعد التحقق.
- للـ PDF: تحقق magic header واعتبرها attachment دائمًا.
- أضف فحص antivirus في الإنتاج للملفات الحساسة.
- استخدم أسماء عشوائية لكل المرفقات وليس فقط بعض المسارات.

الأولوية: P1.

## 5. أمان التطبيق

### نقاط جيدة

- `validate_production_runtime` يمنع إعدادات خطيرة في الإنتاج مثل SQLite وغياب Redis.
- Cookies secure وHSTS تتحول تلقائيًا عند `DEBUG=False`.
- `SESSION_COOKIE_HTTPONLY=True`.
- معظم الملفات الحساسة لا تُخدم مباشرة.

### مشاكل وتحسينات

1. لا يوجد Content-Security-Policy.
   - الموقع يستخدم inline CSS/JS بكثرة، لذلك تنفيذ CSP سيكون تدريجيًا.
   - ابدأ بـ `Content-Security-Policy-Report-Only`.

2. `RateLimitMiddleware` بسيط جدًا.
   - `main/middleware.py:39`
   - يعتمد على cache الافتراضي وقد لا يكون Redis.
   - لا يغطي GET/الـ polling/الـ WebSocket.
   - يثق بـ `X-Forwarded-For` مباشرة في `main/middleware.py:71`.

3. `ALLOWED_HOSTS` و`CSRF_TRUSTED_ORIGINS` يضيفان ngrok دائمًا.
   - `core/settings.py:235-263`
   - مناسب للتطوير، لكن الأفضل أن يكون مشروطًا بـ DEBUG أو env.

4. health endpoint يكشف بعض معلومات التهيئة.
   - `main/views/core.py:291`
   - لا يكشف أسرارًا، لكنه يعرض `debug`, `redis_configured`, `stripe_configured`.
   - في الإنتاج العام يمكن جعله أبسط أو خلف مراقبة داخلية.

5. WebSocket يحتاج حدودًا.
   - `main/consumers.py`
   - أضف حد طول الرسالة، معالجة JSON errors، rate limit، وإعادة تحقق الصلاحية عند كل receive للغرف الحساسة.

الأولوية: P1-P2.

## 6. الدفع والـ Escrow

### Stripe

إيجابيات:

- إنشاء Checkout session منطقي.
- webhook يتحقق من التوقيع.
- refund يستخدم PaymentIntent/Charge عند توفره.

تحسينات مهمة:

- في `stripe_webhook` تحقق من:
  - `session.payment_status == "paid"`.
  - `session.amount_total == int(deal.price * 100)`.
  - `session.currency == settings.STRIPE_CURRENCY`.
  - أن `buyer_id` يطابق buyer المتوقع أو pending buyer.

- احفظ `payment_intent` بوضوح بدل خلط `session.id` و`payment_intent` في `transaction_id`.

- اجعل webhook idempotency أقوى:
  - خزّن `stripe_event_id`.
  - تجاهل event تمت معالجته سابقًا.

### CCP / BaridiMob

إيجابيات:

- مسار مراجعة يدوي.
- حد محاولات.
- proof files محمية عن العامة.
- audit log عند الموافقة/الرفض.

تحسينات:

- لا تحجز الصفقة نهائيًا قبل موافقة الإدارة.
- أضف تحققًا من reference number uniqueness إن كان المرجع يفترض أن يكون فريدًا.
- أضف شاشة مقارنة واضحة للمراجع المالية.
- عند الرفض النهائي، حرر الصفقة وأرسل إشعارًا واضحًا.

### السحب

إيجابيات:

- السحب معطل افتراضيًا.
- في الإنتاج لا يسمح بتفعيله بدون `ALLOW_MANUAL_WITHDRAWALS_IN_PRODUCTION=True`.
- عند إنشاء طلب السحب يتم قفل الرصيد بـ `select_for_update`.

تحسينات:

- إنشاء Ledger مالي منفصل.
- تشفير أو masking تفاصيل السحب البنكية/crypto في admin.
- إضافة 2FA أو re-auth للعمليات المالية الكبيرة.

## 7. صلاحيات الإدارة والملفات الحساسة

نقاط جيدة:

- أدوار منفصلة: support, finance, operations, security.
- ملفات KYC/CCP/private messages/tickets تُخدم عبر views تتحقق من الصلاحية.
- صفحات staff تضيف no-cache وnoindex.

تحسينات:

- أضف سجل تدقيق لكل عمليات KYC وتغيير أدوار المستخدمين والغرف.
- أضف re-auth للعمليات الإدارية الحساسة: approve payment, refund, process withdrawal, change admin roles.
- تأكد أن أي staff user بلا group لا يحصل على صلاحيات legacy غير مقصودة.

## 8. Frontend وتجربة المستخدم

نقاط جيدة:

- واجهات كثيرة ومتكاملة: marketplace، profile، rooms، escrow، support، admin.
- CSRF موجود في أغلب النماذج.
- الرسائل الجديدة تستخدم escaping في عدة أماكن.
- هناك مراعاة للموبايل والـ polling.

مشاكل:

1. Inline CSS/JS ضخم جدًا داخل القوالب.
   - يصعب CSP.
   - يصعب الاختبار.
   - يزيد خطر أخطاء القوالب مثل الخطأ الحالي.

2. تكرار منطق AJAX/polling بين:
   - `static/js/main.js`
   - `templates/deal_detail.html`
   - `templates/room.html`
   - `templates/private_chat.html`
   - `templates/escrow_room.html`

3. لا توجد pipeline واضحة للـ frontend:
   - لا lint.
   - لا bundling.
   - لا اختبارات UI.

4. ملفات CSS كثيرة ومتشعبة.
   - `static/css/main.css`, `improvements.css`, `desktop_light.css`, `mobile_lite.css`, وغيرها.
   - خطر تضارب styles وارتفاع تكلفة الصيانة.

التحسين:

- نقل JS من القوالب إلى ملفات modules.
- توحيد helper للـ async forms.
- توحيد chat renderer.
- إضافة smoke tests بPlaywright للصفحات الأساسية.
- إدخال CSP تدريجيًا بعد تقليل inline scripts.

## 9. قاعدة البيانات والنماذج

ملاحظات:

- `Deal.save()` يستدعي `full_clean()` وهذا جيد للسلامة لكنه قد يزيد تكلفة عمليات bulk أو migrations.
- `Payment` لديه `OneToOneField` مع `Deal`، مناسب لو كل صفقة لها عملية دفع واحدة فقط. لكنه يحد من تاريخ المحاولات.
- `Payment.transaction_id` unique لكنه يخلط Stripe session/payment_intent وCCP IDs.
- `Review` لا يحتوي constraint يمنع duplicate review على مستوى قاعدة البيانات؛ المنع حاليًا في view فقط.

تحسينات:

- أضف database constraints:
  - review unique `(deal, reviewer)`.
  - bid constraints للمبلغ الموجب.
  - payment amount positive.
  - withdrawal amount positive.

- افصل payment attempts عن payment final state:
  - `PaymentAttempt`
  - `Payment`
  - `LedgerEntry`

## 10. الغرف والمحادثة

نقاط جيدة:

- access control موجود في `Room.can_user_access`.
- private chat يتطلب friendship accepted.
- escrow chat يتحقق من buyer/seller/admin عند الاتصال.

مشاكل:

- كود room invite يستخدم `random.choice` وليس `secrets`.
- لا يوجد rate limit للرسائل.
- لا يوجد حد طول في بعض WebSocket consumers.
- لا توجد معالجة JSONDecodeError.
- الغرف تعتمد على code فقط للدخول؛ 8 أحرف جيدة نسبيًا، لكنها دعوة bearer token عمليًا.

تحسين:

- استخدم `secrets.choice`.
- زد الطول إلى 10-12.
- أضف expires_at أو rotate invite code.
- أضف throttling للرسائل.
- أضف moderation/reporting سريع من داخل chat.

## 11. النشر والتشغيل

نقاط جيدة:

- Docker production stack موجود.
- web + celery worker + celery beat + db + redis.
- healthcheck موجود.
- production env example جيد.

تحسينات:

- لا تشغل migrations تلقائيًا في كل web container في production متعدد النسخ بدون سياسة واضحة.
- Redis في production compose يحتاج تأمين أفضل للشبكة وعدم نشره خارجيًا.
- أضف logging JSON منظم.
- أضف Sentry/OpenTelemetry.
- أضف backup/restore runbook لPostgreSQL وmedia.
- أضف collectstatic validation في CI.

## 12. الاختبارات

نقاط قوية:

- وجود 145 اختبارًا تقريبًا.
- تغطية جيدة للمسارات الحساسة: payments, withdrawals, permissions, sensitive media.

المشاكل:

- التشغيل الكامل ثقيل جدًا؛ 68 اختبارًا استغرقت تقريبًا 295 ثانية.
- أخطاء القوالب لم تمنع `manage.py check` لكنها ظهرت في tests.
- لا يظهر وجود CI pipeline.

تحسين:

- تقسيم الاختبارات إلى:
  - unit سريع.
  - integration.
  - smoke templates.
  - payment flow.
- إضافة test لكل template أساسي:
  - home
  - listings
  - deal_detail
  - room
  - escrow_room
  - profile
  - checkout
  - staff pages

## 13. قائمة الأولويات المقترحة

### P0 - قبل أي تجربة عامة

1. إصلاح `room.html` و`escrow_room.html`.
2. منع إكمال أي صفقة بدون `payment.status == escrow_held`.
3. إصلاح منطق CCP حتى لا يحجز الصفقة قبل الموافقة.
4. توضيح/إعادة تصميم release: رصيد داخلي أم تحويل حقيقي؟
5. تشغيل كل الاختبارات بنجاح.

### P1 - قبل أموال حقيقية

1. Ledger مالي كامل.
2. Stripe webhook verification أقوى.
3. فحص ملفات حقيقي.
4. CSP Report-Only ثم CSP فعلي.
5. Rate limiting عبر Redis.
6. WebSocket limits and throttling.
7. re-auth/2FA للعمليات المالية والإدارية.

### P2 - تحسين المنتج والصيانة

1. تنظيم CSS/JS.
2. Playwright smoke tests.
3. Monitoring/logging.
4. CI/CD.
5. تحسين performance للصفحات الثقيلة.
6. مراجعة نصوص i18n والتخلص من mojibake الظاهر في بعض الملفات/outputs.

## 14. الحكم النهائي

المشروع لديه أساس جيد، لكن الخطر الأكبر ليس في Django نفسه، بل في قواعد العمل المالية: متى تصبح الصفقة محجوزة؟ متى تعتبر مدفوعة؟ متى يسمح بالتسليم؟ ومتى يصبح الرصيد قابلًا للسحب؟

إذا أصلحت P0، سيصبح المشروع مناسبًا لتجربة MVP مغلقة.  
إذا أصلحت P1، يمكن التفكير في إطلاق أوسع بأموال حقيقية مع مراقبة وتشغيل جديين.
