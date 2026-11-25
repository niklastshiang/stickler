import Foundation
import Testing

@testable import SticklerCore

let resultLine = #"{"event": "state", "seq": 2, "state": {"kind": "result", "song": "/m/e.flac", "#
    + #""title": "Eye of the Tiger", "subtitle": "Survivor · ♩ = 109 · 4/4", "#
    + #""artist": "Survivor", "#
    + #""seconds": 246.0, "tempo": 109, "meter": [4, 4], "musicxml": "/c/e.musicxml", "#
    + #""corrections": {"tempo": "normal", "beats_per_bar": null, "first_downbeat": null, "#
    + #""simplify": true, "repeats": true}, "correcting": false, "can_open": true, "#
    + #""can_close": true, "can_export": true}}"#

@MainActor @Suite struct Scripted {
    func model(
        _ lines: [String], replies: [String: String] = [:]
    ) throws -> (AppModel, ScriptedCore) {
        let harness = try Harness()
        let core = ScriptedCore(lines: lines, replies: replies)
        let model = AppModel(defaults: harness.defaults) { _ in core }
        model.launch()
        return (model, core)
    }

    @Test func itsLinesBecomeTheWindowsStateAndTitle() async throws {
        let (model, core) = try model([
            #"{"event": "hello", "protocol": 1, "version": "8", "language": "en"}"#,
            "not a line",  // skipped
            resultLine
        ])
        #expect(await settled { model.state.screen.kind == "result" })
        #expect(model.title == "Eye of the Tiger" && model.subtitle == "Survivor · ♩ = 109 · 4/4")
        #expect(await settled { core.sent.filter { $0 != .settings } == [.start] })
        await core.quit(seconds: 3)
    }

    @Test func itsRepliesAreAsSet() async throws {
        let (model, _) = try model([], replies: ["a4_pages": refusal("No.")])
        #expect(await model.a4Pages() == nil && model.notice?.text == "No.")
        #expect(await model.drumTrackCost() == nil)  // `ok` alone has no cost
    }

    @Test func theTitleFollowsTheScreen() async throws {
        let analysingLine = #"{"event": "state", "seq": 1, "state": \#(analysing)}"#
        let failed = #"{"event": "state", "seq": 1, "state": {"kind": "failed", "#
            + #""song": "/m/b.flac", "name": "b", "reason": "analysis", "title": "T", "#
            + #""description": "D", "details": "x", "#
            + #""can_open": true}}"#
        let exporting = #"{"event": "state", "seq": 1, "state": {"kind": "exporting", "#
            + #""song": "/m/e.flac", "title": "E", "subtitle": "S", "dest": "/d/e.flac", "#
            + #""steps": []}}"#
        for (line, title, subtitle) in [
            (analysingLine, "a", ""), (failed, "b", ""), (exporting, "E", "S"),
            (#"{"event": "state", "seq": 1, "state": \#(emptyState)}"#, "Stickler", "")
        ] {
            let (model, _) = try model([line])
            #expect(await settled { model.state.screen != .empty || title == "Stickler" })
            #expect(model.title == title && model.subtitle == subtitle, "\(line)")
        }
    }

    @Test func clearingTheRecentMenuForgetsEverySong() async throws {
        let rows = #"[{"path": "/m/a.flac", "title": "A", "detail": "", "missing": false}, "#
            + #"{"path": "/m/b.flac", "title": "B", "detail": "", "missing": true}]"#
        let (model, core) = try model([#"{"event": "recent", "seq": 1, "rows": \#(rows)}"#])
        #expect(await settled { model.recent.count == 2 })
        model.clearRecent()
        #expect(await settled { core.sent.count == 5 })  // with `start` and two `settings`
        #expect(core.sent.contains(.forgetRecent(path: "/m/a.flac")))
        #expect(core.sent.contains(.forgetRecent(path: "/m/b.flac")))
    }
}
