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
    let written = String(decoding: try LineCoding.encoder().encode(bars), as: UTF8.self)
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
func playing(_ player: FakePlayer) throws -> (Harness, AppModel) {
    let harness = try Harness()
    harness.preset("volumes", with: gainsReply)
    let model = harness.model(player: player)
    model.launch()
    return (harness, model)
}

/// The `volumes` commands sent so far.
func volumesAsked(_ core: FakeCore) -> [Command] {
    core.sent.filter { $0.name == "volumes" }
}

/// Raised once from any thread (an observation's change).
final class Flag: @unchecked Sendable {
    private let lock = NSLock()
    private var value = false

    var raised: Bool { lock.withLock { value } }

    func raise() { lock.withLock { value = true } }
}
