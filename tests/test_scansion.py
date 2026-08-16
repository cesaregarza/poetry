import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client

from poems.models import PoemPage
from poems.scansion import CmuPronunciationProvider, Pronunciation, normalize_word, provider

pytestmark = pytest.mark.django_db


def add_poem(parent, *, title="Meter Test", slug="meter-test", body="A line waits."):
    poem = PoemPage(title=title, slug=slug, poem_body=body, live=False)
    parent.add_child(instance=poem)
    poem.save_revision()
    return poem


def test_cmudict_provider_returns_binary_stress_and_alternatives():
    compare = provider.pronunciations_for_word("compare")
    record = provider.pronunciations_for_word("record")

    assert compare == (Pronunciation((False, True)),)
    assert Pronunciation((True, False)) in record
    assert Pronunciation((False, True)) in record
    assert all(isinstance(stress, bool) for item in record for stress in item.stresses)


def test_function_words_are_destressed_and_duplicate_patterns_are_removed():
    assert provider.pronunciations_for_word("to") == (Pronunciation((False,)),)
    assert provider.pronunciations_for_word("THE") == (Pronunciation((False,)),)


def test_provider_preserves_lines_and_marks_unknown_unicode_words():
    analysis = provider.analyze("Moonlight waits.\n\nCaf\u00e9 quizzaciously")

    assert [line["text"] for line in analysis["lines"]] == [
        "Moonlight waits.",
        "",
        "Caf\u00e9 quizzaciously",
    ]
    assert analysis["lines"][0]["words"][0]["id"] == "l0:w0:moonlight"
    assert analysis["lines"][2]["words"][0]["source"] == "unknown"
    assert analysis["unknown_words"] == 2
    assert len(analysis["source_hash"]) == 64


def test_word_normalization_handles_curly_apostrophes_and_possessives():
    assert normalize_word("Moon\u2019s") == "moon's"
    assert provider.pronunciations_for_word("moon\u2019s") == provider.pronunciations_for_word(
        "moon"
    )


def test_provider_rejects_invalid_mode_and_oversized_text():
    with pytest.raises(ValueError, match="Unsupported"):
        provider.analyze("line", mode="hexameter")
    with pytest.raises(ValueError, match="100,000"):
        provider.analyze("x" * 100_001)


def test_provider_initializes_once_when_threads_lookup_together(tmp_path, monkeypatch):
    dictionary = tmp_path / "cmudict.dict"
    dictionary.write_text("word W ER1 D\n", encoding="utf-8")
    test_provider = CmuPronunciationProvider(dictionary)
    calls = 0
    original = test_provider._load_index

    def counted_load():
        nonlocal calls
        calls += 1
        return original()

    monkeypatch.setattr(test_provider, "_load_index", counted_load)
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(test_provider.pronunciations_for_word, ["word"] * 24))

    assert calls == 1
    assert results == [(Pronunciation((True,)),)] * 24


def test_scansion_endpoint_requires_login_admin_and_edit_permission(client, site_tree):
    poem = add_poem(site_tree["poem_index"])
    path = "/admin/poems/scansion/analyze/"

    anonymous = client.post(
        path,
        data=json.dumps({"text": "A line"}),
        content_type="application/json",
    )
    assert anonymous.status_code == 302
    assert anonymous["Location"].startswith("/admin/login/")

    stranger = get_user_model().objects.create_user("scansion-stranger", password="password")
    client.force_login(stranger)
    assert client.post(path, data="{}", content_type="application/json").status_code == 403

    stranger.user_permissions.add(Permission.objects.get(codename="access_admin"))
    stranger = get_user_model().objects.get(pk=stranger.pk)
    client.force_login(stranger)
    assert (
        client.post(
            path,
            data=json.dumps({"text": "A line", "page_id": poem.pk}),
            content_type="application/json",
        ).status_code
        == 403
    )


def test_scansion_endpoint_returns_private_provider_neutral_document(client, site_tree):
    poem = add_poem(site_tree["poem_index"], body="Shall I compare thee")
    admin = get_user_model().objects.create_superuser(
        username="scansion-admin",
        email="scansion@example.com",
        password="safe-test-password",
    )
    client.force_login(admin)

    response = client.post(
        "/admin/poems/scansion/analyze/",
        data=json.dumps(
            {
                "text": "Shall I compare thee",
                "mode": "iambic_pentameter",
                "page_id": poem.pk,
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["mode"] == "iambic_pentameter"
    assert response.json()["lines"][0]["words"][2]["stresses"] == [False, True]
    assert "private" in response["Cache-Control"]
    assert "no-store" in response["Cache-Control"]
    assert response["X-Robots-Tag"] == "noindex"


@pytest.mark.parametrize(
    ("payload", "status"),
    [
        ("not json", 400),
        ("[]", 400),
        (json.dumps({"text": 3}), 400),
        (json.dumps({"text": "line", "mode": "hexameter"}), 400),
        (json.dumps({"text": "line", "page_id": "nope"}), 400),
        (json.dumps({"text": "x" * 100_001}), 413),
    ],
)
def test_scansion_endpoint_validates_requests(client, payload, status):
    admin = get_user_model().objects.create_superuser(
        username=f"validation-admin-{status}-{len(payload)}",
        email="validation@example.com",
        password="safe-test-password",
    )
    client.force_login(admin)
    response = client.post(
        "/admin/poems/scansion/analyze/",
        data=payload,
        content_type="application/json",
    )
    assert response.status_code == status


def test_scansion_endpoint_enforces_csrf(site_tree):
    admin = get_user_model().objects.create_superuser(
        username="csrf-scansion-admin",
        email="csrf@example.com",
        password="safe-test-password",
    )
    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(admin)
    response = csrf_client.post(
        "/admin/poems/scansion/analyze/",
        data=json.dumps({"text": "A line"}),
        content_type="application/json",
    )
    assert response.status_code == 403


def test_scansion_fields_are_saved_in_wagtail_revisions(site_tree):
    poem = add_poem(site_tree["poem_index"])
    poem.scansion_enabled = True
    poem.scansion_mode = PoemPage.ScansionMode.IAMBIC_PENTAMETER
    poem.scansion_overrides = {
        "version": 1,
        "source_hash": "example",
        "occurrences": {"l0:w0:a": {"word": "a", "pronunciation": 0, "stresses": [True]}},
    }
    revision = poem.save_revision()
    revised_poem = revision.as_object().specific

    assert revised_poem.scansion_enabled is True
    assert revised_poem.scansion_mode == "iambic_pentameter"
    assert revised_poem.scansion_overrides == poem.scansion_overrides


def test_scansion_panel_is_private_to_wagtail(client, site_tree):
    poem = add_poem(site_tree["poem_index"], title="Private Meter", slug="private-meter")
    poem.save_revision().publish()
    admin = get_user_model().objects.create_superuser(
        username="panel-scansion-admin",
        email="panel@example.com",
        password="safe-test-password",
    )
    client.force_login(admin)
    edit_html = client.get(f"/admin/pages/{poem.pk}/edit/").content.decode()

    assert "Scansion assistant" in edit_html
    assert "/admin/poems/scansion/analyze/" in edit_html
    assert "scansion-admin.js" in edit_html
    assert "id_scansion_overrides" in edit_html

    client.logout()
    public_response = client.get("/poems/private-meter/")
    assert public_response.status_code == 200
    assert "Scansion assistant" not in public_response.content.decode()
