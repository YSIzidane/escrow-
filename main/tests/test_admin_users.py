from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse
from unittest.mock import patch

from main.models import AdminActionLog, Deal, EscrowRoom, Payment, Room, RoomParticipant, SupportTicket, TradeExchange
from main.services.admin_roles import ADMIN_ROLE_SPECS, ensure_admin_role_groups
from decimal import Decimal


class AdminUserManagementTests(TestCase):
    def setUp(self):
        ensure_admin_role_groups()
        self.owner = User.objects.create_superuser(
            username="owner",
            email="owner@example.com",
            password="ownerpass",
        )
        self.target = User.objects.create_user(
            username="target",
            email="target@example.com",
            password="targetpass",
        )

    def test_superuser_can_grant_admin_rank(self):
        self.client.login(username="owner", password="ownerpass")
        response = self.client.post(
            reverse("admin_users_list"),
            {"user_id": self.target.id, "action": "grant_staff"},
        )

        self.assertRedirects(response, reverse("admin_users_list"))
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_staff)
        self.assertTrue(AdminActionLog.objects.filter(action="grant_staff", target_user=self.target).exists())

    def test_superuser_can_assign_role_bundle(self):
        self.client.login(username="owner", password="ownerpass")
        response = self.client.post(
            reverse("admin_users_list"),
            {
                "user_id": self.target.id,
                "action": "assign_role",
                "role_key": "finance_admin",
            },
        )

        self.assertRedirects(response, reverse("admin_users_list"))
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_staff)
        self.assertTrue(
            self.target.groups.filter(name=ADMIN_ROLE_SPECS["finance_admin"]["name"]).exists()
        )
        self.assertTrue(
            AdminActionLog.objects.filter(
                action="assign_role",
                target_user=self.target,
                role_key="finance_admin",
            ).exists()
        )

    def test_revoke_staff_clears_admin_groups(self):
        finance_group = Group.objects.get(name=ADMIN_ROLE_SPECS["finance_admin"]["name"])
        self.target.is_staff = True
        self.target.save(update_fields=["is_staff"])
        self.target.groups.add(finance_group)

        self.client.login(username="owner", password="ownerpass")
        response = self.client.post(
            reverse("admin_users_list"),
            {"user_id": self.target.id, "action": "revoke_staff"},
        )

        self.assertRedirects(response, reverse("admin_users_list"))
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_staff)
        self.assertFalse(self.target.groups.filter(name=finance_group.name).exists())
        self.assertTrue(AdminActionLog.objects.filter(action="revoke_staff", target_user=self.target).exists())

    def test_remove_last_role_downgrades_staff_flag(self):
        finance_group = Group.objects.get(name=ADMIN_ROLE_SPECS["finance_admin"]["name"])
        self.target.is_staff = True
        self.target.save(update_fields=["is_staff"])
        self.target.groups.add(finance_group)

        self.client.login(username="owner", password="ownerpass")
        response = self.client.post(
            reverse("admin_users_list"),
            {"user_id": self.target.id, "action": "remove_role", "role_key": "finance_admin"},
        )

        self.assertRedirects(response, reverse("admin_users_list"))
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_staff)
        self.assertFalse(self.target.groups.filter(name=finance_group.name).exists())
        self.assertTrue(
            AdminActionLog.objects.filter(
                action="remove_role",
                target_user=self.target,
                role_key="finance_admin",
            ).exists()
        )

    @patch("main.views.staff.model_table_exists", return_value=False)
    def test_admin_users_page_still_loads_without_invoice_table(self, mocked_exists):
        self.client.login(username="owner", password="ownerpass")
        response = self.client.get(reverse("admin_users_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "0")

    @patch("main.views.staff.model_table_exists", return_value=False)
    def test_admin_users_page_uses_english_translations(self, mocked_exists):
        self.client.login(username="owner", password="ownerpass")
        self.client.cookies["site_language"] = "en"

        response = self.client.get(reverse("admin_users_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Admin control")
        self.assertContains(response, "Users and admin roles")
        self.assertContains(response, "Permission bundles")
        self.assertNotContains(response, "إدارة الصلاحيات")


class AdminRoleAccessTests(TestCase):
    def setUp(self):
        ensure_admin_role_groups()
        self.roleless_staff = User.objects.create_user(
            username="roleless_staff",
            password="staffpass",
            is_staff=True,
        )
        self.support_staff = User.objects.create_user(
            username="support_staff",
            password="supportpass",
            is_staff=True,
        )
        self.finance_staff = User.objects.create_user(
            username="finance_staff",
            password="financepass",
            is_staff=True,
        )
        self.operations_staff = User.objects.create_user(
            username="operations_staff",
            password="opspass",
            is_staff=True,
        )
        self.security_staff = User.objects.create_user(
            username="security_staff",
            password="securitypass",
            is_staff=True,
        )
        self.superuser = User.objects.create_superuser(
            username="platform_owner",
            email="owner2@example.com",
            password="ownerpass",
        )

        self.support_staff.groups.add(Group.objects.get(name=ADMIN_ROLE_SPECS["support_admin"]["name"]))
        self.finance_staff.groups.add(Group.objects.get(name=ADMIN_ROLE_SPECS["finance_admin"]["name"]))
        self.operations_staff.groups.add(Group.objects.get(name=ADMIN_ROLE_SPECS["operations_admin"]["name"]))
        self.security_staff.groups.add(Group.objects.get(name=ADMIN_ROLE_SPECS["security_admin"]["name"]))

    def test_staff_without_group_cannot_access_finance_pages(self):
        self.client.login(username="roleless_staff", password="staffpass")

        dashboard_response = self.client.get(reverse("admin_dashboard"))
        withdrawals_response = self.client.get(reverse("admin_withdrawals_list"))
        pending_response = self.client.get(reverse("staff_pending_payments"))

        self.assertRedirects(dashboard_response, reverse("home"))
        self.assertEqual(withdrawals_response.status_code, 302)
        self.assertEqual(withdrawals_response.url, reverse("admin_dashboard"))
        self.assertEqual(pending_response.status_code, 302)
        self.assertEqual(pending_response.url, reverse("admin_dashboard"))

    def test_staff_without_group_cannot_access_operations_pages(self):
        self.client.login(username="roleless_staff", password="staffpass")

        kyc_response = self.client.get(reverse("admin_kyc_list"))
        escrow_response = self.client.get(reverse("escrow_dashboard"))

        self.assertEqual(kyc_response.status_code, 302)
        self.assertEqual(kyc_response.url, reverse("admin_dashboard"))
        self.assertEqual(escrow_response.status_code, 302)
        self.assertEqual(escrow_response.url, reverse("admin_dashboard"))

    def test_staff_without_group_cannot_access_support_pages(self):
        self.client.login(username="roleless_staff", password="staffpass")

        dashboard_response = self.client.get(reverse("staff_dashboard"))
        rooms_response = self.client.get(reverse("admin_rooms_list"))
        security_response = self.client.get(reverse("admin_security_reports"))

        self.assertEqual(dashboard_response.status_code, 302)
        self.assertEqual(dashboard_response.url, reverse("admin_dashboard"))
        self.assertEqual(rooms_response.status_code, 302)
        self.assertEqual(rooms_response.url, reverse("admin_dashboard"))
        self.assertEqual(security_response.status_code, 302)
        self.assertEqual(security_response.url, reverse("admin_dashboard"))

    def test_superuser_still_has_access(self):
        self.client.login(username="platform_owner", password="ownerpass")
        self.assertEqual(self.client.get(reverse("admin_dashboard")).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin_withdrawals_list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin_kyc_list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("staff_dashboard")).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin_security_reports")).status_code, 200)

    def test_admin_dashboard_uses_private_headers_and_english_shell(self):
        self.client.login(username="platform_owner", password="ownerpass")
        self.client.cookies["site_language"] = "en"

        response = self.client.get(reverse("admin_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Platform operations center")
        self.assertContains(response, "Security posture")
        self.assertIn("no-cache", response["Cache-Control"])
        self.assertEqual(response["X-Robots-Tag"], "noindex, nofollow, noarchive")
        self.assertEqual(response["X-Frame-Options"], "DENY")
        self.assertIn(
            response["Referrer-Policy"],
            {"same-origin", "strict-origin-when-cross-origin"},
        )

    def test_role_group_access_still_works(self):
        self.client.login(username="finance_staff", password="financepass")
        self.assertEqual(self.client.get(reverse("admin_withdrawals_list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("staff_pending_payments")).status_code, 200)

        self.client.logout()
        self.client.login(username="operations_staff", password="opspass")
        self.assertEqual(self.client.get(reverse("admin_kyc_list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("escrow_dashboard")).status_code, 200)

        self.client.logout()
        self.client.login(username="support_staff", password="supportpass")
        self.assertEqual(self.client.get(reverse("staff_dashboard")).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin_rooms_list")).status_code, 200)

        self.client.logout()
        self.client.login(username="security_staff", password="securitypass")
        self.assertEqual(self.client.get(reverse("admin_security_reports")).status_code, 200)

    def test_security_reports_center_collects_reports_and_disputes(self):
        report_ticket = SupportTicket.objects.create(
            user=self.superuser,
            subject="[REPORT] Suspicious seller",
            description="The seller asked to move payment off platform.",
            category="account",
            priority="high",
            status="open",
        )
        deal = Deal.objects.create(
            seller=self.superuser,
            buyer=self.support_staff,
            product_title="Disputed Escrow Item",
            product_description="Needs moderation",
            price=Decimal("55.00"),
            status="disputed",
            dispute_reason="The item does not match.",
        )
        room = Room.objects.create(
            creator=self.superuser,
            room_type="trade",
            title="Disputed Trade Room",
            description="Trade needs review",
        )
        RoomParticipant.objects.create(room=room, user=self.superuser, role="owner")
        exchange = TradeExchange.objects.create(
            room=room,
            status=TradeExchange.STATUS_DISPUTED,
            disputed_by=self.support_staff,
            dispute_reason="Trade details changed.",
        )

        self.client.login(username="platform_owner", password="ownerpass")
        self.client.cookies["site_language"] = "en"
        response = self.client.get(reverse("admin_security_reports"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Security Reports Center")
        self.assertContains(response, report_ticket.ticket_number)
        self.assertContains(response, deal.product_title)
        self.assertContains(response, exchange.room.code)

    def test_security_admin_can_review_report_ticket_only(self):
        report_ticket = SupportTicket.objects.create(
            user=self.superuser,
            subject="[REPORT] Suspicious buyer",
            description="The buyer is asking for credentials outside the platform.",
            category="account",
            priority="high",
            status="open",
        )
        normal_ticket = SupportTicket.objects.create(
            user=self.superuser,
            subject="Normal support request",
            description="Regular help request.",
            category="technical",
            priority="medium",
            status="open",
        )

        self.client.login(username="security_staff", password="securitypass")
        report_response = self.client.get(reverse("staff_ticket_detail", args=[report_ticket.id]))
        normal_response = self.client.get(reverse("staff_ticket_detail", args=[normal_ticket.id]))

        self.assertEqual(report_response.status_code, 200)
        self.assertRedirects(normal_response, reverse("admin_security_reports"))

    def test_internal_admin_pages_use_english_translations(self):
        deal = Deal.objects.create(
            seller=self.superuser,
            buyer=self.support_staff,
            product_title="Escrow Moderation Deal",
            product_description="Internal moderation flow",
            price=Decimal("199.00"),
            status="reserved",
        )
        room = EscrowRoom.objects.create(deal=deal)
        Payment.objects.create(
            deal=deal,
            payer=self.support_staff,
            amount=Decimal("199.00"),
            status="escrow_held",
            transaction_id="pi_internal_translation",
        )
        private_room = Room.objects.create(
            creator=self.superuser,
            room_type="buy",
            title="Support Translation Room",
            description="Internal room for translation coverage",
        )
        RoomParticipant.objects.create(room=private_room, user=self.superuser, role="owner")
        SupportTicket.objects.create(
            user=self.superuser,
            subject="Translation review ticket",
            description="Need to verify staff dashboard labels",
            category="other",
            status="open",
            priority="medium",
        )

        self.client.login(username="platform_owner", password="ownerpass")
        self.client.cookies["site_language"] = "en"

        staff_response = self.client.get(reverse("staff_dashboard"))
        rooms_response = self.client.get(reverse("admin_rooms_list"))
        escrow_dashboard_response = self.client.get(reverse("escrow_dashboard"))
        escrow_room_response = self.client.get(reverse("escrow_room", args=[deal.id]))

        self.assertContains(staff_response, "Search")
        self.assertContains(staff_response, "Ticket number, user, or subject...")
        self.assertContains(rooms_response, "Room Management")
        self.assertContains(rooms_response, "Delete this room permanently?")
        self.assertContains(escrow_dashboard_response, 'title="Messages"', html=False)
        self.assertContains(escrow_room_response, "Current status")
        self.assertContains(escrow_room_response, "Latest messages")
