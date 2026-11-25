using System.Globalization;

namespace Stickler.Core;

/// <summary>Which page the window shows (design screens W4, W5, the error page, the stopped core).</summary>
public enum Page
{
    /// <summary>The core ended or did not start: "Stickler Stopped Unexpectedly".</summary>
    Stopped,

    /// <summary>The drop area and the recent songs (W4); the setup dialogs lie over it.</summary>
    Empty,

    /// <summary>The step list of an analysis or a drum track export (W5).</summary>
    Steps,

    /// <summary>What went wrong with a song, "Technical Details", "Try Again".</summary>
    Failed,

    /// <summary>The sheet music (until <c>win-sheet</c>, the grey desk).</summary>
    Result,
}

/// <summary>The first start's dialog over the empty window (W1–W3), as the core's state says.</summary>
public enum SetupDialog
{
    None,
    Consent,
    Download,
    Failed,
}

/// <summary>What the window shows for the model's state (SPEC.md, module <c>win-shell</c>):
/// decided here, without WinUI, so it is tested on every system; the XAML only draws it.</summary>
public static class WindowView
{
    public static Page Page(AppModel model)
    {
        ArgumentNullException.ThrowIfNull(model);
        if (model.Phase == Phase.Stopped)
        {
            return Core.Page.Stopped;
        }
        return model.State.Screen switch
        {
            AnalysingScreen or ExportingScreen => Core.Page.Steps,
            FailedScreen => Core.Page.Failed,
            ResultScreen => Core.Page.Result,
            _ => Core.Page.Empty,
        };
    }

    public static SetupDialog Dialog(AppState state)
    {
        ArgumentNullException.ThrowIfNull(state);
        return state.Screen switch
        {
            ConsentScreen => SetupDialog.Consent,
            SettingUpScreen => SetupDialog.Download,
            SetupFailedScreen => SetupDialog.Failed,
            _ => SetupDialog.None,
        };
    }

    /// <summary>The header with the song's title and Open and Export: only once a song is open
    /// (W4 has none; File › Open… and the drop area are enough there).</summary>
    public static bool ShowsHeader(AppModel model) =>
        Page(model) is Core.Page.Steps or Core.Page.Failed or Core.Page.Result;

    /// <summary>A step row's state in words, as the other apps say it.</summary>
    public static string StepState(StepProgress state, Strings strings)
    {
        ArgumentNullException.ThrowIfNull(strings);
        return strings.Text(state switch
        {
            StepProgress.Done => "Done",
            StepProgress.Running => "Running",
            _ => "Waiting",
        });
    }

    /// <summary>The consent's first lines: how many models, downloaded once (W1).</summary>
    public static string ConsentIntro(ConsentScreen consent, Strings strings)
    {
        ArgumentNullException.ThrowIfNull(consent);
        ArgumentNullException.ThrowIfNull(strings);
        var count = consent.Models.Count;
        return strings.Plural(
            "To hear the drums, Stickler needs a trained model. It is downloaded once; after that, everything runs on this computer, offline.",
            count,
            ("count", count.ToString(CultureInfo.CurrentCulture)));
    }

    /// <summary>ADTOF's licence allows non-commercial use only: said under the list when it is downloaded.</summary>
    public static bool NamesNonCommercialUse(ConsentScreen consent)
    {
        ArgumentNullException.ThrowIfNull(consent);
        return consent.Models.Any(m => m.Id == "adtof");
    }

    /// <summary>The song's file name without its ending: the start of every export's name.</summary>
    public static string BaseName(string song) => Path.GetFileNameWithoutExtension(song.Replace('\\', '/').Split('/')[^1]);

    public static string MusicXmlName(string song) => BaseName(song) + ".musicxml";

    /// <summary>"Eye of the Tiger (drums).flac", "(drums)" in the reader's language.</summary>
    public static string DrumTrackName(string song, Strings strings)
    {
        ArgumentNullException.ThrowIfNull(strings);
        return strings.Text("{title} (drums)", ("title", BaseName(song))) + ".flac";
    }

    /// <summary>The backup's name the save dialog proposes, as the GTK and Mac apps'.</summary>
    public static string BackupName(DateOnly day) =>
        $"Stickler Backup {day.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture)}.zip";
}
