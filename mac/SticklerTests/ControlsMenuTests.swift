import AppKit
import SticklerCore
import SwiftUI
import XCTest

@testable import Stickler

/// The Controls menu (SPEC.md "Mac playback", scope 6): its items, their keys and what each
/// tells the playback model, with the core played by `ScriptedCore`.
@MainActor
final class ControlsMenuTests: XCTestCase {
    /// A model showing a result that plays, its core answering `step` with 4 s.
    func playing() async throws -> (AppModel, ScriptedCore, QuietPlayer) {
        let lines = [ScreenshotTests.empty, ScreenshotTests.playing]
        let core = ScriptedCore(
            lines: lines,
            replies: [
                "settings": ScreenshotTests.settings,
                "step": #""ok": true, "seconds": 4.0"#,
                "volumes": #""ok": true, "song": 0.0, "hits": 1.0"#
            ])
        let player = QuietPlayer()
        let defaults = try XCTUnwrap(UserDefaults(suiteName: "controls-\(UUID().uuidString)"))
        let model = AppModel(defaults: defaults, languages: ["en"], player: player) { _ in core }
        model.launch()
        try await until { model.playback.canPlay }
        return (model, core, player)
    }

    func until(_ condition: @escaping () -> Bool) async throws {
        var waited = 0
        while !condition(), waited < 200 {
            waited += 1
            try await Task.sleep(for: .milliseconds(10))
        }
        XCTAssertTrue(condition(), "timed out")
    }

    func testTheItemsAndTheirKeysAreMusicsAndQuickTimes() async throws {
        let (model, _, _) = try await playing()
        let items = ControlsMenu.items(model.playback)
        XCTAssertEqual(
            items.map(\.title), ["Play", "Previous Bar", "Next Bar", "Go to the Start"])
        XCTAssertEqual(items.map(\.key), [.space, .leftArrow, .rightArrow, .leftArrow])
        XCTAssertEqual(items.map(\.modifiers), [[], [], [], .option])
        XCTAssertEqual(ControlsMenu.hearing.map(\.title), ["Song", "Hits", "Both"])
        XCTAssertEqual(ControlsMenu.hearing.map(\.hear), [.song, .hits, .both])
    }

    func testTheFirstItemSaysWhatSpaceDoesNow() async throws {
        let (model, _, _) = try await playing()
        XCTAssertEqual(ControlsMenu.playTitle(model.playback), "Play")
        ControlsMenu.items(model.playback)[0].act(model.playback)
        try await until { model.playback.playing }
        XCTAssertEqual(ControlsMenu.playTitle(model.playback), "Pause")
        XCTAssertEqual(ControlsMenu.items(model.playback)[0].title, "Pause")
        ControlsMenu.items(model.playback)[0].act(model.playback)
        XCTAssertFalse(model.playback.playing)
    }

    func testEachItemTellsThePlaybackModel() async throws {
        let (model, core, _) = try await playing()
        let items = ControlsMenu.items(model.playback)
        items[2].act(model.playback)  // Next Bar
        try await until { model.playback.position == 4 }
        XCTAssertTrue(core.sent.contains(.step(from: 0, count: 1)))
        items[1].act(model.playback)  // Previous Bar
        try await until { core.sent.contains(.step(from: 4, count: -1)) }
        model.playback.seek(to: 9)
        items[3].act(model.playback)  // Go to the Start
        XCTAssertEqual(model.playback.position, 0)
    }

    func testTheItemsWorkOnlyWithAResult() async throws {
        let (model, _, _) = try await playing()
        XCTAssertTrue(ControlsMenu.enabled(model))
        model.close()
        let defaults = try XCTUnwrap(UserDefaults(suiteName: "controls-\(UUID().uuidString)"))
        let core = ScriptedCore(lines: [ScreenshotTests.empty])
        let empty = AppModel(defaults: defaults, languages: ["en"], player: QuietPlayer()) { _ in
            core
        }
        XCTAssertFalse(ControlsMenu.enabled(empty), "before the launch")
        empty.launch()
        try await Task.sleep(for: .milliseconds(50))
        XCTAssertFalse(ControlsMenu.enabled(empty), "no result")
    }

    func testHomeAloneInTheWindowGoesToTheStart() {
        let home = ControlsMenu.homeKey
        XCTAssertTrue(
            ControlsMenu.goesToStart(
                keyCode: home, modifiers: [], inMainWindow: true, canPlay: true))
        XCTAssertTrue(
            ControlsMenu.goesToStart(
                keyCode: home, modifiers: .function, inMainWindow: true, canPlay: true),
            "the Fn key some keyboards need for Home")
        XCTAssertFalse(
            ControlsMenu.goesToStart(
                keyCode: home, modifiers: .shift, inMainWindow: true, canPlay: true))
        XCTAssertFalse(
            ControlsMenu.goesToStart(
                keyCode: home, modifiers: [], inMainWindow: false, canPlay: true),
            "a panel's text field keeps its Home")
        XCTAssertFalse(
            ControlsMenu.goesToStart(
                keyCode: home, modifiers: [], inMainWindow: true, canPlay: false))
        XCTAssertFalse(
            ControlsMenu.goesToStart(keyCode: 49, modifiers: [], inMainWindow: true, canPlay: true))
    }
}
