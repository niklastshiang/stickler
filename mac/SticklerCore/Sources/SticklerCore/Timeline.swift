import Foundation

/// What to hear (design screen M10's segmented picker): the song, the detected hits as
/// clicks, or both.
public enum Hear: String, Codable, CaseIterable, Sendable {
    case song, hits, both
}

/// The lookups the controls and the marker make 20 times a second (SPEC.md "Mac playback",
/// "Where each decision lives"): a round trip to the core per frame would wait behind
/// `pages`. Each mirrors a function of `stickler_app` and is tested with its cases; the bars
/// and their texts are the core's.
public enum Timeline {
    /// The index of the song bar started by `seconds`: the last one whose start is not later;
    /// nil before the first.
    public static func index(_ bars: [SongBar], at seconds: Double) -> Int? {
        var low = 0
        var high = bars.count
        while low < high {
            let middle = (low + high) / 2
            if bars[middle].start <= seconds {
                low = middle + 1
            } else {
                high = middle
            }
        }
        return low > 0 ? low - 1 : nil
    }

    /// The written bar sounding at `seconds` (`marker.written_at`); nil before the first bar
    /// and from the last one's end.
    public static func written(_ bars: [SongBar], at seconds: Double) -> Int? {
        guard let sounding = index(bars, at: seconds), seconds < bars[sounding].end else {
            return nil
        }
        return bars[sounding].bar
    }

    /// "Bar 3 of 110" at `seconds` (`playback.bar_label`): before the first bar the first
    /// one's, after the last the last one's; nothing without bars.
    public static func label(_ bars: [SongBar], at seconds: Double) -> String {
        guard !bars.isEmpty else { return "" }
        return bars[index(bars, at: seconds) ?? 0].label
    }

    /// The time as the controls show it (`playback.clock`): "0:06", "4:06", "1:02:05".
    public static func clock(_ seconds: Double) -> String {
        let whole = seconds.isFinite ? Int(max(seconds, 0)) : 0
        let (hours, rest) = whole.quotientAndRemainder(dividingBy: 3600)
        let (minutes, secs) = rest.quotientAndRemainder(dividingBy: 60)
        let twoDigits = { (value: Int) in value < 10 ? "0\(value)" : "\(value)" }
        return hours > 0
            ? "\(hours):\(twoDigits(minutes)):\(twoDigits(secs))"
            : "\(minutes):\(twoDigits(secs))"
    }
}

/// Where the sheet marks a bar and which bar a click is on (`stickler_app.marker`).
public enum Marker {
    /// A written bar's place: the page it is on and its rectangle there.
    public struct Mark: Equatable, Sendable {
        public let page: Int
        public let box: BarBox

        public init(page: Int, box: BarBox) {
            self.page = page
            self.box = box
        }
    }

    /// The page and rectangle that mark written bar `written` (`marker.locate`): a bar
    /// without a rectangle of its own (inside a multi-measure rest) is shown by the nearest
    /// engraved bar before it. Nil when no engraved bar comes before it.
    public static func locate(_ written: Int, in pages: [Page]) -> Mark? {
        var found: (bar: Int, mark: Mark)?
        for (number, page) in pages.enumerated() {
            for box in page.bars where box.bar <= written {
                if let best = found, best.bar > box.bar {
                    continue
                }
                found = (box.bar, Mark(page: number, box: box))
            }
        }
        return found?.mark
    }

    /// The written bar whose rectangle holds the point, in page pixels
    /// (`marker.bar_at_point`).
    public static func bar(atX x: Double, y: Double, on page: Page) -> Int? {
        page.bars.first { box in
            box.x <= x && x <= box.x + box.width && box.y <= y && y <= box.y + box.height
        }?.bar
    }
}
