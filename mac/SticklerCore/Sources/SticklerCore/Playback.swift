import Foundation
import Observation

/// Why the player paused by itself.
public enum PlayerPause: Sendable {
    /// The song played to its end.
    case ended
    /// The sound output changed (headphones unplugged, another device): paused, not lost.
    case interrupted
}

/// What the player cannot do; its message is shown as the window's notice.
public enum PlayerError: Error, Equatable {
    /// The system cannot read the song's format: the core decodes a copy (`playable`).
    case unreadable
    /// Anything else (no sound device, a broken file), said in words for the reader.
    case failed(message: String)
}

/// What plays the sound (the app's AVAudioEngine, `ui/player.py` in GTK; a fake in tests):
/// the song and the clicks together on one clock.
@MainActor
public protocol Playing: AnyObject {
    /// Loads the song and, when there is one, the clicks; stopped at 0. Throws `PlayerError`.
    func load(song: URL, clicks: URL?) throws
    func play() throws
    func pause()
    func seek(to seconds: Double)
    /// Where it is now, in seconds of the song.
    var position: Double { get }
    func setGains(_ gains: Gains)
    /// Lets go of everything: nothing plays or holds the sound device any more.
    func stop()
    /// Told when it paused by itself.
    var paused: (@MainActor (PlayerPause) -> Void)? { get set }
}

/// Playback (SPEC.md "Mac playback", scope 2; GTK's `ui/playbar.py`): the controls' state and
/// what each control does. The core decides where a click or an arrow goes and how loud each
/// source plays; this model asks it and drives the player.
@MainActor @Observable
public final class PlaybackModel {
    public private(set) var playing = false
    /// Where the song is, in seconds.
    public private(set) var position = 0.0 {
        didSet { follow() }
    }
    /// The song's length in seconds.
    public private(set) var length = 0.0
    /// The song's bars in played order.
    public private(set) var bars: [SongBar] = [] {
        didSet { follow() }
    }
    public private(set) var hear = Hear.both
    /// The volume sliders, 0 to 1 (remembered by the core for every song).
    public private(set) var songVolume = 0.7
    public private(set) var hitsVolume = 1.0

    /// A result is shown and there is a player: the controls and the Controls menu work.
    public var canPlay: Bool { song != nil && onScreen && player != nil }
    /// "Bar 2 of 110".
    public var label: String { Timeline.label(bars, at: position) }
    /// "0:06".
    public var time: String { Timeline.clock(position) }
    /// "4:06".
    public var lengthText: String { Timeline.clock(length) }
    /// The written bar to mark on the sheet; nil when none sounds. It changes only when the
    /// bar does, so the sheet is not drawn again at every tick.
    public private(set) var marked: Int?

    private let player: (any Playing)?
    private let tick: Duration
    private let tell: @MainActor (Notice) -> Void
    private var core: (any Core)?
    private var song: String? {
        didSet { follow() }
    }
    private var clicks: String?
    private var onScreen = false  // the result is shown, not an export's steps
    private var loaded = false  // the player holds this song
    private var atEnd = false  // played to the end: play starts again at 0
    private var starting = false  // a play waits for the core (a copy, the gains)
    private var gains: Gains?  // the core's newest answer
    private var volumeRequest = 0  // older answers are dropped
    private var volumes: Task<Void, Never>?  // the last `volumes` command, sent in order
    private var ticking: Task<Void, Never>?

    /// `tick`: how often the position is read while playing (GTK: 50 ms). `tell` shows a
    /// notice in the window.
    init(player: (any Playing)?, tick: Duration, tell: @escaping @MainActor (Notice) -> Void) {
        self.player = player
        self.tick = tick
        self.tell = tell
        player?.paused = { [weak self] why in self?.pausedByItself(why) }
    }

    // what the app model tells it

    /// A new core (or none): nothing plays; the stored volumes are read.
    func attach(_ next: (any Core)?) {
        core = next
        forgetSong()
        gains = nil
        guard let next else { return }
        Task {
            do {
                let settings = try await next.send(.settings).payload(Settings.self)
                guard next === core else { return }
                songVolume = settings.songVolume
                hitsVolume = settings.hitsVolume
            } catch {
                refused(error)
            }
        }
    }

    /// The core's new state: a new song starts stopped at 0; a correction of the same song
    /// goes on with its new bars; an export pauses; any other screen stops playback.
    func show(_ screen: Screen) {
        switch screen {
        case .result(let result):
            if result.song != song {
                forgetSong()
                song = result.song
                clicks = result.clicks
            }
            onScreen = true
            bars = result.bars
            length = result.seconds
        case .exporting:
            onScreen = false
            if playing {
                pause()
            }
        default:
            forgetSong()
        }
    }

    // what the reader does

    /// Play or Pause (Space).
    public func toggle() {
        guard canPlay else { return }
        if playing {
            pause()
        } else {
            Task { await start() }
        }
    }

    /// Moves to `seconds`, kept inside the song; playing goes on from there.
    public func seek(to seconds: Double) {
        guard song != nil else { return }
        let target = min(max(seconds, 0), length)
        atEnd = false
        if loaded {
            player?.seek(to: target)
        }
        position = target
    }

    /// Go to the Start (⌥←, Home).
    public func goToStart() {
        guard canPlay else { return }
        seek(to: 0)
    }

    /// Previous Bar (←).
    public func previousBar() { step(by: -1) }
    /// Next Bar (→).
    public func nextBar() { step(by: 1) }

    /// A click on written bar `bar`: its next pass (the core's rule); stopped, the position
    /// moves there without playing.
    public func jump(toBar bar: Int) {
        guard canPlay else { return }
        ask(.jump(bar: bar, from: now))
    }

    public func setHear(_ next: Hear) {
        hear = next
        changeVolumes(song: nil, hits: nil)
    }

    public func setSongVolume(_ value: Double) {
        songVolume = value
        changeVolumes(song: value, hits: nil)
    }

    public func setHitsVolume(_ value: Double) {
        hitsVolume = value
        changeVolumes(song: nil, hits: value)
    }

    // the player

    private var now: Double { loaded ? (player?.position ?? position) : position }

    private func start() async {
        guard let player, let song, !starting else { return }
        starting = true
        defer { starting = false }
        if !loaded {
            guard await load(song, into: player) else { return }
        }
        if gains == nil {
            await changeVolumes(song: nil, hits: nil).value
        }
        guard song == self.song, loaded, onScreen else { return }  // closed meanwhile
        if atEnd {
            atEnd = false
            position = 0
        }
        player.seek(to: position)
        do {
            try player.play()
        } catch {
            failed(error)
            return
        }
        playing = true
        startTicking()
    }

    /// Loads the song, or the core's copy when the system cannot read it; false when neither
    /// plays (the reader is told why).
    private func load(_ song: String, into player: any Playing) async -> Bool {
        let clicks = self.clicks.map { URL(fileURLWithPath: $0) }
        do {
            try player.load(song: URL(fileURLWithPath: song), clicks: clicks)
        } catch PlayerError.unreadable {
            guard let core else { return false }
            do {
                let copy = try await core.send(.playable).payload(Playable.self)
                guard song == self.song else { return false }
                try player.load(song: URL(fileURLWithPath: copy.path), clicks: clicks)
            } catch {
                failed(error)
                return false
            }
        } catch {
            failed(error)
            return false
        }
        loaded = true
        if let gains {
            player.setGains(gains)
        }
        return true
    }

    private func pause() {
        player?.pause()
        position = now
        playing = false
        stopTicking()
    }

    private func pausedByItself(_ why: PlayerPause) {
        position = now
        playing = false
        stopTicking()
        if why == .ended {
            atEnd = true
        }
    }

    /// Nothing plays or is loaded; the controls show the start.
    private func forgetSong() {
        stopTicking()
        if loaded || playing {
            player?.stop()
        }
        loaded = false
        playing = false
        atEnd = false
        song = nil
        clicks = nil
        onScreen = false
        position = 0
        length = 0
        bars = []
    }

    private func startTicking() {
        stopTicking()
        ticking = Task { [weak self, tick] in
            while !Task.isCancelled {
                guard let self else { return }
                self.position = self.now
                try? await Task.sleep(for: tick)
            }
        }
    }

    /// The sounding bar's written number, set when it changes.
    private func follow() {
        let next = song == nil ? nil : Timeline.written(bars, at: position)
        if next != marked {
            marked = next
        }
    }

    private func stopTicking() {
        ticking?.cancel()
        ticking = nil
    }
}

// the core

extension PlaybackModel {
    private func step(by count: Int) {
        guard canPlay else { return }
        ask(.step(from: now, count: count))
    }

    /// Asks the core where to go and goes there, unless the song changed meanwhile.
    private func ask(_ command: Command) {
        guard let core, let asked = song else { return }
        Task {
            do {
                let reply = try await core.send(command).payload(Seconds.self)
                guard asked == song, let seconds = reply.seconds else { return }
                seek(to: seconds)
            } catch {
                refused(error)
            }
        }
    }

    /// Remembers the volumes given and plays at the gains the core answers. The commands go
    /// out one after another in the reader's order, so the core keeps the newest slider value;
    /// an answer that a newer change overtook is dropped.
    @discardableResult
    private func changeVolumes(song: Double?, hits: Double?) -> Task<Void, Never> {
        volumeRequest += 1
        let mine = volumeRequest
        let before = volumes
        let next = Task {
            await before?.value
            await applyVolumes(song: song, hits: hits, request: mine)
        }
        volumes = next
        return next
    }

    private func applyVolumes(song: Double?, hits: Double?, request mine: Int) async {
        guard let core else { return }
        do {
            let reply = try await core.send(.volumes(hear: hear, song: song, hits: hits))
                .payload(Gains.self)
            guard mine == volumeRequest, core === self.core else { return }
            gains = reply
            if loaded {
                player?.setGains(reply)
            }
        } catch {
            refused(error)
        }
    }

    private func refused(_ error: any Error) {
        if case CoreClientError.refused(let reason) = error {
            tell(Notice(text: reason.message, opens: nil))
        }
    }

    private func failed(_ error: any Error) {
        if case PlayerError.failed(let message) = error {
            tell(Notice(text: message, opens: nil))
        } else {
            refused(error)
        }
    }
}
