import Foundation
import Testing

@testable import SticklerCore

/// Playback at its edges, found by the review of task 167: the end, quick presses, a play
/// called off, a copy that cannot be read, a slider moved before the stored volumes came.
@MainActor @Suite struct PlaybackEdges {
    @Test func playingFromTheEndEndsAtOnceAndPlayStartsAgainAtTheBeginning() async throws {
        let player = FakePlayer()
        let (harness, model) = try playing(player)
        try harness.core.emit(try playingResult(seq: 1))
        #expect(await settled { model.playback.canPlay })
        model.playback.seek(to: 12)  // the slider at its end
        player.endsAtOnce = true
        model.playback.toggle()
        #expect(await settled { player.loads.count == 1 })
        try await Task.sleep(for: .milliseconds(30))
        #expect(!model.playback.playing, "nothing was left to play")
        player.endsAtOnce = false
        model.playback.toggle()
        #expect(await settled { model.playback.playing })
        #expect(player.seeks.last == 0)
    }

    @Test func quickArrowsGoAsManyBarsOn() async throws {
        let player = FakePlayer()
        let (harness, model) = try playing(player)
        try harness.core.emit(try playingResult(seq: 1))
        #expect(await settled { model.playback.canPlay })
        harness.core.queue("step", with: #""ok": true, "seconds": 2.0"#, after: .milliseconds(40))
        harness.core.queue("step", with: #""ok": true, "seconds": 4.0"#)
        model.playback.nextBar()
        model.playback.nextBar()  // before the first answer came
        #expect(await settled { model.playback.position == 4 })
        #expect(
            harness.core.sent.filter { $0.name == "step" }
                == [.step(from: 0, count: 1), .step(from: 2, count: 1)])
    }

    @Test func aSecondPressCallsOffAPlayThatWaits() async throws {
        let player = FakePlayer()
        player.unreadable = ["/m/e.ogg"]
        let (harness, model) = try playing(player)
        harness.core.queue(
            "playable", with: #""ok": true, "path": "/c/e.flac""#, after: .milliseconds(60))
        try harness.core.emit(try playingResult(seq: 1, song: "/m/e.ogg"))
        #expect(await settled { model.playback.canPlay })
        model.playback.toggle()
        #expect(await settled { harness.core.sent.contains(.playable) })
        model.playback.toggle()  // the copy is still being made
        try await Task.sleep(for: .milliseconds(150))
        #expect(!model.playback.playing && !player.isPlaying)
        model.playback.toggle()  // the copy is loaded now: it plays at once
        #expect(await settled { model.playback.playing })
    }

    @Test func aCopyThePlayerCannotReadEitherSaysWhy() async throws {
        let player = FakePlayer()
        player.unreadable = ["/m/e.ogg", "/c/e.flac"]
        let (harness, model) = try playing(player)
        harness.core.answer("playable", with: #""ok": true, "path": "/c/e.flac""#)
        try harness.core.emit(try playingResult(seq: 1, song: "/m/e.ogg"))
        #expect(await settled { model.playback.canPlay })
        model.playback.toggle()
        #expect(await settled { model.notice?.text == "Cannot read e.flac." })
        #expect(!model.playback.playing)
    }

    @Test func aSliderMovedBeforeTheStoredVolumesCameIsKept() async throws {
        let harness = try Harness()
        harness.preset("volumes", with: gainsReply)
        harness.preset(
            "settings",
            with: #""ok": true, "appearance": "system", "zoom": 1.0, "song_volume": 0.4, "#
                + #""hits_volume": 0.9, "setup_agreed": true, "percent": "100%""#,
            after: .milliseconds(60))
        let model = harness.model(player: FakePlayer())
        model.launch()
        model.playback.setSongVolume(0.2)
        try await Task.sleep(for: .milliseconds(150))
        #expect(model.playback.songVolume == 0.2)
        #expect(model.playback.hitsVolume == 1.0)
    }
}
