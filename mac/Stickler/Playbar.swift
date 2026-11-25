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

    var body: some View {
        HStack(spacing: 10) {
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
            Text(verbatim: playback.time)
                .font(.caption.monospacedDigit())
                .foregroundStyle(.secondary)
                .frame(minWidth: 34, alignment: .trailing)
                .accessibilityHidden(true)  // the slider says it
            Slider(
                value: Binding(get: { playback.position }, set: { playback.seek(to: $0) }),
                in: 0...max(playback.length, 0.001)
            )
            .frame(minWidth: 120)
            .accessibilityLabel(Text("Position"))
            .accessibilityValue(Text(verbatim: "\(playback.time), \(playback.label)"))
            Text(verbatim: playback.lengthText)
                .font(.caption.monospacedDigit())
                .foregroundStyle(.secondary)
                .frame(minWidth: 34, alignment: .leading)
            Text(verbatim: playback.label)
                .lineLimit(1)
                .frame(width: 100, alignment: .leading)
                .accessibilityHidden(true)
            Button {
                volumeOpen.toggle()
            } label: {
                Label("Volume", systemImage: "speaker.wave.2.fill")
            }
            .labelStyle(.iconOnly)
            .buttonStyle(.borderless)
            .help(Text("Volume"))
            .popover(isPresented: $volumeOpen, arrowEdge: .top) {
                VolumeSliders(playback: playback)
            }
            Picker(
                "What to Hear",
                selection: Binding(get: { playback.hear }, set: { playback.setHear($0) })
            ) {
                Text("Song").tag(Hear.song)
                Text("Hits").tag(Hear.hits)
                Text("Both").tag(Hear.both)
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            .frame(width: 168)
        }
        .padding(.horizontal, 14)
        .frame(height: 52)
        .glassEffect(.regular, in: .capsule)
        .accessibilityElement(children: .contain)
        .accessibilityLabel(Text("Controls"))
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
