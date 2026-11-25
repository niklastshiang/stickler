import AppKit
import SticklerCore
import SwiftUI
import XCTest

@testable import Stickler

/// A player that plays nothing, for pictures of the controls.
@MainActor
final class QuietPlayer: Playing {
    var position = 0.0
    var paused: (@MainActor (PlayerPause) -> Void)?

    func load(song _: URL, clicks _: URL?) throws {}
    func play() throws {}
    func pause() {}
    func seek(to seconds: Double) { position = seconds }
    func setGains(_: Gains) {}
    func stop() {}
}

/// Design screen M10 in the screenshots (SPEC.md "Mac playback", Testing): the controls over
/// the sheet in light and dark, and the volume popover.
extension ScreenshotTests {
    /// The groove of `pages.json` as a result that plays: 8 bars of 2 s.
    static let playing: String = {
        let bars = (0..<8).map { bar in
            #"{"start": \#(Double(bar) * 2), "end": \#(Double(bar + 1) * 2), "#
                + #""bar": \#(bar + 1), "label": "Bar \#(bar + 1) of 8"}"#
        }
        return #"{"event": "state", "seq": 3, "state": {"kind": "result", "#
            + #""song": "/Users/me/Music/Eye of the Tiger.flac", "title": "Eye of the Tiger", "#
            + #""subtitle": "Survivor · ♩ = 109 · 4/4", "artist": "Survivor", "seconds": 16.0, "#
            + #""tempo": 109, "meter": [4, 4], "musicxml": "/c/e.musicxml", "corrections": "#
            + #"{"tempo": "normal", "beats_per_bar": null, "first_downbeat": null, "#
            + #""simplify": true, "repeats": true}, "correcting": false, "#
            + #""clicks": "/c/e.wav", "bars": [\#(bars.joined(separator: ", "))], "#
            + #""can_open": true, "can_close": true, "can_export": true}}"#
    }()

    func playingModel() async throws -> AppModel {
        let lines = [Self.empty, Self.recent, Self.playing]
        let core = ScriptedCore(
            lines: lines,
            replies: [
                "pages": try Self.pagesReply(), "settings": Self.settings,
                "volumes": #""ok": true, "song": 0.0, "hits": 1.0"#
            ])
        let model = try await model(lines, core: core, player: QuietPlayer())
        try await wait(2) { model.playback.canPlay }
        model.playback.seek(to: 3)  // in the second bar, as the canvas shows it
        return model
    }

    func testTheControlsFloatOverTheSheet() async throws {
        let model = try await playingModel()
        XCTAssertEqual(model.playback.label, "Bar 2 of 8")
        XCTAssertEqual(model.playback.time, "0:03")
        XCTAssertEqual(model.playback.lengthText, "0:16")
        XCTAssertEqual(model.playback.marked, 2)
        // the window's picture has the marker; the sheet's snapshot is drawn over the window
        // where the web view is, the controls too, so they are shot again on their own
        try await shoot(model, "M10-playing")
        try await shootView(overlay(model), "M10-controls")
        model.playback.setHear(.hits)  // the canvas's dark board hears only the hits
        XCTAssertEqual(model.playback.hear, .hits)
        try await shootView(overlay(model), "M10-controls-hits")
    }

    func testTheSavedNoteSitsAboveTheControls() async throws {
        let model = try await playingModel()
        model.tell(Notice(text: "Saved “Eye of the Tiger.pdf”", opens: "/tmp/e.pdf"))
        try await shootView(overlay(model), "M10-saved")
    }

    /// Each part of the capsule is as wide as its words (owner, 2026-11-25: a fixed width let
    /// the German Song · Schläge · Beides spill over the Volume button), and in a narrow page
    /// the capsule gives way part by part, down to what fits beside an inspector.
    func testTheControlsFitTheirWordsAndGiveWay() async throws {
        let model = try await playingModel()
        let bar = Playbar(playback: model.playback)
        var full: [String: Double] = [:]
        for language in ["en", "de", "es"] {
            let fits = Playbar.Fit.allCases.map { least(bar.row($0), in: language) }
            full[language] = fits[0]
            for (wider, narrower) in zip(fits, fits.dropFirst()) {
                XCTAssertGreaterThan(wider, narrower, "\(language): \(fits)")
            }
            let overlay = least(PlaybackOverlay(model: model), in: language)
            XCTAssertLessThanOrEqual(overlay, ContentView.minimumWidth, "\(language): \(fits)")
        }
        // the words are measured in each language, not a width set for English
        XCTAssertGreaterThan(full["de", default: 0], full["en", default: 0], "\(full)")
        try await shootView(overlay(model, width: 520), "M10-controls-narrow")
    }

    func testTheBarTextKeepsTheWidthOfTheSongsWidest() {
        let bars = [
            SongBar(start: 0, end: 2, bar: 9, label: "Bar 9 of 10"),
            SongBar(start: 2, end: 4, bar: 10, label: "Bar 10 of 10"),
            SongBar(start: 4, end: 6, bar: 9, label: "Bar 9 of 10")
        ]
        XCTAssertEqual(Playbar.widest(bars), "Bar 10 of 10")
        XCTAssertEqual(Playbar.widest([]), "")
    }

    /// The least width `view` takes in `language`.
    func least(_ view: some View, in language: String) -> Double {
        let host = NSHostingController(
            rootView: view.environment(\.locale, Locale(identifier: language)))
        return host.sizeThatFits(in: CGSize(width: 10, height: 200)).width
    }

    /// The controls as they float over the sheet of a window `width` points wide.
    func overlay(_ model: AppModel, width: Double = 900) -> some View {
        PlaybackOverlay(model: model).frame(width: width)
    }

    func testTheVolumePopoverHoldsBothSliders() async throws {
        let model = try await playingModel()
        try await shootView(VolumeSliders(playback: model.playback), "M10-volume")
    }

    /// `view` alone in a window, saved in both appearances like `shoot`.
    func shootView(_ view: some View, _ name: String) async throws {
        for (appearance, look) in [(NSAppearance.Name.aqua, "light"), (.darkAqua, "dark")] {
            let host = NSHostingController(rootView: view)
            let window = NSWindow(contentViewController: host)
            window.appearance = NSAppearance(named: appearance)
            window.orderFront(nil)
            try await Task.sleep(for: .milliseconds(300))
            let frame = try XCTUnwrap(window.contentView)
            let bitmap = try XCTUnwrap(frame.bitmapImageRepForCachingDisplay(in: frame.bounds))
            frame.cacheDisplay(in: frame.bounds, to: bitmap)
            window.orderOut(nil)
            XCTAssertGreaterThan(colours(in: bitmap), 2, "\(name) \(look) is blank")
            let png = try XCTUnwrap(bitmap.representation(using: .png, properties: [:]))
            try FileManager.default.createDirectory(
                at: Self.folder, withIntermediateDirectories: true)
            try png.write(to: Self.folder.appendingPathComponent("\(name)-\(look).png"))
        }
    }
}
