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
