from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from main.models import Notification, Room, RoomParticipant, TradeExchange
from main.services.admin_roles import ADMIN_ROLE_SPECS, ensure_admin_role_groups


class RoomManagementTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner", password="pass12345")
        self.guest = User.objects.create_user(username="guest", password="pass12345")
        self.outsider = User.objects.create_user(username="outsider", password="pass12345")

    def _create_room(self, **kwargs):
        room = Room.objects.create(
            creator=self.owner,
            room_type=kwargs.get("room_type", "sell"),
            title=kwargs.get("title", "Private sale"),
            description=kwargs.get("description", "Invite-only room"),
            is_active=kwargs.get("is_active", True),
        )
        RoomParticipant.objects.get_or_create(room=room, user=self.owner, defaults={"role": "owner"})
        return room

    def test_create_room_creates_owner_membership(self):
        self.client.login(username="owner", password="pass12345")

        response = self.client.post(
            reverse("create_room"),
            {
                "type": "trade",
                "title": "Swap two phones",
                "description": "Private room for a direct exchange",
            },
        )

        room = Room.objects.get(title="Swap two phones")
        self.assertRedirects(response, reverse("room_detail", args=[room.code]))
        self.assertTrue(room.code.isupper())
        self.assertTrue(
            RoomParticipant.objects.filter(room=room, user=self.owner, role="owner").exists()
        )

    def test_join_room_adds_member_and_blocks_third_user(self):
        room = self._create_room()

        self.client.login(username="guest", password="pass12345")
        response = self.client.post(reverse("join_room"), {"code": room.code.lower()})
        self.assertRedirects(response, reverse("room_detail", args=[room.code]))
        self.assertTrue(
            RoomParticipant.objects.filter(room=room, user=self.guest, role="member").exists()
        )

        self.client.logout()
        self.client.login(username="outsider", password="pass12345")
        response = self.client.post(reverse("join_room"), {"code": room.code})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(RoomParticipant.objects.filter(room=room, user=self.outsider).exists())

    def test_non_participant_cannot_open_room_or_poll(self):
        room = self._create_room()

        self.client.login(username="outsider", password="pass12345")
        detail_response = self.client.get(reverse("room_detail", args=[room.code]))
        poll_response = self.client.get(reverse("poll_room_chat", args=[room.code]))

        self.assertRedirects(detail_response, reverse("join_room"))
        self.assertEqual(poll_response.status_code, 403)

    def test_owner_can_close_reopen_and_delete_room(self):
        room = self._create_room()
        self.client.login(username="owner", password="pass12345")

        close_response = self.client.post(reverse("close_room", args=[room.code]))
        room.refresh_from_db()
        self.assertRedirects(close_response, reverse("room_detail", args=[room.code]))
        self.assertFalse(room.is_active)
        self.assertIsNotNone(room.closed_at)

        reopen_response = self.client.post(reverse("reopen_room", args=[room.code]))
        room.refresh_from_db()
        self.assertRedirects(reopen_response, reverse("room_detail", args=[room.code]))
        self.assertTrue(room.is_active)
        self.assertIsNone(room.closed_at)

        delete_response = self.client.post(reverse("delete_room", args=[room.code]))
        self.assertRedirects(delete_response, reverse("chat_hub"))
        self.assertFalse(Room.objects.filter(id=room.id).exists())

    def test_closed_room_stays_visible_but_blocks_new_messages(self):
        room = self._create_room(is_active=False)
        self.client.login(username="owner", password="pass12345")

        page_response = self.client.get(reverse("room_detail", args=[room.code]))
        send_response = self.client.post(
            reverse("room_detail", args=[room.code]),
            {"message": "hello"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(page_response.status_code, 200)
        self.assertContains(page_response, room.title)
        self.assertEqual(send_response.status_code, 400)

    def test_trade_room_completes_after_both_parties_confirm_receipt(self):
        room = self._create_room(room_type="trade", title="Phone swap")
        RoomParticipant.objects.create(room=room, user=self.guest, role="member")

        self.client.login(username="owner", password="pass12345")
        self.client.post(
            reverse("trade_room_action", args=[room.code]),
            {"action": "update_item", "item_description": "iPhone 13, clean IMEI"},
        )
        self.client.post(reverse("trade_room_action", args=[room.code]), {"action": "mark_ready"})

        self.client.logout()
        self.client.login(username="guest", password="pass12345")
        self.client.post(
            reverse("trade_room_action", args=[room.code]),
            {"action": "update_item", "item_description": "Samsung S23 with charger"},
        )
        self.client.post(reverse("trade_room_action", args=[room.code]), {"action": "mark_ready"})

        exchange = TradeExchange.objects.get(room=room)
        self.assertEqual(exchange.status, TradeExchange.STATUS_READY)

        self.client.post(reverse("trade_room_action", args=[room.code]), {"action": "confirm_received"})
        self.client.logout()
        self.client.login(username="owner", password="pass12345")
        self.client.post(reverse("trade_room_action", args=[room.code]), {"action": "confirm_received"})

        exchange.refresh_from_db()
        room.refresh_from_db()
        self.assertEqual(exchange.status, TradeExchange.STATUS_COMPLETED)
        self.assertIsNotNone(exchange.completed_at)
        self.assertFalse(room.is_active)

        reopen_response = self.client.post(reverse("reopen_room", args=[room.code]))
        room.refresh_from_db()
        self.assertRedirects(reopen_response, reverse("room_detail", args=[room.code]))
        self.assertFalse(room.is_active)

    def test_trade_ready_notifies_partner_and_cannot_repeat_ready(self):
        room = self._create_room(room_type="trade", title="Console swap")
        RoomParticipant.objects.create(room=room, user=self.guest, role="member")

        self.client.login(username="owner", password="pass12345")
        self.client.post(
            reverse("trade_room_action", args=[room.code]),
            {"action": "update_item", "item_description": "PS5 digital edition"},
        )
        self.client.post(reverse("trade_room_action", args=[room.code]), {"action": "mark_ready"})
        first_ready_count = Notification.objects.filter(recipient=self.guest, notif_type="message").count()
        self.client.post(reverse("trade_room_action", args=[room.code]), {"action": "mark_ready"})

        exchange = TradeExchange.objects.get(room=room)
        self.assertEqual(exchange.status, TradeExchange.STATUS_WAITING)
        self.assertEqual(
            Notification.objects.filter(recipient=self.guest, notif_type="message").count(),
            first_ready_count,
        )

    def test_trade_dispute_notifies_staff(self):
        room = self._create_room(room_type="trade", title="Account swap")
        RoomParticipant.objects.create(room=room, user=self.guest, role="member")
        staff = User.objects.create_user(
            username="moderator",
            password="pass12345",
            is_staff=True,
        )

        self.client.login(username="guest", password="pass12345")
        response = self.client.post(
            reverse("trade_room_action", args=[room.code]),
            {"action": "report_issue", "reason": "The account details do not match the agreement."},
        )

        self.assertRedirects(response, reverse("room_detail", args=[room.code]))
        exchange = TradeExchange.objects.get(room=room)
        self.assertEqual(exchange.status, TradeExchange.STATUS_DISPUTED)
        self.assertEqual(exchange.disputed_by, self.guest)
        self.assertTrue(Notification.objects.filter(recipient=staff, notif_type="dispute").exists())

    def test_superuser_can_manage_private_room_but_not_reopen_completed_trade(self):
        admin = User.objects.create_superuser(username="root", password="pass12345")
        room = self._create_room(room_type="trade", title="Completed swap", is_active=False)
        exchange = TradeExchange.objects.create(room=room, status=TradeExchange.STATUS_COMPLETED)

        self.client.login(username="root", password="pass12345")
        close_response = self.client.post(reverse("close_room", args=[room.code]))
        reopen_response = self.client.post(reverse("reopen_room", args=[room.code]))

        room.refresh_from_db()
        exchange.refresh_from_db()
        self.assertRedirects(close_response, reverse("room_detail", args=[room.code]))
        self.assertRedirects(reopen_response, reverse("room_detail", args=[room.code]))
        self.assertEqual(exchange.status, TradeExchange.STATUS_COMPLETED)
        self.assertFalse(room.is_active)


class RoomAdminManagementTests(TestCase):
    def setUp(self):
        ensure_admin_role_groups()
        self.owner = User.objects.create_user(username="owner", password="pass12345")
        self.staff_user = User.objects.create_user(username="staffer", password="pass12345", is_staff=True)
        support_group = Group.objects.get(name=ADMIN_ROLE_SPECS["support_admin"]["name"])
        self.staff_user.groups.add(support_group)

        self.room = Room.objects.create(
            creator=self.owner,
            room_type="buy",
            title="Staff moderation room",
            description="Needs admin visibility",
        )
        RoomParticipant.objects.create(room=self.room, user=self.owner, role="owner")

    def test_support_admin_can_close_and_reopen_room(self):
        self.client.login(username="staffer", password="pass12345")

        close_response = self.client.post(
            reverse("admin_rooms_list"),
            {"room_id": self.room.id, "action": "close"},
        )
        self.assertRedirects(close_response, reverse("admin_rooms_list"))
        self.room.refresh_from_db()
        self.assertFalse(self.room.is_active)

        reopen_response = self.client.post(
            reverse("admin_rooms_list"),
            {"room_id": self.room.id, "action": "reopen"},
        )
        self.assertRedirects(reopen_response, reverse("admin_rooms_list"))
        self.room.refresh_from_db()
        self.assertTrue(self.room.is_active)

    def test_support_admin_room_page_loads(self):
        self.client.login(username="staffer", password="pass12345")
        response = self.client.get(reverse("admin_rooms_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.room.title)
