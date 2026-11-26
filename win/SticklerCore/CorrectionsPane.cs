namespace Stickler.Core;

/// <summary>The corrections pane's decisions (SPEC.md, module <c>win-corrections</c>; the Mac's
/// <c>CorrectionsMenu</c>): when it can be beside the sheet, what its menu item says, and when
/// the header's small spinner turns. What the controls show and every change's range are the
/// core's.</summary>
public static class CorrectionsPane
{
    /// <summary>The shown result's controls; null while there is nothing to correct: no result,
    /// an export's steps (the core would refuse), a stopped core, or a core from before
    /// <c>mac-corrections</c>.</summary>
    public static CorrectionControls? Controls(AppModel model)
    {
        ArgumentNullException.ThrowIfNull(model);
        return model.Phase == Phase.Running && model.State.Screen is ResultScreen result ? result.Controls : null;
    }

    public static bool Enabled(AppModel model) => Controls(model) is not null;

    /// <summary>The pane is beside the sheet when it was left open and there is something to
    /// correct; without a result it stays away but is remembered as open.</summary>
    public static bool Presented(bool shown, AppModel model) => shown && Enabled(model);

    /// <summary>The menu item says what it does now.</summary>
    public static string Title(bool presented, Strings strings)
    {
        ArgumentNullException.ThrowIfNull(strings);
        return strings.Text(presented ? "Hide Corrections" : "Show Corrections");
    }

    /// <summary>The core is writing a correction's notes: the old sheet stays, a spinner turns.</summary>
    public static bool Correcting(AppModel model)
    {
        ArgumentNullException.ThrowIfNull(model);
        return model.Phase == Phase.Running && model.State.Screen is ResultScreen { Correcting: true };
    }
}
