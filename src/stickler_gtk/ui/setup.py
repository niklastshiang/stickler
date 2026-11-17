"""The setup assistant's consent page (SPEC.md, module `setup-assistant`; design screen 1). The
download runs on the step list of the analysing page; what to show and the sizes are
`logic.setup`'s business."""

from __future__ import annotations

from gi.repository import Adw, Gtk

from stickler_app import setup
from stickler_app.i18n import _, ngettext
from stickler_app.steps import model_name


def consent_page(missing: tuple[str, ...]) -> Gtk.Widget:
    """What is downloaded, what each model does, its licence and size; "Not Now" and
    "Download" (win.setup-later, win.setup-download)."""
    intro = ngettext(
        "To hear the drums, Stickler needs a trained model. It is downloaded once; after "
        "that, everything runs on this computer, offline.",
        "To hear the drums, Stickler needs {count} trained models. They are downloaded once; "
        "after that, everything runs on this computer, offline.",
        len(missing),
    ).format(count=len(missing))
    models = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["boxed-list"])
    for adapter in missing:
        does, licence = setup.model_text(adapter)
        title = f"{model_name(adapter)} · {does}" if does else model_name(adapter)
        row = Adw.ActionRow(title=title, subtitle=licence, subtitle_lines=0)
        row.add_suffix(Gtk.Label(label=setup.model_size(adapter), css_classes=["numeric"]))
        models.append(row)
    total = Adw.ActionRow(title=_("Together, on disk"))
    total.add_suffix(
        Gtk.Label(
            label=_("about {size}").format(size=setup.total_size(missing)),
            css_classes=["numeric", "heading"],
        )
    )
    models.append(total)

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
    box.append(Adw.Clamp(maximum_size=520, child=models))
    if "adtof" in missing:
        note = Gtk.Label(
            label=_(
                "By downloading, you accept that ADTOF’s model is used for non-commercial "
                "purposes only."
            ),
            wrap=True,
            justify=Gtk.Justification.CENTER,
            css_classes=["caption", "dim-label"],
        )
        box.append(Adw.Clamp(maximum_size=520, child=note))
    later = Gtk.Button(label=_("Not Now"), action_name="win.setup-later", css_classes=["pill"])
    download = Gtk.Button(
        label=_("Download {size}").format(size=setup.total_size(missing)),
        action_name="win.setup-download",
        css_classes=["pill", "suggested-action"],
    )
    buttons = Adw.WrapBox(child_spacing=12, line_spacing=12, align=0.5)
    buttons.append(later)
    buttons.append(download)
    box.append(buttons)
    return Adw.StatusPage(
        icon_name="ng.tshia.Stickler",
        title=_("Welcome to Stickler"),
        description=intro,
        child=box,
    )


def error_page(steps, server: str, details: str) -> Gtk.Widget:
    """Design screen 3: which server did not answer; what is done stays; "Later" and "Try
    Again" (win.setup-later, win.setup-retry)."""
    rows = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["boxed-list"])
    for step in steps:
        row = Adw.ActionRow(title=step.label)
        if step.state == "done":
            icon = Gtk.Image(icon_name="object-select-symbolic", css_classes=["success"])
            row.add_prefix(icon)
            row.add_suffix(Gtk.Label(label=_("Ready"), css_classes=["dim-label"]))
        else:
            row.add_prefix(Gtk.Image(icon_name="network-error-symbolic", opacity=0.6))
            row.add_suffix(Gtk.Label(label=_("Not reached"), css_classes=["dim-label"]))
        rows.append(row)
    text = Gtk.Label(label=details, selectable=True, wrap=True, xalign=0, css_classes=["monospace"])
    expander = Gtk.Expander(label=_("Technical Details"), child=text)
    later = Gtk.Button(label=_("Later"), action_name="win.setup-later", css_classes=["pill"])
    again = Gtk.Button(
        label=_("Try Again"),
        action_name="win.setup-retry",
        css_classes=["pill", "suggested-action"],
    )
    buttons = Adw.WrapBox(child_spacing=12, line_spacing=12, align=0.5)
    buttons.append(later)
    buttons.append(again)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
    box.append(Adw.Clamp(maximum_size=520, child=rows))
    box.append(Adw.Clamp(maximum_size=520, child=expander))
    box.append(buttons)
    return Adw.StatusPage(
        icon_name="network-error-symbolic",
        title=_("A Download Server Is Not Answering"),
        description=_(
            "Stickler could not reach {server}. Everything that is done stays downloaded."
        ).format(server=server),
        child=box,
    )
