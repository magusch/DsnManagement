def css_color(color):
    """Inline CSS color that follows the admin dark mode.

    Light mode keeps `color` as is (it is the var() fallback and the light value);
    dark mode swaps it for --dsn-c-<color> defined in templates/admin/base_site.html.
    """
    return f"var(--dsn-c-{color.lstrip('#').lower()}, {color})"
