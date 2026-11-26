"""The corrections' controls (SPEC.md, module `corrections`; design screens 7 and 11), shown in
the sidebar or, in a narrow window, in a bottom sheet. Each change is reported at once as the
new `api.Corrections`; what they mean and their ranges are `logic.corrections`' business."""

from __future__ import annotations

from collections.abc import Callable

from gi.repository import Adw, Gtk

from stickler import api
from stickler_app import corrections
from stickler_app.i18n import _

WIDTH = 340  # design screen 7


class CorrectionsPanel(Gtk.Box):
    def __init__(self, on_change: Callable[[api.Corrections], None]) -> None:
        super().__init__(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=18,
            margin_top=18,
            margin_bottom=18,
            margin_start=16,
            margin_end=16,
        )
        self.on_change = on_change
        self.fix = corrections.DETECTED
        self.beats_per_bar = 4
        self.first = 1
        self._showing = False  # set while values are shown, so they are not reported back

        self.tempo = Adw.ToggleGroup(valign=Gtk.Align.CENTER)
        self.tempo.update_property([Gtk.AccessibleProperty.LABEL], [_("Tempo")])
        for name, label in (
            ("half", _("Half")),
            ("normal", _("As Detected")),
            ("double", _("Double")),
        ):
            self.tempo.add(Adw.Toggle(name=name, label=label))
        self.tempo.connect("notify::active-name", lambda *_a: self._tempo_changed())
        tempo_row = Adw.PreferencesRow(activatable=False)
        tempo_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=8,
            margin_top=10,
            margin_bottom=10,
            margin_start=12,
            margin_end=12,
        )
        tempo_box.append(Gtk.Label(label=_("Tempo"), xalign=0))
        tempo_box.append(self.tempo)
        tempo_row.set_child(tempo_box)

        self.beats = Adw.SpinRow.new_with_range(corrections.FEWEST_BEATS, corrections.MOST_BEATS, 1)
        self.beats.set_title(_("Beats per bar"))
        self.beats.connect("notify::value", lambda *_a: self._beats_changed())

        self.earlier = Gtk.Button(
            icon_name="go-previous-symbolic",
            tooltip_text=_("Earlier first one"),
            valign=Gtk.Align.CENTER,
            css_classes=["flat"],
        )
        self.later = Gtk.Button(
            icon_name="go-next-symbolic",
            tooltip_text=_("Later first one"),
            valign=Gtk.Align.CENTER,
            css_classes=["flat"],
        )
        self.first_one = Gtk.Label(css_classes=["numeric"])
        self.earlier.connect("clicked", lambda _b: self._move_first(-1))
        self.later.connect("clicked", lambda _b: self._move_first(1))
        first_row = Adw.ActionRow(
            title=_("First “one”"), subtitle=_("Beats before it are a pickup")
        )
        for widget in (self.earlier, self.first_one, self.later):
            first_row.add_suffix(widget)

        beat = Adw.PreferencesGroup(title=_("Beat"))
        for row in (tempo_row, self.beats, first_row):
            beat.add(row)

        self.simplify = Adw.SwitchRow(
            title=_("Simplify"), subtitle=_("Nearly equal bars get one pattern")
        )
        self.repeats = Adw.SwitchRow(
            title=_("Repeat signs"), subtitle=_("Equal bars are written once")
        )
        self.simplify.connect("notify::active", lambda *_a: self._switched())
        self.repeats.connect("notify::active", lambda *_a: self._switched())
        easier = Adw.PreferencesGroup(title=_("Easier to Read"))
        easier.add(self.simplify)
        easier.add(self.repeats)

        self.back = Gtk.Button(label=_("Back to Detected"), halign=Gtk.Align.CENTER)
        self.back.add_css_class("pill")
        self.back.connect("clicked", lambda _b: self._report(corrections.DETECTED))
        for widget in (beat, easier, self.back):
            self.append(widget)

    # what the window asks

    def show_values(self, fix: api.Corrections, *, beats_per_bar: int, first_one: int) -> None:
        """`fix` as the controls show it; `beats_per_bar` and `first_one` as engraved, for the
        values the reader has not set."""
        shown = corrections.controls(fix, beats_per_bar=beats_per_bar, first_one=first_one)
        self._showing = True
        try:
            self.fix = fix
            self.beats_per_bar = shown.beats_per_bar
            self.first = shown.first_one
            self.tempo.set_active_name(shown.tempo)
            self.beats.set_value(shown.beats_per_bar)
            self.first_one.set_label(shown.first_one_label)
            self.earlier.set_sensitive(shown.earlier)
            self.later.set_sensitive(shown.later)
            self.simplify.set_active(shown.simplify)
            self.repeats.set_active(shown.repeats)
            self.back.set_sensitive(shown.corrected)
        finally:
            self._showing = False

    # what the reader does

    def _report(self, fix: api.Corrections) -> None:
        if self._showing or fix == self.fix:
            return
        self.show_values(fix, beats_per_bar=self.beats_per_bar, first_one=self.first)
        self.on_change(fix)

    def _tempo_changed(self) -> None:
        self._report(corrections.with_tempo(self.fix, self.tempo.get_active_name() or "normal"))

    def _beats_changed(self) -> None:
        beats = round(self.beats.get_value())
        if beats != self.beats_per_bar:
            self._report(corrections.with_beats(self.fix, beats))

    def _move_first(self, by: int) -> None:
        moved = corrections.with_first_one(
            self.fix, self.first + by, beats_per_bar=self.beats_per_bar
        )
        self._report(moved)

    def _switched(self) -> None:
        fix = corrections.with_simplify(self.fix, self.simplify.get_active())
        self._report(corrections.with_repeats(fix, self.repeats.get_active()))
