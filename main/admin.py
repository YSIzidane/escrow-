from django.contrib import admin

from .models import (
    Bid,
    Deal,
    DealComment,
    DealFile,
    DealImage,
    DealMessage,
    EscrowMessage,
    EscrowRoom,
    Friendship,
    Notification,
    Payment,
    PaymentAuditLog,
    PrivateMessage,
    Profile,
    Review,
    Room,
    RoomMessage,
    RoomParticipant,
    SiteSettings,
    SupportTicket,
    TicketReply,
    TradeExchange,
    TransactionInvoice,
    WithdrawalRequest,
)


admin.site.site_header = "Escrow Project Administration"
admin.site.site_title = "Escrow Admin"
admin.site.index_title = "Management Dashboard"
admin.site.empty_value_display = "-"


class BaseAdmin(admin.ModelAdmin):
    list_per_page = 25
    ordering = ("-id",)


class DealImageInline(admin.TabularInline):
    model = DealImage
    extra = 0
    fields = ("image", "uploaded_at")
    readonly_fields = ("uploaded_at",)


class DealFileInline(admin.TabularInline):
    model = DealFile
    extra = 0
    fields = ("file", "uploader", "uploaded_at")
    readonly_fields = ("uploaded_at",)
    autocomplete_fields = ("uploader",)


class BidInline(admin.TabularInline):
    model = Bid
    extra = 0
    fields = ("bidder", "amount", "is_accepted", "is_rejected", "created_at")
    readonly_fields = ("created_at",)
    autocomplete_fields = ("bidder",)


class TicketReplyInline(admin.TabularInline):
    model = TicketReply
    extra = 0
    fields = ("sender", "message", "attachment", "is_staff_reply", "created_at")
    readonly_fields = ("created_at",)
    autocomplete_fields = ("sender",)


class EscrowMessageInline(admin.TabularInline):
    model = EscrowMessage
    extra = 0
    fields = ("sender", "text", "is_admin", "created_at")
    readonly_fields = ("created_at",)
    autocomplete_fields = ("sender",)


@admin.register(Deal)
class DealAdmin(BaseAdmin):
    list_display = (
        "id",
        "product_title",
        "seller",
        "buyer",
        "price",
        "status",
        "is_auction",
        "buyer_confirmed",
        "seller_shipped",
        "created_at",
    )
    list_filter = ("status", "is_auction", "created_at", "updated_at")
    search_fields = ("product_title", "seller__username", "buyer__username")
    readonly_fields = ("created_at", "updated_at")
    list_select_related = ("seller", "buyer")
    autocomplete_fields = ("seller", "buyer")
    inlines = (DealImageInline, DealFileInline, BidInline)


@admin.register(DealMessage)
class DealMessageAdmin(BaseAdmin):
    list_display = ("id", "deal", "sender", "created_at")
    list_filter = ("created_at",)
    search_fields = ("deal__product_title", "sender__username", "text")
    list_select_related = ("deal", "sender")
    autocomplete_fields = ("deal", "sender")
    readonly_fields = ("created_at",)


@admin.register(Review)
class ReviewAdmin(BaseAdmin):
    list_display = ("id", "deal", "reviewer", "rated_user", "rating", "created_at")
    list_filter = ("rating", "created_at")
    search_fields = ("reviewer__username", "rated_user__username", "deal__product_title")
    list_select_related = ("deal", "reviewer", "rated_user")
    autocomplete_fields = ("deal", "reviewer", "rated_user")
    readonly_fields = ("created_at",)


@admin.register(Bid)
class BidAdmin(BaseAdmin):
    list_display = ("id", "deal", "bidder", "amount", "is_accepted", "is_rejected", "created_at")
    list_filter = ("is_accepted", "is_rejected", "created_at")
    search_fields = ("bidder__username", "deal__product_title")
    list_select_related = ("deal", "bidder")
    autocomplete_fields = ("deal", "bidder")
    readonly_fields = ("created_at",)


@admin.register(DealFile)
class DealFileAdmin(BaseAdmin):
    list_display = ("id", "deal", "uploader", "uploaded_at")
    list_filter = ("uploaded_at",)
    search_fields = ("deal__product_title", "uploader__username")
    list_select_related = ("deal", "uploader")
    autocomplete_fields = ("deal", "uploader")
    readonly_fields = ("uploaded_at",)


@admin.register(DealImage)
class DealImageAdmin(BaseAdmin):
    list_display = ("id", "deal", "uploaded_at")
    list_filter = ("uploaded_at",)
    search_fields = ("deal__product_title",)
    list_select_related = ("deal",)
    autocomplete_fields = ("deal",)
    readonly_fields = ("uploaded_at",)


@admin.register(DealComment)
class DealCommentAdmin(BaseAdmin):
    list_display = ("id", "deal", "author", "parent", "created_at")
    list_filter = ("created_at",)
    search_fields = ("deal__product_title", "author__username", "text")
    list_select_related = ("deal", "author", "parent")
    autocomplete_fields = ("deal", "author", "parent")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Profile)
class ProfileAdmin(BaseAdmin):
    list_display = ("id", "user", "phone", "is_verified", "verification_tier", "kyc_status", "balance", "created_at")
    list_filter = ("is_verified", "verification_tier", "kyc_status", "created_at")
    search_fields = ("user__username", "user__email", "phone")
    list_select_related = ("user",)
    autocomplete_fields = ("user",)
    readonly_fields = ("created_at",)


@admin.register(Friendship)
class FriendshipAdmin(BaseAdmin):
    list_display = ("id", "from_user", "to_user", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("from_user__username", "to_user__username")
    list_select_related = ("from_user", "to_user")
    autocomplete_fields = ("from_user", "to_user")
    readonly_fields = ("created_at",)


@admin.register(PrivateMessage)
class PrivateMessageAdmin(BaseAdmin):
    list_display = ("id", "sender", "receiver", "created_at")
    list_filter = ("created_at",)
    search_fields = ("sender__username", "receiver__username", "text")
    list_select_related = ("sender", "receiver")
    autocomplete_fields = ("sender", "receiver")
    readonly_fields = ("created_at",)


@admin.register(WithdrawalRequest)
class WithdrawalRequestAdmin(BaseAdmin):
    list_display = ("id", "user", "amount", "method", "status", "created_at")
    list_filter = ("method", "status", "created_at")
    search_fields = ("user__username", "details")
    list_select_related = ("user",)
    autocomplete_fields = ("user",)
    readonly_fields = ("created_at",)


class RoomParticipantInline(admin.TabularInline):
    model = RoomParticipant
    extra = 0
    fields = ("user", "role", "joined_at")
    readonly_fields = ("joined_at",)
    autocomplete_fields = ("user",)


@admin.register(Room)
class RoomAdmin(BaseAdmin):
    list_display = ("id", "code", "title", "creator", "room_type", "is_active", "created_at")
    list_filter = ("room_type", "is_active", "created_at")
    search_fields = ("code", "title", "creator__username")
    list_select_related = ("creator",)
    autocomplete_fields = ("creator",)
    readonly_fields = ("created_at", "closed_at")
    inlines = (RoomParticipantInline,)


@admin.register(RoomParticipant)
class RoomParticipantAdmin(BaseAdmin):
    list_display = ("id", "room", "user", "role", "joined_at")
    list_filter = ("role", "joined_at")
    search_fields = ("room__code", "room__title", "user__username")
    list_select_related = ("room", "user")
    autocomplete_fields = ("room", "user")
    readonly_fields = ("joined_at",)


@admin.register(RoomMessage)
class RoomMessageAdmin(BaseAdmin):
    list_display = ("id", "room", "sender", "created_at")
    list_filter = ("created_at",)
    search_fields = ("room__code", "sender__username", "text")
    list_select_related = ("room", "sender")
    autocomplete_fields = ("room", "sender")
    readonly_fields = ("created_at",)


@admin.register(TradeExchange)
class TradeExchangeAdmin(BaseAdmin):
    list_display = ("id", "room", "status", "disputed_by", "completed_at", "updated_at")
    list_filter = ("status", "created_at", "updated_at")
    search_fields = ("room__code", "room__title", "room__creator__username", "disputed_by__username")
    list_select_related = ("room", "room__creator", "disputed_by")
    autocomplete_fields = ("room", "disputed_by")
    readonly_fields = ("created_at", "updated_at", "completed_at", "disputed_at")


@admin.register(EscrowRoom)
class EscrowRoomAdmin(BaseAdmin):
    list_display = ("id", "deal", "created_at")
    list_filter = ("created_at",)
    search_fields = ("deal__product_title", "deal__seller__username", "deal__buyer__username")
    list_select_related = ("deal",)
    autocomplete_fields = ("deal",)
    readonly_fields = ("created_at",)
    inlines = (EscrowMessageInline,)


@admin.register(EscrowMessage)
class EscrowMessageAdmin(BaseAdmin):
    list_display = ("id", "room", "sender", "is_admin", "created_at")
    list_filter = ("is_admin", "created_at")
    search_fields = ("room__deal__product_title", "sender__username", "text")
    list_select_related = ("room__deal", "sender")
    autocomplete_fields = ("room", "sender")
    readonly_fields = ("created_at",)


@admin.register(Notification)
class NotificationAdmin(BaseAdmin):
    list_display = ("id", "recipient", "notif_type", "title", "is_read", "created_at")
    list_filter = ("notif_type", "is_read", "created_at")
    search_fields = ("recipient__username", "title", "body", "url")
    list_select_related = ("recipient",)
    autocomplete_fields = ("recipient",)
    readonly_fields = ("created_at",)


@admin.register(SupportTicket)
class SupportTicketAdmin(BaseAdmin):
    list_display = (
        "ticket_number",
        "user",
        "assigned_to",
        "subject",
        "category",
        "priority",
        "status",
        "created_at",
    )
    list_filter = ("status", "priority", "category", "created_at")
    search_fields = ("ticket_number", "user__username", "assigned_to__username", "subject")
    list_select_related = ("user", "assigned_to", "deal")
    autocomplete_fields = ("user", "assigned_to", "deal")
    readonly_fields = ("ticket_number", "created_at", "updated_at")
    inlines = (TicketReplyInline,)


@admin.register(TicketReply)
class TicketReplyAdmin(BaseAdmin):
    list_display = ("id", "ticket", "sender", "is_staff_reply", "created_at")
    list_filter = ("is_staff_reply", "created_at")
    search_fields = ("ticket__ticket_number", "sender__username", "message")
    list_select_related = ("ticket", "sender")
    autocomplete_fields = ("ticket", "sender")
    readonly_fields = ("created_at",)


@admin.register(Payment)
class PaymentAdmin(BaseAdmin):
    list_display = (
        "id",
        "deal",
        "payer",
        "amount",
        "fee_amount",
        "net_amount",
        "status",
        "created_at",
    )
    list_filter = ("status", "payment_method", "created_at", "held_at", "released_at")
    search_fields = ("deal__product_title", "payer__username", "transaction_id", "reference_number", "transfer_code")
    list_select_related = ("deal", "payer")
    autocomplete_fields = ("deal", "payer")
    readonly_fields = (
        "transaction_id",
        "created_at",
        "updated_at",
        "held_at",
        "released_at",
    )


@admin.register(PaymentAuditLog)
class PaymentAuditLogAdmin(BaseAdmin):
    list_display = ("id", "payment", "admin", "action", "created_at")
    list_filter = ("action", "created_at")
    search_fields = ("payment__deal__product_title", "admin__username", "reason")
    list_select_related = ("payment", "admin")
    readonly_fields = ("created_at",)


@admin.register(TransactionInvoice)
class TransactionInvoiceAdmin(BaseAdmin):
    list_display = (
        "invoice_number",
        "deal",
        "buyer",
        "seller",
        "subtotal",
        "platform_fee",
        "seller_net",
        "status",
        "issued_at",
    )
    list_filter = ("status", "issued_at", "updated_at")
    search_fields = ("invoice_number", "deal__product_title", "buyer__username", "seller__username")
    list_select_related = ("deal", "buyer", "seller", "payment")
    autocomplete_fields = ("deal", "buyer", "seller", "payment")
    readonly_fields = ("invoice_number", "issued_at", "updated_at")


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    list_display = ("ccp_name", "ccp_account", "ccp_rip", "baridimob_number")
    fieldsets = (
        ("معلومات حساب CCP", {
            "fields": ("ccp_name", "ccp_account", "ccp_rip", "baridimob_number"),
        }),
    )

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
