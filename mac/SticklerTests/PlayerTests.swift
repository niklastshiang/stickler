import AVFoundation
import SticklerCore
import XCTest

@testable import Stickler

/// The player on a real AVAudioEngine in offline rendering (SPEC.md "Mac playback", scope 3):
/// no sound device, every sample of what it would play is read back.
@MainActor
final class PlayerTests: XCTestCase {
    static let rate = 44100.0
    var folder: URL?
    var engine = AVAudioEngine()

    override func setUp() async throws {
        let made = FileManager.default.temporaryDirectory
            .appendingPathComponent("player-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: made, withIntermediateDirectories: true)
        folder = made
        engine = AVAudioEngine()
        let output = try XCTUnwrap(
            AVAudioFormat(standardFormatWithSampleRate: Self.rate, channels: 2))
        try engine.enableManualRenderingMode(.offline, format: output, maximumFrameCount: 4096)
    }

    override func tearDown() async throws {
        if let folder {
            try? FileManager.default.removeItem(at: folder)
        }
    }

    /// A mono WAV of `seconds` that is silent but for impulses of 0.5 at `frames`.
    func impulses(_ name: String, seconds: Double = 1, at frames: [Int]) throws -> URL {
        let url = try XCTUnwrap(folder).appendingPathComponent(name)
        let format = try XCTUnwrap(
            AVAudioFormat(standardFormatWithSampleRate: Self.rate, channels: 1))
        let file = try AVAudioFile(forWriting: url, settings: format.settings)
        let count = AVAudioFrameCount(seconds * Self.rate)
        let buffer = try XCTUnwrap(AVAudioPCMBuffer(pcmFormat: format, frameCapacity: count))
        buffer.frameLength = count
        let samples = try XCTUnwrap(buffer.floatChannelData)[0]
        for frame in frames {
            samples[frame] = 0.5
        }
        try file.write(from: buffer)
        return url
    }

    /// The next `frames` of the left channel.
    func render(_ frames: Int) throws -> [Float] {
        let buffer = try XCTUnwrap(
            AVAudioPCMBuffer(pcmFormat: engine.manualRenderingFormat, frameCapacity: 4096))
        var out: [Float] = []
        while out.count < frames {
            let want = AVAudioFrameCount(min(4096, frames - out.count))
            XCTAssertEqual(try engine.renderOffline(want, to: buffer), .success)
            let left = try XCTUnwrap(buffer.floatChannelData)[0]
            out += UnsafeBufferPointer(start: left, count: Int(buffer.frameLength))
        }
        return out
    }

    /// Where the rendered samples are loud, and how loud (a mono source sits at -3 dB in
    /// each channel of the stereo mix).
    func peaks(_ samples: [Float]) -> [Int: Float] {
        var found: [Int: Float] = [:]
        for (frame, value) in samples.enumerated() where abs(value) > 0.05 {
            found[frame] = (value * 1000).rounded() / 1000
        }
        return found
    }

    func loaded(gains: Gains = Gains(song: 1, hits: 1)) throws -> Player {
        let player = Player(engine: engine)
        try player.load(
            song: try impulses("song.wav", at: [1000, 30000]),
            clicks: try impulses("clicks.wav", at: [1000, 30000]))
        player.setGains(gains)
        return player
    }

    func testBothSourcesStartOnTheSameFrame() throws {
        let player = try loaded()
        XCTAssertEqual(player.length, 1)
        try player.play()
        XCTAssertEqual(peaks(try render(4410)), [1000: 0.707])  // one impulse, both at once
        XCTAssertEqual(player.position, 0.1, accuracy: 0.001)
    }

    func testASeekLandsOnItsFrameAndTheGainsMuteASource() throws {
        let player = try loaded(gains: Gains(song: 0, hits: 1))
        player.seek(to: 0.5)  // before playing: it starts there
        XCTAssertEqual(player.position, 0.5)
        try player.play()
        XCTAssertEqual(peaks(try render(10000)), [30000 - 22050: 0.354])  // the clicks alone
        player.seek(to: 0)  // while playing
        player.setGains(Gains(song: 1, hits: 0))
        XCTAssertEqual(peaks(try render(2000)), [1000: 0.354])  // the song alone
        player.seek(to: -1)
        XCTAssertEqual(player.position, 0)
        player.seek(to: 9)
        XCTAssertEqual(player.position, 1)
    }

    func testPauseHoldsThePlaceAndPlayGoesOnFromIt() throws {
        let player = try loaded()
        try player.play()
        try player.play()  // a second play changes nothing
        _ = try render(22050)
        player.pause()
        player.pause()
        XCTAssertEqual(player.position, 0.5, accuracy: 0.001)
        try player.play()
        XCTAssertEqual(peaks(try render(10000)), [30000 - 22050: 0.707])
    }

    func testTheEndIsToldOnceAndStopLetsGo() async throws {
        let player = try loaded()
        var told: [PlayerPause] = []
        player.paused = { told.append($0) }
        try player.play()
        _ = try render(48000)
        for _ in 0..<100 where told.isEmpty {
            try await Task.sleep(for: .milliseconds(10))
        }
        XCTAssertEqual(told, [.ended])
        XCTAssertEqual(player.position, 1)
        player.stop()
        XCTAssertFalse(engine.isRunning)
        XCTAssertEqual(player.length, 0)
        XCTAssertEqual(player.position, 0)
        try player.play()  // nothing loaded: nothing plays
        XCTAssertFalse(engine.isRunning)
    }

    func testPlayingFromTheEndEndsAtOnce() throws {
        let player = try loaded()
        var told: [PlayerPause] = []
        player.paused = { told.append($0) }
        player.seek(to: 1)
        try player.play()
        XCTAssertEqual(told, [.ended])
    }

    func testAChangedOutputPausesWhereItWas() async throws {
        let player = try loaded()
        var told: [PlayerPause] = []
        player.paused = { told.append($0) }
        NotificationCenter.default.post(name: .AVAudioEngineConfigurationChange, object: engine)
        try await Task.sleep(for: .milliseconds(50))
        XCTAssertEqual(told, [])  // not playing: nothing to pause
        try player.play()
        _ = try render(4410)
        NotificationCenter.default.post(name: .AVAudioEngineConfigurationChange, object: engine)
        for _ in 0..<100 where told.isEmpty {
            try await Task.sleep(for: .milliseconds(10))
        }
        XCTAssertEqual(told, [.interrupted])
        XCTAssertEqual(player.position, 0.1, accuracy: 0.001)
    }

    func testASongTheSystemCannotReadIsUnreadableAndClicksItCannotAreLeftOut() throws {
        let player = Player(engine: engine)
        let text = try XCTUnwrap(folder).appendingPathComponent("song.txt")
        try Data("not a sound".utf8).write(to: text)
        XCTAssertThrowsError(try player.load(song: text, clicks: nil)) { error in
            XCTAssertEqual(error as? PlayerError, .unreadable)
        }
        try player.load(song: try impulses("song.wav", at: [1000]), clicks: text)
        try player.play()
        XCTAssertEqual(peaks(try render(2000)), [1000: 0.354])  // the song alone
    }

    func testTheReaderIsToldWhyTheSoundCannotStart() {
        let error = NSError(
            domain: "test", code: 1, userInfo: [NSLocalizedDescriptionKey: "No output device."])
        XCTAssertEqual(
            Player.cannotPlay(error), "The song cannot be played: No output device.")
    }
}
