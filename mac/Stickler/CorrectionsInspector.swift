import SticklerCore
import SwiftUI

/// Design screen M11: the corrections in an inspector at the window's trailing edge. Beat:
/// Tempo, Beats per bar, the first "one"; Easier to Read: Simplify and Repeat signs; Back to
/// Detected under them. It draws the core's `controls` and sends one change per action; the
/// steppers send steps, which the core counts from its newest values.
struct CorrectionsInspector: View {
    let model: AppModel
    let controls: CorrectionControls

    /// The inspector's width on the canvas.
    static let width = 300.0

    var body: some View {
        Form {
            Section("Beat") {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Tempo")
                    Picker("Tempo", selection: tempo) {
                        Text("Half").tag(Tempo.half)
                        Text("As Detected").tag(Tempo.normal)
                        Text("Double").tag(Tempo.double)
                    }
                    .pickerStyle(.segmented)
                    .labelsHidden()
                }
                LabeledContent("Beats per bar") {
                    HStack(spacing: 6) {
                        Text(verbatim: "\(controls.beatsPerBar)")
                            .monospacedDigit()
                            .accessibilityHidden(true)  // the stepper says it
                        Stepper(
                            "Beats per bar",
                            onIncrement: controls.more ? { model.correct(.beatsPerBarBy(1)) } : nil,
                            onDecrement: controls.fewer
                                ? { model.correct(.beatsPerBarBy(-1)) } : nil
                        )
                        .labelsHidden()
                        .accessibilityValue(Text(verbatim: "\(controls.beatsPerBar)"))
                    }
                }
                LabeledContent {
                    HStack(spacing: 6) {
                        Text(verbatim: controls.firstOneLabel)
                            .monospacedDigit()
                            .accessibilityHidden(true)
                        Stepper(
                            "First “one”",
                            onIncrement: controls.later ? { model.correct(.firstOneBy(1)) } : nil,
                            onDecrement: controls.earlier
                                ? { model.correct(.firstOneBy(-1)) } : nil
                        )
                        .labelsHidden()
                        .accessibilityValue(Text(verbatim: controls.firstOneLabel))
                    }
                } label: {
                    Text("First “one”")
                    Text("Beats before it are a pickup")
                }
            }
            Section {
                Toggle(isOn: simplify) {
                    Text("Simplify")
                    Text("Nearly equal bars get one pattern")
                }
                Toggle(isOn: repeats) {
                    Text("Repeat signs")
                    Text("Equal bars are written once")
                }
            } header: {
                Text("Easier to Read")
            } footer: {
                HStack {
                    Spacer()
                    Button("Back to Detected") { model.correct(.detected) }
                        .disabled(!controls.corrected)
                    Spacer()
                }
                .padding(.top, 8)
            }
        }
        .formStyle(.grouped)
        .toggleStyle(.switch)
        .inspectorColumnWidth(Self.width)
    }

    private var tempo: Binding<Tempo> {
        Binding(get: { controls.tempo }, set: { model.correct(.tempo($0)) })
    }

    private var simplify: Binding<Bool> {
        Binding(get: { controls.simplify }, set: { model.correct(.simplify($0)) })
    }

    private var repeats: Binding<Bool> {
        Binding(get: { controls.repeats }, set: { model.correct(.repeats($0)) })
    }
}
