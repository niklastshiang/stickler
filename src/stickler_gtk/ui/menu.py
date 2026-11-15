"""The main menu (design screen 9) with the appearance switch, the shortcuts dialog and the
about dialog. The appearance is a setting (`stickler_gtk.logic.settings`) applied through
Adw.StyleManager."""

from __future__ import annotations

from gi.repository import Adw, Gio, GLib, Gtk

import stickler
from stickler_gtk import APP_ID, APP_NAME
from stickler_gtk.i18n import N_, _
from stickler_gtk.logic import settings

COLOR_SCHEMES = {
    "system": Adw.ColorScheme.DEFAULT,
    "light": Adw.ColorScheme.FORCE_LIGHT,
    "dark": Adw.ColorScheme.FORCE_DARK,
}
WEBSITE = "https://github.com/niklastshiang/stickler"

# The three circles, as GNOME's own apps draw them
STYLE = """
.style-switcher { margin: 6px 12px 12px; }
.style-switcher checkbutton { padding: 0; min-height: 40px; min-width: 40px;
  border-radius: 9999px; box-shadow: inset 0 0 0 1px alpha(black, 0.2); }
/* grouped check buttons draw a radio indicator: the ring shows the choice instead */
.style-switcher checkbutton radio { opacity: 0; min-width: 0; min-height: 0; margin: 0;
  padding: 0; border: none; -gtk-icon-source: none; }
.style-switcher checkbutton:checked { box-shadow: inset 0 0 0 3px var(--accent-bg-color); }
.style-switcher .system {
  background: linear-gradient(to bottom right, #ffffff 49.9%, #222226 50.1%); }
.style-switcher .light { background: #ffffff; }
.style-switcher .dark { background: #222226; }
"""


def apply_appearance(appearance: str) -> None:
    Adw.StyleManager.get_default().set_color_scheme(COLOR_SCHEMES[appearance])


def choose_appearance(appearance: str) -> None:
    apply_appearance(appearance)
    settings.save(settings.store_path(), settings.Settings(appearance))


def _style_switcher() -> Gtk.Widget:
    current = settings.load(settings.store_path()).appearance
    names = {
        "system": _("Follow System Style"),
        "light": _("Light Style"),
        "dark": _("Dark Style"),
    }
    box = Gtk.Box(spacing=18, halign=Gtk.Align.CENTER, css_classes=["style-switcher"])
    group = None
    for appearance, name in names.items():
        button = Gtk.CheckButton(
            group=group,
            active=appearance == current,
            tooltip_text=name,
            css_classes=[appearance],
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.CENTER,
        )
        button.update_property([Gtk.AccessibleProperty.LABEL], [name])
        button.connect("toggled", lambda b, a=appearance: b.get_active() and choose_appearance(a))
        group = group or button
        box.append(button)
    return box


def main_menu() -> Gtk.MenuButton:
    """The primary menu: F10 opens it (GtkMenuButton:primary)."""
    menu = Gio.Menu()
    switcher = Gio.MenuItem()
    switcher.set_attribute_value("custom", GLib.Variant.new_string("style-switcher"))
    menu.append_item(switcher)
    items = Gio.Menu()
    items.append(_("Open a Song…"), "win.open")
    items.append(_("Keyboard Shortcuts"), "app.shortcuts")
    items.append(_("About Stickler"), "app.about")
    menu.append_section(None, items)
    popover = Gtk.PopoverMenu.new_from_model(menu)
    popover.add_child(_style_switcher(), "style-switcher")
    return Gtk.MenuButton(
        icon_name="open-menu-symbolic", popover=popover, primary=True, tooltip_text=_("Main Menu")
    )


SHORTCUTS = (
    ("<Control>o", N_("Open a Song")),
    ("<Control>e", N_("Export")),
    ("Escape", N_("Cancel the Analysis or Export")),
    ("F10", N_("Main Menu")),
    ("<Control>question", N_("Keyboard Shortcuts")),
    ("<Control>w", N_("Close the Window")),
    ("<Control>q", N_("Quit")),
)


def shortcuts_dialog() -> Adw.ShortcutsDialog:
    section = Adw.ShortcutsSection()
    for accelerator, title in SHORTCUTS:
        section.add(Adw.ShortcutsItem(title=_(title), accelerator=accelerator))
    dialog = Adw.ShortcutsDialog()
    dialog.add(section)
    return dialog


def about_dialog() -> Adw.AboutDialog:
    return Adw.AboutDialog(
        application_name=APP_NAME,
        application_icon=APP_ID,
        version=stickler.__version__,
        developer_name="Niklas Tshiang Tshiananga",
        comments=_("Writes the drums of a song as sheet music, so you can play along."),
        license_type=Gtk.License.MIT_X11,
        website=WEBSITE,
        issue_url=f"{WEBSITE}/issues",
    )
