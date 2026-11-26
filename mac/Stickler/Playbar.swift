import SticklerCore
import SwiftUI

/// Design screen M10: the controls in a glass capsule floating over the desk at the window's
/// bottom, the sheet scrolling under it. Previous Bar, Play/Pause, Next Bar, the time, the
/// position, the length, "Bar 2 of 110", Volume, and Song · Hits · Both. The model decides;
/// this only draws it and forwards the reader's actions.
struct Playbar: View {
    let playback: PlaybackModel
    @State private var volumeOpen = false

    /// The room the capsule takes at the window's bottom, its margin included: the sheet
    /// leaves it free under its last page.
    static let room = 84.0

    /// What the capsule shows in the width it has. Each part is as wide as its own text in
    /// the reader's language; in a narrow window (an inspector beside the sheet) the capsule
    /// keeps one row and gives way as macOS's own controls do (owner, 2026-11-25): it leaves
    /// out, in turn, "Bar n of N" (the marker shows the bar, VoiceOver hears it with the
    /// position), then the time and the length, and then draws Song · Hits · Both as a pop-up
    /// menu.
    enum Fit: CaseIterable {
        case full, noLabel, noTimes, narrowest

        var label: Bool { self == .full }
        var times: Bool { self == .full || self == .noLabel }
        var segmented: Bool { self != .narrowest }
    }

    /// The song's widest "Bar n of N": the text keeps its width while the bars go by.
    static func widest(_ bars: [SongBar]) -> String {
        bars.map(\.label).max { $0.count < $1.count } ?? ""
    }

    var body: some View {
        ViewThatFits(in: .horizontal) {
            row(.full)
            row(.noLabel)
            row(.noTimes)
            row(.narrowest)
        }
        .padding(.horizontal, 14)
        .frame(height: 52)
        .glassEffect(.regular, in: .capsule)
        .accessibilityElement(children: .contain)
        .accessibilityLabel(Text("Controls"))
    }

    /// The capsule's one row as `fit` has it.
    func row(_ fit: Fit) -> some View {
        HStack(spacing: 10) {
            buttons
            if fit.times {
                clock(playback.time, alignment: .trailing)
                    .accessibilityHidden(true)  // the slider says it
            }
            Slider(
                value: Binding(get: { playback.position }, set: { playback.seek(to: $0) }),
                in: 0...max(playback.length, 0.001)
            )
            .frame(minWidth: 120, idealWidth: 120, maxWidth: .infinity)
            .accessibilityLabel(Text("Position"))
            .accessibilityValue(Text(verbatim: "\(playback.time), \(playback.label)"))
            if fit.times {
                clock(playback.lengthText, alignment: .leading)
            }
            if fit.label {
                ZStack(alignment: .leading) {
                    Text(verbatim: Self.widest(playback.bars)).hidden()
                    Text(verbatim: playback.label)
                }
                .lineLimit(1)
                .fixedSize()
                .accessibilityHidden(true)
            }
            volume
            hear(segmented: fit.segmented)
        }
    }

    private var buttons: some View {
        HStack(spacing: 2) {
            Button(action: playback.previousBar) {
                Label("Previous Bar", systemImage: "backward.end.fill")
            }
            .help(Text("Previous Bar"))
            Button(action: playback.toggle) {
                Label(
                    playback.playing ? LocalizedStringKey("Pause") : "Play",
                    systemImage: playback.playing ? "pause.fill" : "play.fill"
                )
                .font(.title2)
                .frame(width: 28)
            }
            .help(Text(playback.playing ? LocalizedStringKey("Pause") : "Play"))
            Button(action: playback.nextBar) {
                Label("Next Bar", systemImage: "forward.end.fill")
            }
            .help(Text("Next Bar"))
        }
        .labelStyle(.iconOnly)
        .buttonStyle(.borderless)
        .controlSize(.large)
        .fixedSize()
    }

    private func clock(_ text: String, alignment: Alignment) -> some View {
        Text(verbatim: text)
            .font(.caption.monospacedDigit())
            .foregroundStyle(.secondary)
            .frame(minWidth: 34, alignment: alignment)
            .fixedSize()
    }

    private var volume: some View {
        Button {
            volumeOpen.toggle()
        } label: {
            Label("Volume", systemImage: "speaker.wave.2.fill")
        }
        .labelStyle(.iconOnly)
        .buttonStyle(.borderless)
        .fixedSize()
        .help(Text("Volume"))
        .popover(isPresented: $volumeOpen, arrowEdge: .top) {
            VolumeSliders(playback: playback)
        }
    }

    /// Song · Hits · Both as wide as its words: a fixed width let the German ones spill over
    /// the Volume button (owner, 2026-11-25).
    @ViewBuilder
    private func hear(segmented: Bool) -> some View {
        let picker = Picker(
            "What to Hear",
            selection: Binding(get: { playback.hear }, set: { playback.setHear($0) })
        ) {
            Text("Song").tag(Hear.song)
            Text("Hits").tag(Hear.hits)
            Text("Both").tag(Hear.both)
        }
        .labelsHidden()
        .fixedSize()
        if segmented {
            picker.pickerStyle(.segmented)
        } else {
            picker.pickerStyle(.menu).help(Text("What to Hear"))
        }
    }
}

/// What floats over the sheet at the window's bottom (M10): the notice, then the controls.
struct PlaybackOverlay: View {
    let model: AppModel

    var body: some View {
        VStack(spacing: 8) {
            if let notice = model.notice {
                NoticeBar(model: model, notice: notice)
                    .clipShape(.rect(cornerRadius: 12))
            }
            Playbar(playback: model.playback)
        }
        .padding(.horizontal, 24)
        .padding(.bottom, 16)
    }
}

/// The volume popover (M10): the song's and the detected hits' slider, remembered by the core
/// for every song.
struct VolumeSliders: View {
    let playback: PlaybackModel

    var body: some View {
        Grid(alignment: .leading, horizontalSpacing: 12, verticalSpacing: 10) {
            GridRow {
                Text("Song")
                Slider(
                    value: Binding(
                        get: { playback.songVolume }, set: { playback.setSongVolume($0) }),
                    in: 0...1
                )
                .accessibilityLabel(Text("Song"))
            }
            GridRow {
                Text("Detected hits")
                Slider(
                    value: Binding(
                        get: { playback.hitsVolume }, set: { playback.setHitsVolume($0) }),
                    in: 0...1
                )
                .accessibilityLabel(Text("Detected hits"))
            }
        }
        .frame(width: 264)
        .padding(16)
    }
}
