import SticklerCore
import SwiftUI

/// The first start, or a folder that cannot run the core: where the Stickler checkout is.
struct FolderView: View {
    let problem: FolderProblem?
    let choose: () -> Void

    var body: some View {
        ContentUnavailableView {
            Label("Where Is Stickler?", systemImage: "folder.badge.questionmark")
        } description: {
            Text(message)
        } actions: {
            Button("Choose Stickler Folder…", action: choose)
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
        }
    }

    private var message: LocalizedStringKey {
        switch problem {
        case nil:
            // the key is one text of the catalog; `+` alone would make a plain String
            LocalizedStringKey(
                "Until Stickler comes as an app, it runs from the folder you downloaded with git. "
                    + "Choose that folder.")
        case .notStickler:
            "This folder is not Stickler. Choose the folder with pyproject.toml and adapters in it."
        case .noUV:
            "uv was not found. Install it as the guide says, then choose the folder again."
        }
    }
}

/// Design screen M4: drop or open a song, and the recent songs.
struct EmptyWindowView: View {
    let model: AppModel

    var body: some View {
        VStack(spacing: 28) {
            ContentUnavailableView {
                Label("Drop a Song Here", systemImage: "music.note")
            } description: {
                Text(
                    LocalizedStringKey(
                        "Stickler listens to the drums and writes them as sheet music. "
                            + "MP3, FLAC, WAV or OGG; a song takes about 15 seconds."))
            } actions: {
                Button("Open a Song…") { Panels.openSong(model) }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                    .disabled(!model.state.can.open)
            }
            .fixedSize(horizontal: false, vertical: true)
            if !model.recent.isEmpty {
                RecentSongs(model: model)
                    .frame(maxWidth: 520)
            }
        }
        .padding(32)
    }
}

/// The recent songs: a click opens one; a song whose file is gone can only be removed.
struct RecentSongs: View {
    let model: AppModel

    var body: some View {
        GroupBox {
            VStack(spacing: 0) {
                ForEach(Array(model.recent.enumerated()), id: \.element.path) { index, row in
                    if index > 0 {
                        Divider()
                    }
                    RecentRowView(model: model, row: row)
                }
            }
        } label: {
            Text("Recent")
                .font(.headline)
        }
    }
}

struct RecentRowView: View {
    let model: AppModel
    let row: RecentRow

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(verbatim: row.title)
                Text(verbatim: row.detail)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            if row.missing {
                Button {
                    model.forget(row.path)
                } label: {
                    Image(systemName: "trash")
                }
                .buttonStyle(.borderless)
                .help(Text("Remove from the List"))
            } else {
                Image(systemName: "chevron.forward")
                    .foregroundStyle(.tertiary)
            }
        }
        .padding(.vertical, 6)
        .contentShape(Rectangle())
        .opacity(row.missing ? 0.5 : 1)
        .onTapGesture {
            if !row.missing, model.state.can.open {
                model.open(row.path)
            }
        }
    }
}

/// Until `mac-sheet`: a result is exported to be read (never in a release).
struct ResultPlaceholder: View {
    var body: some View {
        Text("Sheet music ready. Export it as PDF to read it.")
            .foregroundStyle(.secondary)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color(nsColor: .underPageBackgroundColor))
    }
}
