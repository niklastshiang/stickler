import Foundation

/// The fields of the replies that carry more than `ok` (`Reply.payload(_:)`).

/// A written bar's rectangle on a page, in page pixels (a click on it jumps there).
public struct BarBox: Codable, Equatable, Sendable {
    public var bar: Int
    public var x: Double
    public var y: Double
    public var width: Double
    public var height: Double
}

/// One engraved page: its SVG, its size and its bars.
public struct Page: Codable, Equatable, Sendable {
    public var svg: String
    public var width: Double
    public var height: Double
    public var bars: [BarBox]
}

/// `pages`: the sheet music at a width and note size.
public struct Pages: Codable, Equatable, Sendable {
    public var zoom: Double
    public var pages: [Page]
}

/// `a4_pages`: the pages of the PDF and its title.
public struct A4Pages: Codable, Equatable, Sendable {
    public var title: String
    public var pages: [Page]
}

/// `drum_track_cost`: what saving the drum track costs, said before it starts.
public struct DrumTrackCost: Codable, Equatable, Sendable {
    public var minutes: Int
    public var text: String
    public var download: Bool
}

/// `settings`: the stored settings, the note size as the menu shows it.
public struct Settings: Codable, Equatable, Sendable {
    public var appearance: String
    public var zoom: Double
    public var songVolume: Double
    public var hitsVolume: Double
    public var setupAgreed: Bool
    public var percent: String
}

/// `set_zoom`, `zoom_in`, `zoom_out`, `actual_size`: the new note size.
public struct Zoom: Codable, Equatable, Sendable {
    public var zoom: Double
    public var percent: String
}

/// `removal_sizes`: what "Remove Downloaded Models…" frees, and the dialog's text for both.
public struct RemovalSizes: Codable, Equatable, Sendable {
    public var models: Int64
    public var everything: Int64
    public var modelsText: String
    public var everythingText: String

    public init(models: Int64, everything: Int64, modelsText: String, everythingText: String) {
        self.models = models
        self.everything = everything
        self.modelsText = modelsText
        self.everythingText = everythingText
    }
}

/// `uninstall_sizes`: what "Uninstall Stickler…" frees, and the dialog's text for both.
public struct UninstallSizes: Codable, Equatable, Sendable {
    public var keep: Int64
    public var everything: Int64
    public var keepText: String
    public var everythingText: String

    public init(keep: Int64, everything: Int64, keepText: String, everythingText: String) {
        self.keep = keep
        self.everything = everything
        self.keepText = keepText
        self.everythingText = everythingText
    }
}

/// A reply that carries nothing but its `ok` (`uninstall`).
public struct Done: Codable, Equatable, Sendable {}

/// `backup_summary`: what a backup holds, and the restore's question.
public struct BackupSummary: Codable, Equatable, Sendable {
    public var created: String
    public var songs: Int
    public var size: Int64
    public var text: String

    public init(created: String, songs: Int, size: Int64, text: String) {
        self.created = created
        self.songs = songs
        self.size = size
        self.text = text
    }
}

/// The names the save panels propose, as the GTK app's (`stickler_app.exports`).
public enum ExportName {
    /// The song's file name without its suffix, or "Stickler" when that is blank.
    public static func base(of song: String) -> String {
        let stem = URL(fileURLWithPath: song).deletingPathExtension().lastPathComponent
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return stem.isEmpty ? "Stickler" : stem
    }

    public static func musicXML(_ song: String) -> String { base(of: song) + ".musicxml" }

    public static func pdf(_ song: String) -> String { base(of: song) + ".pdf" }
}
