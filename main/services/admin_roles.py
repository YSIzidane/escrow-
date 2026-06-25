from django.contrib.auth.models import Group, Permission


ADMIN_ROLE_SPECS = {
    "support_admin": {
        "name": "Support Admin",
        "description": "Tickets, support replies, and user communication.",
        "permissions": [
            ("main", "view_supportticket"),
            ("main", "change_supportticket"),
            ("main", "view_ticketreply"),
            ("main", "add_ticketreply"),
            ("main", "view_notification"),
            ("main", "view_room"),
            ("main", "change_room"),
            ("main", "view_roomparticipant"),
            ("main", "view_roommessage"),
        ],
    },
    "finance_admin": {
        "name": "Finance Admin",
        "description": "Payments, withdrawals, and invoices.",
        "permissions": [
            ("main", "view_payment"),
            ("main", "change_payment"),
            ("main", "view_paymentauditlog"),
            ("main", "add_paymentauditlog"),
            ("main", "view_withdrawalrequest"),
            ("main", "change_withdrawalrequest"),
            ("main", "view_transactioninvoice"),
        ],
    },
    "operations_admin": {
        "name": "Operations Admin",
        "description": "Deals, KYC, escrow flow, and platform operations.",
        "permissions": [
            ("main", "view_deal"),
            ("main", "change_deal"),
            ("main", "view_profile"),
            ("main", "change_profile"),
            ("main", "view_escrowroom"),
            ("main", "view_notification"),
        ],
    },
    "security_admin": {
        "name": "Security Admin",
        "description": "Reports, disputes, suspicious activity, and moderation review.",
        "permissions": [
            ("main", "view_supportticket"),
            ("main", "change_supportticket"),
            ("main", "view_ticketreply"),
            ("main", "add_ticketreply"),
            ("main", "view_deal"),
            ("main", "change_deal"),
            ("main", "view_room"),
            ("main", "change_room"),
            ("main", "view_roomparticipant"),
            ("main", "view_roommessage"),
            ("main", "view_tradeexchange"),
            ("main", "change_tradeexchange"),
            ("main", "view_notification"),
        ],
    },
}


def get_admin_group_names():
    return [spec["name"] for spec in ADMIN_ROLE_SPECS.values()]


def ensure_admin_role_groups():
    for spec in ADMIN_ROLE_SPECS.values():
        group, _ = Group.objects.get_or_create(name=spec["name"])
        permissions = []
        for app_label, codename in spec["permissions"]:
            permission = Permission.objects.filter(
                content_type__app_label=app_label,
                codename=codename,
            ).first()
            if permission:
                permissions.append(permission)
        if permissions:
            group.permissions.set(permissions)


def get_user_role_keys(user):
    if not getattr(user, "is_authenticated", False):
        return []
    user_group_names = set(user.groups.values_list("name", flat=True))
    return [
        role_key
        for role_key, spec in ADMIN_ROLE_SPECS.items()
        if spec["name"] in user_group_names
    ]


def has_any_admin_role(user, role_keys=None):
    if not getattr(user, "is_authenticated", False) or not user.is_staff:
        return False
    if user.is_superuser:
        return True

    assigned_role_keys = set(get_user_role_keys(user))
    if role_keys is None:
        return bool(assigned_role_keys)
    return bool(assigned_role_keys & set(role_keys))


def has_role_or_legacy_staff(user, role_key):
    if role_key not in ADMIN_ROLE_SPECS:
        return False
    return has_any_admin_role(user, {role_key})
