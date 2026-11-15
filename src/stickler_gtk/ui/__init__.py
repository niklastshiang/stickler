"""The widgets. They show what `stickler_gtk.logic` decides and hold no logic of their own.

Importing this package pins the GTK versions, before any module imports `gi.repository`."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GLibUnix", "2.0")
gi.require_version("Rsvg", "2.0")
