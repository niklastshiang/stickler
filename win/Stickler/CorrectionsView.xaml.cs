using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Stickler.Core;

namespace Stickler;

/// <summary>The corrections pane of design screen W11 (SPEC.md, module <c>win-corrections</c>,
/// scope 2). It shows the core's <see cref="CorrectionControls"/> and sends one change per
/// control action; every value, range and text of a value is the core's. A pure view: checked
/// by screenshots and by hand, not counted for coverage.</summary>
public sealed partial class CorrectionsView : UserControl
{
    private AppModel? model;
    private CorrectionControls? shown;
    private bool showing; // the core's values are being put into the controls: not the reader's doing

    public CorrectionsView()
    {
        InitializeComponent();
    }

    public void Attach(AppModel app, Strings strings)
    {
        model = app;
        string T(string english) => strings.Text(english);
        Heading.Text = T("Corrections");
        AutomationProperties.SetName(this, T("Corrections"));
        BeatHeading.Text = T("Beat");
        TempoText.Text = T("Tempo");
        AutomationProperties.SetName(TempoGroup, T("Tempo"));
        HalfButton.Content = T("Half");
        NormalButton.Content = T("As Detected");
        DoubleButton.Content = T("Double");
        BeatsText.Text = T("Beats per bar");
        Call(MoreButton, T("One beat more"));
        Call(FewerButton, T("One beat fewer"));
        FirstText.Text = T("First “one”");
        FirstNote.Text = T("Beats before it are a pickup");
        Call(LaterButton, T("One beat later"));
        Call(EarlierButton, T("One beat earlier"));
        ReadHeading.Text = T("Easier to Read");
        SimplifyText.Text = T("Simplify");
        SimplifyNote.Text = T("Nearly equal bars get one pattern");
        AutomationProperties.SetName(SimplifySwitch, T("Simplify"));
        RepeatsText.Text = T("Repeat signs");
        RepeatsNote.Text = T("Equal bars are written once");
        AutomationProperties.SetName(RepeatsSwitch, T("Repeat signs"));
        DetectedButton.Content = T("Back to Detected");
    }

    /// <summary>The core's values in the controls.</summary>
    public void Show(CorrectionControls controls)
    {
        shown = controls;
        showing = true;
        try
        {
            HalfButton.IsChecked = controls.Tempo == Tempo.Halved;
            NormalButton.IsChecked = controls.Tempo == Tempo.Normal;
            DoubleButton.IsChecked = controls.Tempo == Tempo.Doubled;
            BeatsValue.Text = controls.BeatsPerBar.ToString(System.Globalization.CultureInfo.CurrentCulture);
            MoreButton.IsEnabled = controls.More;
            FewerButton.IsEnabled = controls.Fewer;
            FirstValue.Text = controls.FirstOneLabel;
            LaterButton.IsEnabled = controls.Later;
            EarlierButton.IsEnabled = controls.Earlier;
            SimplifySwitch.IsOn = controls.Simplify;
            RepeatsSwitch.IsOn = controls.Repeats;
            DetectedButton.IsEnabled = controls.Corrected;
        }
        finally
        {
            showing = false;
        }
    }

    private static void Call(Button button, string name)
    {
        AutomationProperties.SetName(button, name);
        ToolTipService.SetToolTip(button, name);
    }

    // a click on the chosen tempo would switch its button off: the core's value is shown again
    private void SetTempo(Correction change)
    {
        model?.Correct(change);
        if (shown is { } controls)
        {
            Show(controls);
        }
    }

    private void OnHalf(object sender, RoutedEventArgs e) => SetTempo(Correction.HalfTempo);

    private void OnNormal(object sender, RoutedEventArgs e) => SetTempo(Correction.NormalTempo);

    private void OnDouble(object sender, RoutedEventArgs e) => SetTempo(Correction.DoubleTempo);

    // steps, counted by the core from its newest values: two quick clicks are two steps
    private void OnMore(object sender, RoutedEventArgs e) => model?.Correct(Correction.BeatsPerBarBy(1));

    private void OnFewer(object sender, RoutedEventArgs e) => model?.Correct(Correction.BeatsPerBarBy(-1));

    private void OnLater(object sender, RoutedEventArgs e) => model?.Correct(Correction.FirstOneBy(1));

    private void OnEarlier(object sender, RoutedEventArgs e) => model?.Correct(Correction.FirstOneBy(-1));

    private void OnSimplify(object sender, RoutedEventArgs e)
    {
        if (!showing)
        {
            model?.Correct(Correction.Simplify(SimplifySwitch.IsOn));
        }
    }

    private void OnRepeats(object sender, RoutedEventArgs e)
    {
        if (!showing)
        {
            model?.Correct(Correction.Repeats(RepeatsSwitch.IsOn));
        }
    }

    private void OnDetected(object sender, RoutedEventArgs e) => model?.Correct(Correction.Detected);
}
