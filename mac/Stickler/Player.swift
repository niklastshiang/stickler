import AVFoundation
import SticklerCore

/// The song and its clicks on one AVAudioEngine (SPEC.md "Mac playback", scope 3; GTK's
/// `ui/player.py`): two player nodes into the engine's mixer, scheduled from the same place and
/// started at the same time, so they share one clock as GStreamer's one pipeline does. Each
/// node's volume changes what is heard at once. Stopped, the engine is stopped too and holds
/// no sound device. The tests run it in the engine's offline rendering, without a device.
@MainActor
final class Player: Playing {
    var paused: (@MainActor (PlayerPause) -> Void)?

    private let engine: AVAudioEngine
    private let songNode = AVAudioPlayerNode()
    private let clicksNode = AVAudioPlayerNode()
    private var song: AVAudioFile?
    private var clicks: AVAudioFile?
    private var gains = Gains(song: 1, hits: 1)
    /// Where the scheduled segments start, in seconds of the song; the position while paused.
    private var from = 0.0
    private var playing = false
    /// Raised whenever the nodes are stopped: their completions from before are ignored.
    private var generation = 0
    private var changes: (any NSObjectProtocol)?
    /// How long after `play` both nodes start, so the second is scheduled before the first
    /// begins (a real device only; offline both start at the next render).
    static let lead = 0.05

    init(engine: AVAudioEngine = AVAudioEngine()) {
        self.engine = engine
        engine.attach(songNode)
        engine.attach(clicksNode)
        // the output changed (headphones unplugged, another device): the engine has stopped
        changes = NotificationCenter.default.addObserver(
            forName: .AVAudioEngineConfigurationChange, object: engine, queue: .main
        ) { [weak self] _ in
            MainActor.assumeIsolated { self?.outputChanged() }
        }
    }

    /// The song's length in seconds; 0 without one.
    var length: Double {
        guard let song else { return 0 }
        return Double(song.length) / song.processingFormat.sampleRate
    }

    /// Opens both files, stopped at 0. A song the system cannot read is `unreadable` (the core
    /// then decodes a copy); clicks it cannot read are left out, the song plays alone.
    func load(song url: URL, clicks clicksURL: URL?) throws {
        stop()
        do {
            song = try AVAudioFile(forReading: url)
        } catch {
            throw PlayerError.unreadable
        }
        clicks = clicksURL.flatMap { try? AVAudioFile(forReading: $0) }
        if let song {
            engine.connect(songNode, to: engine.mainMixerNode, format: song.processingFormat)
        }
        if let clicks {
            engine.connect(clicksNode, to: engine.mainMixerNode, format: clicks.processingFormat)
        }
        apply(gains)
    }

    func play() throws {
        guard song != nil, !playing else { return }
        if !engine.isRunning {
            engine.prepare()
            do {
                try engine.start()
            } catch {
                throw PlayerError.failed(message: Self.cannotPlay(error))
            }
        }
        playing = true
        startNodes()
    }

    func pause() {
        guard playing else { return }
        from = position
        playing = false
        stopNodes()
        engine.pause()
    }

    func seek(to seconds: Double) {
        from = min(max(seconds, 0), length)
        if playing {
            stopNodes()
            startNodes()
        }
    }

    /// Where the song is: the place the segments started from plus what the song's node has
    /// played since.
    var position: Double {
        guard playing, let song, let rendered = songNode.lastRenderTime,
            let played = songNode.playerTime(forNodeTime: rendered), played.sampleTime >= 0
        else { return from }
        return min(from + Double(played.sampleTime) / song.processingFormat.sampleRate, length)
    }

    func setGains(_ next: Gains) {
        gains = next
        apply(next)
    }

    func stop() {
        playing = false
        stopNodes()
        engine.stop()
        engine.disconnectNodeOutput(songNode)
        engine.disconnectNodeOutput(clicksNode)
        song = nil
        clicks = nil
        from = 0
    }

    // the nodes

    private func apply(_ next: Gains) {
        songNode.volume = Float(next.song)
        clicksNode.volume = Float(next.hits)
    }

    /// Schedules both files from `from` and starts both nodes at one time.
    private func startNodes() {
        guard let song else { return }
        generation += 1
        let mine = generation
        let ends = schedule(song, on: songNode) { [weak self] in
            Task { @MainActor in self?.reachedTheEnd(mine) }
        }
        guard ends else {
            reachedTheEnd(mine)  // nothing left to play
            return
        }
        if let clicks {
            _ = schedule(clicks, on: clicksNode, then: nil)
        }
        let start =
            engine.isInManualRenderingMode
            ? nil
            : AVAudioTime(
                hostTime: mach_absolute_time() + AVAudioTime.hostTime(forSeconds: Self.lead))
        songNode.play(at: start)
        if clicks != nil {
            clicksNode.play(at: start)
        }
    }

    /// Schedules `file` from `from` on `node`; false when nothing of it is left.
    private func schedule(
        _ file: AVAudioFile, on node: AVAudioPlayerNode, then done: (@Sendable () -> Void)?
    ) -> Bool {
        let rate = file.processingFormat.sampleRate
        let first = AVAudioFramePosition((from * rate).rounded())
        guard first < file.length else { return false }
        let count = AVAudioFrameCount(file.length - first)
        // played back from a device; offline there is no device to wait for
        let reported: AVAudioPlayerNodeCompletionCallbackType =
            engine.isInManualRenderingMode ? .dataRendered : .dataPlayedBack
        node.scheduleSegment(
            file, startingFrame: first, frameCount: count, at: nil,
            completionCallbackType: reported
        ) { _ in done?() }
        return true
    }

    private func stopNodes() {
        generation += 1  // the stop calls the completions of what was scheduled: ignored
        songNode.stop()
        clicksNode.stop()
    }

    private func reachedTheEnd(_ scheduled: Int) {
        guard scheduled == generation, playing else { return }
        from = length
        playing = false
        stopNodes()
        engine.pause()
        paused?(.ended)
    }

    private func outputChanged() {
        guard playing else { return }
        from = position
        playing = false
        stopNodes()
        paused?(.interrupted)
    }

    /// What the reader is told when the sound cannot start (no output device, a busy one).
    static func cannotPlay(_ error: any Error) -> String {
        localized("The song cannot be played: %1$@", error.localizedDescription)
    }
}
