import AppKit
import SticklerCore
import SwiftUI
import XCTest

@testable import Stickler

/// The corrections inspector's decisions and design screen M11 (SPEC.md "Mac corrections",
/// Testing), with the core played by `ScriptedCore`.
@MainActor
final class CorrectionsTests: XCTestCase {
    /// A result as the core sends it with its corrections' controls; `bars` makes it play.
    static func result(
        tempo: String = "normal", simplify: Bool = true, correcting: Bool = false,
        subtitle: String = "Survivor · ♩ = 109 · 4/4", controls: Bool = true, bars: Bool = false
    ) -> String {
        let corrected = tempo != "normal" || !simplify
        let shown = #""controls": {"tempo": "\#(tempo)", "beats_per_bar": 4, "fewer": true, "#
            + #""more": true, "first_one": 1, "#
            + #""first_one_label": "Beat 1", "earlier": false, "later": true, "#
            + #""simplify": \#(simplify), "repeats": true, "corrected": \#(corrected)}, "#
        let played = (0..<8).map { bar in
            #"{"start": \#(Double(bar) * 2), "end": \#(Double(bar + 1) * 2), "#
                + #""bar": \#(bar + 1), "label": "Bar \#(bar + 1) of 8"}"#
        }
        return #"{"event": "state", "seq": 3, "state": {"kind": "result", "#
            + #""song": "/Users/me/Music/Eye of the Tiger.flac", "title": "Eye of the Tiger", "#
            + #""subtitle": "\#(subtitle)", "artist": "Survivor", "seconds": 16.0, "#
            + #""tempo": 109, "meter": [4, 4], "musicxml": "/c/e.musicxml", "corrections": "#
            + #"{"tempo": "\#(tempo)", "beats_per_bar": null, "first_downbeat": null, "#
            + #""simplify": \#(simplify), "repeats": true}, "correcting": \#(correcting), "#
            + (controls ? shown : "") + #""sheet": 4, "#
            + (bars ? #""clicks": "/c/e.wav", "bars": [\#(played.joined(separator: ", "))], "# : "")
            + #""can_open": true, "can_close": true, "can_export": true}}"#
    }

    func model(_ lines: [String]) async throws -> (AppModel, ScriptedCore) {
        let core = ScriptedCore(
            lines: lines,
            replies: [
                "pages": try ScreenshotTests.pagesReply(), "settings": ScreenshotTests.settings,
                "volumes": #""ok": true, "song": 0.7, "hits": 1.0"#
            ])
        let defaults = try XCTUnwrap(UserDefaults(suiteName: "corrections-\(UUID().uuidString)"))
        let model = AppModel(defaults: defaults, languages: ["en"], player: QuietPlayer()) { _ in
            core
        }
        model.launch()
        var waited = 0
        while model.state.screen.kind != lines.last.map(kind) ?? "", waited < 200 {
            waited += 1
            try await Task.sleep(for: .milliseconds(10))
        }
        return (model, core)
    }

    private func kind(_ line: String) -> String {
        line.contains(#""kind": "result""#) ? "result" : "empty"
    }

    func testOnlyAResultWithControlsCanBeCorrected() async throws {
        let (empty, _) = try await model([ScreenshotTests.empty])
        XCTAssertNil(CorrectionsMenu.controls(empty))
        XCTAssertFalse(CorrectionsMenu.enabled(empty))
        XCTAssertFalse(CorrectionsMenu.presented(shown: true, empty))  // remembered, not shown
        XCTAssertFalse(CorrectionsMenu.correcting(empty))

        let (older, _) = try await model([ScreenshotTests.empty, Self.result(controls: false)])
        XCTAssertEqual(older.state.screen.kind, "result")
        XCTAssertFalse(CorrectionsMenu.enabled(older))  // a core from before the corrections

        let (shown, _) = try await model([ScreenshotTests.empty, Self.result(simplify: false)])
        let controls = try XCTUnwrap(CorrectionsMenu.controls(shown))
        XCTAssertEqual(controls.firstOneLabel, "Beat 1")
        XCTAssertTrue(controls.corrected)
        XCTAssertTrue(CorrectionsMenu.presented(shown: true, shown))
        XCTAssertFalse(CorrectionsMenu.presented(shown: false, shown))
        XCTAssertFalse(CorrectionsMenu.correcting(shown))
    }

    func testTheMenuItemSaysWhatItDoesAndHasTheInspectorsKey() {
        XCTAssertEqual(CorrectionsMenu.title(presented: false), "Show Corrections")
        XCTAssertEqual(CorrectionsMenu.title(presented: true), "Hide Corrections")
        XCTAssertEqual(CorrectionsMenu.key, "i")
        XCTAssertEqual(CorrectionsMenu.modifiers, [.control, .command])
        XCTAssertEqual(CorrectionsMenu.shownKey, "CorrectionsShown")
    }

    func testTheSpinnerTurnsAndNothingIsExportedWhileACorrectionIsWritten() async throws {
        let line = Self.result(tempo: "half", correcting: true)
        let (writing, _) = try await model([ScreenshotTests.empty, line])
        XCTAssertTrue(CorrectionsMenu.correcting(writing))
        XCTAssertNil(Exports.result(writing))  // the core would refuse: the old notes
        let (written, _) = try await model([ScreenshotTests.empty, Self.result(tempo: "half")])
        XCTAssertNotNil(Exports.result(written))
    }

    func testTheInspectorBuildsAndTheModelSendsEachChange() async throws {
        let (model, core) = try await model([ScreenshotTests.empty, Self.result()])
        let controls = try XCTUnwrap(CorrectionsMenu.controls(model))
        let inspector = CorrectionsInspector(model: model, controls: controls)
        XCTAssertEqual(CorrectionsInspector.width, 300)
        _ = inspector.body  // builds without a window
        model.correct(.beatsPerBarBy(1))
        model.correct(.detected)
        var waited = 0
        while core.sent.filter({ $0.name == "correct" }).count < 2, waited < 200 {
            waited += 1
            try await Task.sleep(for: .milliseconds(10))
        }
        XCTAssertEqual(
            core.sent.filter { $0.name == "correct" },
            [.correct(.beatsPerBarBy(1)), .correct(.detected)])
    }
}

/// Design screen M11 in the screenshots: the inspector beside the sheet, with Simplify off;
/// while playing a correction being written (half tempo).
extension ScreenshotTests {
    func testTheCorrectionsSitInAnInspectorBesideTheSheet() async throws {
        UserDefaults.standard.set(true, forKey: CorrectionsMenu.shownKey)
        defer { UserDefaults.standard.removeObject(forKey: CorrectionsMenu.shownKey) }
        let lines = [Self.empty, Self.recent, CorrectionsTests.result(simplify: false)]
        let core = ScriptedCore(
            lines: lines, replies: ["pages": try Self.pagesReply(), "settings": Self.settings])
        let model = try await model(lines, core: core)
        XCTAssertTrue(CorrectionsMenu.presented(shown: true, model))
        try await shoot(model, "M11-corrections")
        let controls = try XCTUnwrap(CorrectionsMenu.controls(model))
        try await shootView(
            CorrectionsInspector(model: model, controls: controls)
                .frame(width: CorrectionsInspector.width, height: 520),
            "M11-inspector")
    }

    func testACorrectionBeingWrittenWhilePlaying() async throws {
        UserDefaults.standard.set(true, forKey: CorrectionsMenu.shownKey)
        defer { UserDefaults.standard.removeObject(forKey: CorrectionsMenu.shownKey) }
        let line = CorrectionsTests.result(
            tempo: "half", correcting: true, subtitle: "Survivor · ♩ = 55 · 4/4", bars: true)
        let lines = [Self.empty, Self.recent, line]
        let core = ScriptedCore(
            lines: lines,
            replies: [
                "pages": try Self.pagesReply(), "settings": Self.settings,
                "volumes": #""ok": true, "song": 0.7, "hits": 1.0"#
            ])
        let model = try await model(lines, core: core, player: QuietPlayer())
        try await wait(2) { model.playback.canPlay }
        model.playback.seek(to: 3)
        XCTAssertTrue(CorrectionsMenu.correcting(model))
        try await shoot(model, "M11-correcting")
    }
}
