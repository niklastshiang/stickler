import Foundation
import Testing

@testable import SticklerCore

/// A player that records what it is told; the test moves its position and pauses it.
@MainActor
final class FakePlayer: Playing {
    var loads: [(song: String, clicks: String?)] = []
    var unreadable: Set<String> = []
    var loadFailure: PlayerError?
    var playFailure: PlayerError?
    var isPlaying = false
    var position = 0.0
    var seeks: [Double] = []
    var gains: [Gains] = []
    var stops = 0
    var paused: (@MainActor (PlayerPause) -> Void)?

    func load(song: URL, clicks: URL?) throws {
        if unreadable.contains(song.path) { throw PlayerError.unreadable }
        if let loadFailure { throw loadFailure }
        loads.append((song.path, clicks?.path))
        position = 0
    }

    func play() throws {
        if let playFailure { throw playFailure }
        isPlaying = true
    }

    func pause() { isPlaying = false }

    func seek(to seconds: Double) {
        seeks.append(seconds)
        position = seconds
    }

    func setGains(_ gains: Gains) { self.gains.append(gains) }

    func stop() {
        stops += 1
        isPlaying = false
    }

    /// The player pauses by itself.
    func pauses(_ why: PlayerPause) {
        isPlaying = false
        paused?(why)
    }
}

/// A result whose song plays: the bars above, 12 s, clicks unless `clicks` is nil.
func playingResult(
    seq: Int, song: String = "/m/e.flac", clicks: String? = "/c/e.wav",
    bars: [SongBar] = songBars, kind: String = "result"
) throws -> String {
    let written = try #require(String(bytes: LineCoding.encoder().encode(bars), encoding: .utf8))
    let named = clicks.map { "\"\($0)\"" } ?? "null"
    return #"{"event": "state", "seq": \#(seq), "state": {"kind": "\#(kind)", "#
        + #""song": "\#(song)", "title": "E", "subtitle": "S", "artist": "", "#
        + #""seconds": 12.0, "tempo": 109, "meter": [4, 4], "musicxml": "/c/e.musicxml", "#
        + #""corrections": {"tempo": "normal", "beats_per_bar": null, "first_downbeat": null, "#
        + #""simplify": true, "repeats": true}, "correcting": false, "clicks": \#(named), "#
        + #""bars": \#(written), "can_open": true, "can_close": true, "can_export": true}}"#
}

let gainsReply = #""ok": true, "song": 0.7, "hits": 1.0"#

@MainActor
func playing(_ player: FakePlayer = FakePlayer()) throws -> (Harness, AppModel, FakePlayer) {
    let harness = try Harness()
    harness.preset("volumes", with: gainsReply)
    let model = harness.model(player: player)
    model.launch()
    return (harness, model, player)
}

/// The `volumes` commands sent so far.
func volumesAsked(_ core: FakeCore) -> [Command] {
    core.sent.filter { $0.name == "volumes" }
}

@MainActor @Suite struct Playback {
    @Test func withoutAResultOrAPlayerNothingPlays() async throws {
        let (harness, model, player) = try playing()
        #expect(!model.playback.canPlay)
        model.playback.toggle()
        model.playback.nextBar()
        model.playback.jump(toBar: 2)
        model.playback.goToStart()
        model.playback.seek(to: 3)
        #expect(await settled { harness.core.sent.contains(.settings) })
        #expect(player.loads.isEmpty && model.playback.position == 0)
        #expect(harness.core.actions == [.start])
        #expect(model.playback.label == "" && model.playback.marked == nil)

        let silent = try Harness()
        let quiet = silent.model()
        quiet.launch()
        try silent.core.emit(try playingResult(seq: 1))
        #expect(await settled { quiet.playback.length == 12 })
        #expect(!quiet.playback.canPlay)  // no player
    }

    @Test func theStoredVolumesComeWithTheCore() async throws {
        let harness = try Harness()
        harness.preset(
            "settings",
            with: #""ok": true, "appearance": "system", "zoom": 1.0, "song_volume": 0.4, "#
                + #""hits_volume": 0.9, "setup_agreed": true, "percent": "100%""#)
        let model = harness.model(player: FakePlayer())
        model.launch()
        #expect(await settled { model.playback.songVolume == 0.4 })
        #expect(model.playback.hitsVolume == 0.9)
    }

    @Test func aResultIsReadyAtItsStart() async throws {
        let (harness, model, player) = try playing()
        try harness.core.emit(try playingResult(seq: 1))
        #expect(await settled { model.playback.canPlay })
        #expect(model.playback.length == 12 && model.playback.lengthText == "0:12")
        #expect(model.playback.time == "0:00" && model.playback.label == "Bar 1 of 6")
        #expect(model.playback.marked == 1 && model.playback.bars == songBars)
        #expect(!model.playback.playing && player.loads.isEmpty)  // loaded on the first play
    }

    @Test func playLoadsBothSourcesAtTheCoresGainsAndFollowsThePosition() async throws {
        let (harness, model, player) = try playing()
        try harness.core.emit(try playingResult(seq: 1))
        #expect(await settled { model.playback.canPlay })
        model.playback.toggle()
        #expect(await settled { model.playback.playing })
        #expect(player.loads.map(\.song) == ["/m/e.flac"] && player.loads[0].clicks == "/c/e.wav")
        #expect(volumesAsked(harness.core) == [.volumes(hear: .both, song: nil, hits: nil)])
        #expect(player.gains == [Gains(song: 0.7, hits: 1.0)])
        #expect(player.isPlaying && player.seeks == [0])
        player.position = 5
        #expect(await settled { model.playback.position == 5 })
        #expect(model.playback.label == "Bar 3 of 6" && model.playback.marked == 1)
        #expect(model.playback.time == "0:05")

        model.playback.toggle()  // pause
        #expect(!model.playback.playing && !player.isPlaying && model.playback.position == 5)
        player.position = 7  // a tick after the pause changes nothing
        try await Task.sleep(for: .milliseconds(30))
        #expect(model.playback.position == 5)
        model.playback.toggle()  // on from where it paused, nothing loaded again
        #expect(await settled { model.playback.playing })
        #expect(player.loads.count == 1 && player.seeks.last == 5)
        #expect(volumesAsked(harness.core).count == 1)
    }

    @Test func aSongWithoutClicksPlaysAlone() async throws {
        let (harness, model, player) = try playing()
        try harness.core.emit(try playingResult(seq: 1, clicks: nil))
        #expect(await settled { model.playback.canPlay })
        model.playback.toggle()
        #expect(await settled { model.playback.playing })
        #expect(player.loads[0].clicks == nil)
    }

    @Test func theArrowsAndABarClickGoWhereTheCoreSays() async throws {
        let (harness, model, player) = try playing()
        try harness.core.emit(try playingResult(seq: 1))
        #expect(await settled { model.playback.canPlay })
        model.playback.seek(to: 5)
        harness.core.answer("step", with: #""ok": true, "seconds": 2.0"#)
        model.playback.previousBar()
        #expect(await settled { model.playback.position == 2 })
        model.playback.nextBar()
        #expect(await settled { harness.core.sent.filter { $0.name == "step" }.count == 2 })
        #expect(
            harness.core.sent.filter { $0.name == "step" }
                == [.step(at: 5, by: -1), .step(at: 2, by: 1)])

        harness.core.answer("jump", with: #""ok": true, "seconds": 8.0"#)
        model.playback.jump(toBar: 3)  // stopped: the position moves, nothing plays
        #expect(await settled { model.playback.position == 8 })
        #expect(harness.core.sent.contains(.jump(bar: 3, at: 2)))
        #expect(!model.playback.playing && player.loads.isEmpty)

        harness.core.answer("jump", with: #""ok": true, "seconds": null"#)
        model.playback.jump(toBar: 9)  // never played: nowhere to go
        #expect(await settled { harness.core.sent.contains(.jump(bar: 9, at: 8)) })
        try await Task.sleep(for: .milliseconds(20))
        #expect(model.playback.position == 8)

        model.playback.goToStart()
        #expect(model.playback.position == 0)
        model.playback.seek(to: 99)  // kept inside the song
        #expect(model.playback.position == 12)
        model.playback.seek(to: -3)
        #expect(model.playback.position == 0)
    }

    @Test func whilePlayingTheArrowsAskFromThePlayersPosition() async throws {
        let (harness, model, player) = try playing()
        try harness.core.emit(try playingResult(seq: 1))
        #expect(await settled { model.playback.canPlay })
        model.playback.toggle()
        #expect(await settled { model.playback.playing })
        player.position = 6.5
        harness.core.answer("step", with: #""ok": true, "seconds": 8.0"#)
        model.playback.nextBar()
        #expect(await settled { player.seeks.last == 8 })
        #expect(harness.core.sent.contains(.step(at: 6.5, by: 1)))
    }

    @Test func aRefusedCommandSaysWhy() async throws {
        let (harness, model, _) = try playing()
        try harness.core.emit(try playingResult(seq: 1))
        #expect(await settled { model.playback.canPlay })
        harness.core.answer("step", with: refusal("Not now."))
        model.playback.nextBar()
        #expect(await settled { model.notice?.text == "Not now." })
        harness.core.answer("volumes", with: refusal("No volumes."))
        model.playback.setHear(.song)
        #expect(await settled { model.notice?.text == "No volumes." })
        harness.preset("settings", with: refusal("No settings."))
        model.startAgain()
        #expect(await settled { model.notice?.text == "No settings." })
    }

    @Test func theEndStopsAndPlayStartsAgainAtTheBeginning() async throws {
        let (harness, model, player) = try playing()
        try harness.core.emit(try playingResult(seq: 1))
        #expect(await settled { model.playback.canPlay })
        model.playback.toggle()
        #expect(await settled { model.playback.playing })
        player.position = 12
        player.pauses(.ended)
        #expect(!model.playback.playing && model.playback.position == 12)
        model.playback.toggle()
        #expect(await settled { model.playback.playing })
        #expect(player.seeks.last == 0 && model.playback.position == 0)
    }

    @Test func anOutputThatChangedPausesWhereItWas() async throws {
        let (harness, model, player) = try playing()
        try harness.core.emit(try playingResult(seq: 1))
        #expect(await settled { model.playback.canPlay })
        model.playback.toggle()
        #expect(await settled { model.playback.playing })
        player.position = 3
        player.pauses(.interrupted)
        #expect(!model.playback.playing && model.playback.position == 3)
        model.playback.toggle()
        #expect(await settled { model.playback.playing })
        #expect(player.seeks.last == 3)
    }

    @Test func aNewSongCloseAndAStoppedCoreStopTheSound() async throws {
        let (harness, model, player) = try playing()
        try harness.core.emit(try playingResult(seq: 1))
        #expect(await settled { model.playback.canPlay })
        model.playback.toggle()
        #expect(await settled { model.playback.playing })
        player.position = 4

        // a correction of the same song goes on with its new bars
        let corrected = Array(songBars.prefix(3))
        try harness.core.emit(try playingResult(seq: 2, bars: corrected))
        #expect(await settled { model.playback.bars == corrected })
        #expect(model.playback.playing && player.stops == 0)

        try harness.core.emit(try playingResult(seq: 3, song: "/m/other.flac"))
        #expect(await settled { player.stops == 1 })
        #expect(!model.playback.playing && model.playback.position == 0)
        model.playback.toggle()
        #expect(await settled { model.playback.playing })
        #expect(player.loads.last?.song == "/m/other.flac")

        try harness.core.emit(#"{"event": "state", "seq": 4, "state": \#(emptyState)}"#)
        #expect(await settled { player.stops == 2 })
        #expect(!model.playback.playing && !model.playback.canPlay)

        try harness.core.emit(try playingResult(seq: 5))
        #expect(await settled { model.playback.canPlay })
        model.playback.toggle()
        #expect(await settled { model.playback.playing })
        harness.core.stop(CoreEnd(reason: .signalled(9), details: []))
        #expect(await settled { player.stops == 3 })
        #expect(!model.playback.playing && !model.playback.canPlay)
    }

    @Test func anExportPausesAndHidesTheControls() async throws {
        let (harness, model, player) = try playing()
        try harness.core.emit(try playingResult(seq: 1))
        #expect(await settled { model.playback.canPlay })
        model.playback.toggle()
        #expect(await settled { model.playback.playing })
        try harness.core.emit(exportingEvent(seq: 2))
        #expect(await settled { !model.playback.canPlay })
        #expect(!model.playback.playing && !player.isPlaying && player.stops == 0)
        try harness.core.emit(try playingResult(seq: 3))  // back: the song is still loaded
        #expect(await settled { model.playback.canPlay })
        model.playback.toggle()
        #expect(await settled { model.playback.playing })
        #expect(player.loads.count == 1)
    }

}

/// What the core decides for playback: a copy of the song, the gains.
@MainActor @Suite struct PlaybackAndTheCore {
    @Test func aSongTheSystemCannotReadPlaysFromTheCoresCopy() async throws {
        let player = FakePlayer()
        player.unreadable = ["/m/e.ogg"]
        let (harness, model, _) = try playing(player)
        harness.core.answer("playable", with: #""ok": true, "path": "/c/e.flac""#)
        try harness.core.emit(try playingResult(seq: 1, song: "/m/e.ogg"))
        #expect(await settled { model.playback.canPlay })
        model.playback.toggle()
        #expect(await settled { model.playback.playing })
        #expect(player.loads.map(\.song) == ["/c/e.flac"])
        #expect(harness.core.sent.contains(.playable))
    }

    @Test func aSongThatPlaysNowhereSaysWhy() async throws {
        let player = FakePlayer()
        player.unreadable = ["/m/e.ogg"]
        let (harness, model, _) = try playing(player)
        harness.core.answer("playable", with: refusal("“e.ogg” cannot be played."))
        try harness.core.emit(try playingResult(seq: 1, song: "/m/e.ogg"))
        #expect(await settled { model.playback.canPlay })
        model.playback.toggle()
        #expect(await settled { model.notice?.text == "“e.ogg” cannot be played." })
        #expect(!model.playback.playing)

        player.unreadable = []
        player.loadFailure = .failed(message: "No sound device.")
        model.playback.toggle()
        #expect(await settled { model.notice?.text == "No sound device." })
        #expect(!model.playback.playing)

        player.loadFailure = nil
        player.playFailure = .failed(message: "The output is busy.")
        model.playback.toggle()
        #expect(await settled { model.notice?.text == "The output is busy." })
        #expect(!model.playback.playing)
    }

    @Test func whatToHearAndTheVolumesAreTheCoresGains() async throws {
        let (harness, model, player) = try playing()
        try harness.core.emit(try playingResult(seq: 1))
        #expect(await settled { model.playback.canPlay })
        model.playback.toggle()
        #expect(await settled { model.playback.playing })

        harness.core.answer("volumes", with: #""ok": true, "song": 0.0, "hits": 1.0"#)
        model.playback.setHear(.hits)
        #expect(model.playback.hear == .hits)
        #expect(await settled { player.gains.last == Gains(song: 0, hits: 1) })
        harness.core.answer("volumes", with: #""ok": true, "song": 0.0, "hits": 0.5"#)
        model.playback.setHitsVolume(0.5)
        #expect(model.playback.hitsVolume == 0.5)
        #expect(await settled { player.gains.last == Gains(song: 0, hits: 0.5) })
        model.playback.setSongVolume(0.3)
        #expect(model.playback.songVolume == 0.3)
        #expect(await settled { volumesAsked(harness.core).count == 4 })
        #expect(
            Array(volumesAsked(harness.core).dropFirst())
                == [
                    .volumes(hear: .hits, song: nil, hits: nil),
                    .volumes(hear: .hits, song: nil, hits: 0.5),
                    .volumes(hear: .hits, song: 0.3, hits: nil)
                ])
    }

    @Test func anAnswerANewerChangeOvertookIsDropped() async throws {
        let (harness, model, player) = try playing()
        try harness.core.emit(try playingResult(seq: 1))
        #expect(await settled { model.playback.canPlay })
        model.playback.toggle()
        #expect(await settled { model.playback.playing })
        harness.core.queue(
            "volumes", with: #""ok": true, "song": 0.1, "hits": 0.1"#, after: .milliseconds(80))
        harness.core.queue("volumes", with: #""ok": true, "song": 0.2, "hits": 0.2"#)
        model.playback.setSongVolume(0.1)
        model.playback.setSongVolume(0.2)
        #expect(await settled { player.gains.last == Gains(song: 0.2, hits: 0.2) })
        try await Task.sleep(for: .milliseconds(150))
        #expect(player.gains.last == Gains(song: 0.2, hits: 0.2))
    }

    @Test func theVolumesBeforeAPlayAreUsedWhenItLoads() async throws {
        let (harness, model, player) = try playing()
        try harness.core.emit(try playingResult(seq: 1))
        #expect(await settled { model.playback.canPlay })
        harness.core.answer("volumes", with: #""ok": true, "song": 0.3, "hits": 1.0"#)
        model.playback.setSongVolume(0.3)
        #expect(await settled { volumesAsked(harness.core).count == 1 })
        model.playback.toggle()
        #expect(await settled { model.playback.playing })
        #expect(player.gains == [Gains(song: 0.3, hits: 1.0)])
        #expect(volumesAsked(harness.core).count == 1)  // the gains were known
    }
}
