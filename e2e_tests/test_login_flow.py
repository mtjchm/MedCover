"""E2E tests: login → dashboard → logout flow."""


def test_login_shows_dashboard(logged_in_page, base_url):
    """After login, the dashboard should be visible."""
    page = logged_in_page
    assert "/dashboard" in page.url
    # Dashboard heading is "Přehled"
    assert page.locator("h2").filter(has_text="Přehled").count() > 0


def test_logout_redirects_to_login(logged_in_page, base_url):
    """Clicking logout should redirect back to the login page."""
    page = logged_in_page
    # Find and click the logout link/button
    logout_link = page.locator('a[href*="logout"]')
    if logout_link.count() > 0:
        logout_link.first.click()
    else:
        # Try nav dropdown or other patterns
        page.click("text=Odhlásit")
    page.wait_for_url("**/auth/login**")
    assert "/auth/login" in page.url


def test_invalid_login_shows_error(page, base_url):
    """Invalid credentials should show an error, not crash."""
    page.goto(f"{base_url}/auth/login")
    page.fill("#email", "nonexistent@example.com")
    page.fill("#password", "wrongpassword")
    page.click('button[type="submit"]')
    # Should stay on login page with an error message
    assert "/auth/login" in page.url
    # Flash message or form error should be visible
    assert page.locator(".alert-danger, .alert-warning, .invalid-feedback").count() > 0
