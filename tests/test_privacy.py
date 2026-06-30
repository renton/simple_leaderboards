"""Tests for the public per-game privacy policy pages."""

from __future__ import annotations

import pytest


@pytest.fixture
def signed_in_client(client, app):
    from app.extensions import db
    from app.models.user import AdminUser

    with app.app_context():
        user = AdminUser(username="root")
        user.set_password("hunter2-hunter2-hunter2")
        db.session.add(user)
        db.session.commit()
    client.post(
        "/admin/login",
        data={"username": "root", "password": "hunter2-hunter2-hunter2"},
    )
    return client


class TestPublicPrivacyPages:
    def test_index_is_public_no_login(self, client, make_game):
        make_game(slug="tetris-classic", name="Tetris Classic")
        resp = client.get("/privacy")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "Tetris Classic" in body
        assert "/privacy/tetris-classic" in body

    def test_policy_page_public_and_names_the_game(self, client, make_game):
        make_game(slug="tetris-classic", name="Tetris Classic")
        resp = client.get("/privacy/tetris-classic")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "Privacy Policy" in body
        assert "Tetris Classic" in body
        # Core disclosures Google Play expects: collection, use, sharing.
        assert "Information we collect" in body
        assert "How we use information" in body
        assert "How we share information" in body
        # Specific data categories this software actually collects.
        assert "Player name" in body
        assert "IP address" in body
        assert "Device and technical information" in body

    def test_policy_shows_operator_and_contact_when_set(self, client, make_game):
        make_game(
            slug="tetris-classic",
            name="Tetris Classic",
            operator_name="Ren Games Ltd",
            contact_email="privacy@rengames.example",
        )
        body = client.get("/privacy/tetris-classic").get_data(as_text=True)
        assert "Ren Games Ltd" in body
        assert "privacy@rengames.example" in body
        assert "mailto:privacy@rengames.example" in body

    def test_policy_falls_back_when_operator_unset(self, client, make_game):
        make_game(slug="tetris-classic", name="Tetris Classic")
        body = client.get("/privacy/tetris-classic").get_data(as_text=True)
        assert "the operator of this game" in body
        assert "contact the operator who provided you" in body

    def test_extra_clauses_rendered_and_escaped(self, client, make_game):
        make_game(
            slug="tetris-classic",
            name="Tetris Classic",
            privacy_policy_extra="Custom clause. <script>alert(1)</script>",
        )
        body = client.get("/privacy/tetris-classic").get_data(as_text=True)
        assert "Custom clause." in body
        # Must be HTML-escaped, never rendered as a live tag.
        assert "<script>alert(1)</script>" not in body
        assert "&lt;script&gt;" in body

    def test_unknown_game_404(self, client):
        assert client.get("/privacy/no-such-game").status_code == 404

    def test_archived_game_hidden(self, client, make_game):
        make_game(slug="archived-game", name="Archived", archived=True)
        assert client.get("/privacy/archived-game").status_code == 404
        index = client.get("/privacy").get_data(as_text=True)
        assert "archived-game" not in index


class TestAdminPrivacyEditing:
    def test_create_game_with_privacy_fields(self, signed_in_client):
        resp = signed_in_client.post(
            "/admin/games/new",
            data={
                "name": "Tetris",
                "slug": "tetris-classic",
                "timezone": "UTC",
                "score_direction": "desc",
                "metadata_json": "{}",
                "operator_name": "Ren Games Ltd",
                "contact_email": "privacy@rengames.example",
                "privacy_policy_extra": "We also do X.",
            },
        )
        assert resp.status_code == 302
        from app.extensions import db
        from app.models.game import Game

        with signed_in_client.application.app_context():
            g = db.session.execute(
                db.select(Game).where(Game.slug == "tetris-classic")
            ).scalar_one()
            assert g.operator_name == "Ren Games Ltd"
            assert g.contact_email == "privacy@rengames.example"
            assert g.privacy_policy_extra == "We also do X."

    def test_invalid_contact_email_rejected(self, signed_in_client):
        resp = signed_in_client.post(
            "/admin/games/new",
            data={
                "name": "Tetris",
                "slug": "tetris-classic",
                "timezone": "UTC",
                "score_direction": "desc",
                "metadata_json": "{}",
                "contact_email": "not-an-email",
            },
        )
        assert resp.status_code == 400

    def test_edit_sets_privacy_updated_at(self, signed_in_client):
        signed_in_client.post(
            "/admin/games/new",
            data={
                "name": "Tetris",
                "slug": "tetris-classic",
                "timezone": "UTC",
                "score_direction": "desc",
                "metadata_json": "{}",
            },
        )
        from app.extensions import db
        from app.models.game import Game

        with signed_in_client.application.app_context():
            gid = db.session.execute(
                db.select(Game.id).where(Game.slug == "tetris-classic")
            ).scalar_one()

        signed_in_client.post(
            f"/admin/games/{gid}/edit",
            data={
                "name": "Tetris",
                "slug": "tetris-classic",
                "timezone": "UTC",
                "score_direction": "desc",
                "metadata_json": "{}",
                "operator_name": "Ren Games Ltd",
            },
        )
        with signed_in_client.application.app_context():
            g = db.session.get(Game, gid)
            assert g.privacy_updated_at is not None
            assert g.operator_name == "Ren Games Ltd"


def test_privacy_nav_link_present_on_admin_pages(signed_in_client, make_game):
    make_game()
    body = signed_in_client.get("/admin/").get_data(as_text=True)
    assert "/privacy" in body
