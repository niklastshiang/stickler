import Foundation
import Testing

@testable import SticklerCore

/// A result's state event; `corrections` changes with a correction, `correcting` does not.
func resultEvent(
    seq: Int, song: String = "/m/e.flac", tempo: String = "normal", correcting: Bool = false
) -> String {
    #"{"event": "state", "seq": \#(seq), "state": {"kind": "result", "song": "\#(song)", "#
        + #""title": "Eye of the Tiger", "subtitle": "Survivor · ♩ = 109 · 4/4", "#
        + #""artist": "Survivor", "seconds": 246.0, "tempo": 109, "meter": [4, 4], "#
        + #""musicxml": "/c/e.musicxml", "corrections": {"tempo": "\#(tempo)", "#
        + #""beats_per_bar": null, "first_downbeat": null, "simplify": true, "repeats": true}, "#
        + #""correcting": \#(correcting), "can_open": true, "can_close": true, "#
        + #""can_export": true}}"#
}

func exportingEvent(seq: Int) -> String {
    #"{"event": "state", "seq": \#(seq), "state": {"kind": "exporting", "song": "/m/e.flac", "#
        + #""title": "Eye of the Tiger", "subtitle": "Survivor", "dest": "/d/e.pdf", "#
        + #""steps": []}}"#
}

/// A `pages` reply with one page whose SVG is `svg`.
func pagesReply(_ svg: String, zoom: Double = 1.0) -> String {
    #""ok": true, "zoom": \#(zoom), "pages": [{"svg": "\#(svg)", "width": 800.0, "#
        + #""height": 252.0, "bars": [{"bar": 1, "x": 1.0, "y": 2.0, "width": 3.0, "#
        + #""height": 4.0}]}]"#
}

func zoomReply(_ zoom: Double, _ percent: String) -> String {
    #""ok": true, "zoom": \#(zoom), "percent": "\#(percent)""#
}

/// The `pages` commands sent so far.
func pagesAsked(_ core: FakeCore) -> [Command] {
    core.sent.filter { $0.name == "pages" }
}

@MainActor
func running(settle: Duration = .milliseconds(300)) throws -> (Harness, AppModel) {
    let harness = try Harness()
    let model = harness.model(settle: settle)
    model.choose(folder: harness.folder)
    return (harness, model)
}

/// A zoom item: what the reader does, the command it sends and the core's answer.
struct ZoomStep {
    let act: @MainActor () -> Void
    let command: Command
    let zoom: Double
    let percent: String
}

@MainActor @Suite struct TheSheet {
    @Test func theNoteSizeComesFromTheSettingsAtStart() async throws {
        let harness = try Harness()
        let model = harness.model()
        #expect(model.sheet.percent == "100%" && model.sheet.zoom == 1.0)
        harness.preset(
            "settings",
            with: #""ok": true, "appearance": "system", "zoom": 1.25, "song_volume": 0.7, "#
                + #""hits_volume": 1.0, "setup_agreed": true, "percent": "125%""#)
        model.choose(folder: harness.folder)
        #expect(await settled { model.sheet.percent == "125%" })
        #expect(model.sheet.zoom == 1.25)
    }

    @Test func theFirstPagesComeAtTheWidthAndTheStoredSize() async throws {
        let (harness, model) = try running()
        harness.core.answer("pages", with: pagesReply("first", zoom: 1.25))
        #expect(!model.sheet.canZoom)
        try harness.core.emit(resultEvent(seq: 1))
        #expect(await settled { model.sheet.canZoom })
        #expect(pagesAsked(harness.core).isEmpty)  // no width yet
        model.sheet.resize(to: 800)  // the first width counts at once
        #expect(await settled { model.sheet.pages.first?.svg == "first" })
        #expect(pagesAsked(harness.core) == [.pages(width: 800, zoom: nil)])
        #expect(model.sheet.zoom == 1.25)
        let bar = BarBox(bar: 1, x: 1, y: 2, width: 3, height: 4)
        #expect(model.sheet.pages.first?.bars.first == bar)
    }

    @Test func aNewSongAndACorrectionAskAgainAnExportDoesNot() async throws {
        let (harness, model) = try running(settle: .milliseconds(20))
        harness.core.answer("pages", with: pagesReply("p"))
        model.sheet.resize(to: 800)
        try harness.core.emit(resultEvent(seq: 1))
        #expect(await settled { pagesAsked(harness.core).count == 1 })
        try harness.core.emit(resultEvent(seq: 2, correcting: true))  // the same music
        try harness.core.emit(exportingEvent(seq: 3))
        try harness.core.emit(resultEvent(seq: 4))
        try await Task.sleep(for: .milliseconds(80))
        #expect(pagesAsked(harness.core).count == 1)
        #expect(model.sheet.pages.count == 1)  // an export keeps the sheet

        try harness.core.emit(resultEvent(seq: 5, tempo: "double"))  // a correction
        #expect(await settled { pagesAsked(harness.core).count == 2 })
        try harness.core.emit(resultEvent(seq: 6, song: "/m/other.flac"))  // another song
        #expect(await settled { pagesAsked(harness.core).count == 3 })
    }

    @Test func aQuickSeriesOfWidthsMakesOneRequestAfterThePause() async throws {
        let (harness, model) = try running(settle: .milliseconds(60))
        harness.core.answer("pages", with: pagesReply("p"))
        try harness.core.emit(resultEvent(seq: 1))
        #expect(await settled { model.sheet.canZoom })
        model.sheet.resize(to: 800)
        #expect(await settled { pagesAsked(harness.core).count == 1 })
        for width in [810.0, 840, 870, 900, 930] {
            model.sheet.resize(to: width)
            try await Task.sleep(for: .milliseconds(10))
        }
        #expect(pagesAsked(harness.core).count == 1)  // still moving
        #expect(await settled { pagesAsked(harness.core).count == 2 })
        try await Task.sleep(for: .milliseconds(150))
        #expect(pagesAsked(harness.core) == [
            .pages(width: 800, zoom: nil), .pages(width: 930, zoom: nil)
        ])
        model.sheet.resize(to: 930)  // the same width asks for nothing
        try await Task.sleep(for: .milliseconds(150))
        #expect(pagesAsked(harness.core).count == 2)
    }

    @Test func eachZoomSendsItsCommandAndAsksForPagesAtTheNewSize() async throws {
        let (harness, model) = try running()
        harness.core.answer("pages", with: pagesReply("p"))
        try harness.core.emit(resultEvent(seq: 1))
        #expect(await settled { model.sheet.canZoom })
        model.sheet.resize(to: 800)
        #expect(await settled { pagesAsked(harness.core).count == 1 })
        let steps: [ZoomStep] = [
            ZoomStep(act: { model.sheet.zoomIn() }, command: .zoomIn, zoom: 1.25, percent: "125%"),
            ZoomStep(act: { model.sheet.zoomOut() }, command: .zoomOut, zoom: 0.8, percent: "80%"),
            ZoomStep(
                act: { model.sheet.actualSize() }, command: .actualSize, zoom: 1, percent: "100%"),
            ZoomStep(
                act: { model.sheet.setZoom(1.5) }, command: .setZoom(1.5), zoom: 1.5,
                percent: "150%")
        ]
        for (index, step) in steps.enumerated() {
            harness.core.answer(step.command.name, with: zoomReply(step.zoom, step.percent))
            // the pages come at the new size, as the core sends them
            harness.core.answer("pages", with: pagesReply("p", zoom: step.zoom))
            step.act()
            #expect(await settled { pagesAsked(harness.core).count == index + 2 })
            #expect(harness.core.sent.contains(step.command))
            #expect(model.sheet.percent == step.percent && model.sheet.zoom == step.zoom)
        }
    }

    @Test func aReplyOvertakenByANewerRequestIsDropped() async throws {
        let (harness, model) = try running()
        harness.core.queue("pages", with: pagesReply("old"), after: .milliseconds(150))
        harness.core.answer("pages", with: pagesReply("new"))
        harness.core.answer("zoom_in", with: zoomReply(1.0, "100%"))
        try harness.core.emit(resultEvent(seq: 1))
        #expect(await settled { model.sheet.canZoom })
        model.sheet.resize(to: 800)  // its reply comes late
        #expect(await settled { pagesAsked(harness.core).count == 1 })
        model.sheet.zoomIn()
        #expect(await settled { model.sheet.pages.first?.svg == "new" })
        try await Task.sleep(for: .milliseconds(250))
        #expect(model.sheet.pages.first?.svg == "new")
    }

    @Test func theOldPagesStayWhileNewOnesComeAndWhenTheyAreRefused() async throws {
        let (harness, model) = try running()
        harness.core.answer("pages", with: pagesReply("old"))
        harness.core.answer("zoom_in", with: zoomReply(1.0, "100%"))
        harness.core.answer("zoom_out", with: zoomReply(1.0, "100%"))
        try harness.core.emit(resultEvent(seq: 1))
        #expect(await settled { model.sheet.canZoom })
        model.sheet.resize(to: 800)
        #expect(await settled { model.sheet.pages.first?.svg == "old" })

        harness.core.queue("pages", with: pagesReply("new"), after: .milliseconds(100))
        model.sheet.zoomIn()
        #expect(await settled { pagesAsked(harness.core).count == 2 })
        #expect(model.sheet.pages.first?.svg == "old")  // no empty page in between
        #expect(await settled { model.sheet.pages.first?.svg == "new" })

        harness.core.answer("pages", with: refusal("Cannot engrave."))
        model.sheet.zoomOut()
        #expect(await settled { model.notice != nil })
        #expect(model.notice == Notice(text: "Cannot engrave.", opens: nil))
        #expect(model.sheet.pages.first?.svg == "new")
    }

    @Test func aRefusedZoomSaysWhyAndAsksForNothing() async throws {
        let (harness, model) = try running()
        try harness.core.emit(resultEvent(seq: 1))
        #expect(await settled { model.sheet.canZoom })
        model.sheet.resize(to: 800)
        #expect(await settled { pagesAsked(harness.core).count == 1 })
        harness.core.answer("zoom_in", with: refusal("Too big."))
        model.sheet.zoomIn()
        #expect(await settled { model.notice?.text == "Too big." })
        #expect(pagesAsked(harness.core).count == 1 && model.sheet.percent == "100%")
    }

    @Test func withoutAResultAZoomIsKeptButNoPagesAreAsked() async throws {
        let (harness, model) = try running()
        harness.core.answer("zoom_in", with: zoomReply(1.25, "125%"))
        model.sheet.resize(to: 800)
        model.sheet.zoomIn()
        #expect(await settled { model.sheet.percent == "125%" })
        #expect(pagesAsked(harness.core).isEmpty && !model.sheet.canZoom)
    }

    @Test func anotherScreenEmptiesTheSheet() async throws {
        let (harness, model) = try running()
        harness.core.answer("pages", with: pagesReply("p"))
        try harness.core.emit(resultEvent(seq: 1))
        model.sheet.resize(to: 800)
        #expect(await settled { !model.sheet.pages.isEmpty })
        try harness.core.emit(#"{"event": "state", "seq": 2, "state": \#(analysing)}"#)
        #expect(await settled { model.sheet.pages.isEmpty })
        #expect(!model.sheet.canZoom)
        try harness.core.emit(resultEvent(seq: 3))  // the same song again asks again
        #expect(await settled { pagesAsked(harness.core).count == 2 })
    }

    @Test func aNewCoreStartsWithAnEmptySheetAndDropsTheOldReplies() async throws {
        let (harness, model) = try running()
        let first = harness.core
        first.queue("pages", with: pagesReply("old"), after: .milliseconds(100))
        try first.emit(resultEvent(seq: 1))
        #expect(await settled { model.sheet.canZoom })
        model.sheet.resize(to: 800)
        #expect(await settled { pagesAsked(first).count == 1 })
        model.startAgain()
        #expect(!model.sheet.canZoom && model.sheet.pages.isEmpty)
        try await Task.sleep(for: .milliseconds(200))
        #expect(model.sheet.pages.isEmpty)  // the old core's reply is not shown
        #expect(await settled { harness.core.sent.contains(.settings) })
    }

    @Test func withoutACoreTheSheetSendsNothing() async throws {
        let model = try Harness().model()
        model.sheet.resize(to: 800)
        model.sheet.zoomIn()
        try await Task.sleep(for: .milliseconds(50))
        #expect(model.sheet.pages.isEmpty && model.sheet.percent == "100%")
    }
}

@MainActor @Suite struct ThePinch {
    @Test func aPinchGivesOneScaleWhenTheFingersLift() {
        var pinch = Pinch()
        pinch.begin()
        pinch.change(by: 0.25)
        pinch.change(by: 0.6)
        #expect(pinch.end() == 2.0)  // 1.25 × 1.6
        #expect(pinch.end() == nil)  // told once
    }

    @Test func aPinchThatChangesNothingOrWasNeverBegunGivesNoScale() {
        var pinch = Pinch()
        pinch.change(by: 0.5)  // a change without a beginning
        #expect(pinch.end() == nil)
        pinch.begin()
        #expect(pinch.end() == nil)  // the fingers did not move
        pinch.begin()
        pinch.change(by: -1.5)  // nothing can be shown at a negative size
        #expect(pinch.end() == nil)
    }

    @Test func aCancelledPinchGivesNoScaleAndTheNextOneStartsAfresh() {
        var pinch = Pinch()
        pinch.begin()
        pinch.change(by: 0.5)
        pinch.cancel()
        #expect(pinch.end() == nil)
        pinch.begin()
        pinch.change(by: -0.5)
        #expect(pinch.end() == 0.5)
    }

    @Test func aPinchSetsTheNoteSizeItBeganAtTimesItsScale() async throws {
        let (harness, model) = try running()
        harness.core.answer("zoom_in", with: zoomReply(1.25, "125%"))
        harness.core.answer("set_zoom", with: zoomReply(2.5, "250%"))
        try harness.core.emit(resultEvent(seq: 1))
        #expect(await settled { model.sheet.canZoom })
        model.sheet.zoomIn()
        #expect(await settled { model.sheet.zoom == 1.25 })
        model.sheet.pinched(by: 2.0)
        #expect(await settled { model.sheet.percent == "250%" })
        #expect(harness.core.sent.filter { $0.name == "set_zoom" } == [.setZoom(2.5)])
    }
}
