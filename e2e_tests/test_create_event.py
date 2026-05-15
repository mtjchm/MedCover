"""E2E tests: create an event and verify it appears in the event list."""


def test_create_event(logged_in_page, base_url):
    """Create a new event via the form and verify it shows up."""
    page = logged_in_page
    event_name = "E2E Test Event"

    page.goto(f"{base_url}/events/create")
    assert page.url.endswith("/events/create") or "/events/create" in page.url

    # Fill mandatory fields
    page.fill("#name", event_name)

    # Event type — select first non-empty option (should default to MEDICAL_COVER)
    page.select_option("#event_type", index=1)

    # Master event — select "Obecné (Výchozí)" (the general/default one)
    me_option = page.locator('#master_event_id option:has-text("Obecné")')
    me_value = me_option.get_attribute("value")
    page.select_option("#master_event_id", value=me_value)

    # Flatpickr datetime fields: altInput=true hides the original <input>.
    # Set the hidden input value directly via JS, then notify flatpickr.
    page.evaluate("""() => {
        const start = document.querySelector('#start_datetime');
        const end = document.querySelector('#end_datetime');
        if (start._flatpickr) start._flatpickr.setDate('2026-12-01 09:00', true);
        if (end._flatpickr) end._flatpickr.setDate('2026-12-01 17:00', true);
    }""")

    # Submit the form (the "Vytvořit akci" button)
    page.click('button[type="submit"][value="create"]')

    # Should redirect to event detail page
    page.wait_for_url("**/events/*")
    assert "/events/" in page.url
    assert page.locator("h2, h3, h1").filter(has_text=event_name).count() > 0

    # The event is created as DRAFT, which is hidden from the default list view.
    # Verify it appears when filtering by all statuses.
    page.goto(f"{base_url}/events/?statuses=DRAFT")
    assert page.locator(f"text={event_name}").count() > 0
