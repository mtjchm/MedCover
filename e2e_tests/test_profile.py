"""E2E tests: profile page sections and iCal feed.

Regression coverage for:
- PR #190: iCal calendar feed per user
- PR #220: dark mode toggle CSS
"""


def test_profile_renders_all_sections(logged_in_page, base_url):
    """Profile page should show all expected sections."""
    page = logged_in_page
    page.goto(f"{base_url}/users/profile")

    body = page.locator("body").inner_text()
    assert "Profil" in body or "Osobní" in body
    assert page.locator("#dark_mode").count() > 0, "Dark mode toggle missing"


def test_ical_section_present(logged_in_page, base_url):
    """Profile should have the iCal subscription section."""
    page = logged_in_page
    page.goto(f"{base_url}/users/profile")

    ical = page.locator("#ical")
    assert ical.count() > 0, "iCal section (#ical) not found"

    # Should have the URL input and copy button
    assert page.locator("#ical-url-input").count() > 0
    assert page.locator("#ical-copy-btn").count() > 0


def test_ical_url_is_populated(logged_in_page, base_url):
    """The iCal URL field should contain a .ics link."""
    page = logged_in_page
    page.goto(f"{base_url}/users/profile")

    url_input = page.locator("#ical-url-input")
    if url_input.count() == 0:
        return

    value = url_input.input_value()
    assert ".ics" in value, f"iCal URL should contain .ics, got: {value}"


def test_profile_password_form_has_all_fields(logged_in_page, base_url):
    """Password change form should have current, new, and confirm fields."""
    page = logged_in_page
    page.goto(f"{base_url}/users/profile")

    assert page.locator("#current_password").count() > 0
    assert page.locator("#new_password").count() > 0
    assert page.locator("#confirm_password").count() > 0
