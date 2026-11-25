using System.Text.Json;

namespace Stickler.Core;

/// <summary>The <c>can_*</c> fields (<c>docs/bridge.md</c>, "States"): which buttons and menu
/// items are enabled. A field the core does not send means "not allowed".</summary>
public sealed record Abilities(
    bool Open = false,
    bool Cancel = false,
    bool Retry = false,
    bool Close = false,
    bool Export = false,
    bool Agree = false,
    bool NotNow = false,
    bool RetrySetup = false,
    bool RemoveModels = false)
{
    internal static Abilities Read(JsonElement s) => new(
        Json.Flag(s, "can_open"),
        Json.Flag(s, "can_cancel"),
        Json.Flag(s, "can_retry"),
        Json.Flag(s, "can_close"),
        Json.Flag(s, "can_export"),
        Json.Flag(s, "can_agree"),
        Json.Flag(s, "can_not_now"),
        Json.Flag(s, "can_retry_setup"),
        Json.Flag(s, "can_remove_models"));
}

public enum StepProgress
{
    Waiting,
    Running,
    Done,
}

/// <summary>A row of the step list (setup, analysis, drum track).</summary>
public sealed record StepRow(string Id, string Label, string Detail, StepProgress State)
{
    internal static StepRow Read(JsonElement s) => new(
        Json.Str(s, "id"),
        Json.Str(s, "label"),
        Json.Str(s, "detail"),
        Json.Str(s, "state") switch
        {
            "waiting" => StepProgress.Waiting,
            "running" => StepProgress.Running,
            "done" => StepProgress.Done,
            var other => throw new UnreadableLineException($"a step's state \"{other}\""),
        });
}

/// <summary>One missing model on the consent dialog (W1).</summary>
public sealed record Model(string Id, string Name, string Does, string Licence, string Size)
{
    internal static Model Read(JsonElement s) => new(
        Json.Str(s, "id"), Json.Str(s, "name"), Json.Str(s, "does"), Json.Str(s, "licence"), Json.Str(s, "size"));
}

/// <summary>One bar of the song in played order (for the playback module).</summary>
public sealed record SongBar(double Start, double End, int Bar, string Label)
{
    internal static SongBar Read(JsonElement s) => new(
        Json.Double(s, "start"), Json.Double(s, "end"), Json.Int(s, "bar"), Json.Str(s, "label"));
}

/// <summary>What the window shows: one screen of the core's states.</summary>
public abstract record Screen(string Kind);

public sealed record EmptyScreen() : Screen("empty");

public sealed record ConsentScreen(string? Song, IReadOnlyList<Model> Models, string TotalSize) : Screen("consent");

public sealed record SettingUpScreen(string? Song, IReadOnlyList<StepRow> Steps) : Screen("setting_up");

public sealed record SetupFailedScreen(
    string? Song, IReadOnlyList<StepRow> Steps, string Step, string Server, string Details) : Screen("setup_failed");

public sealed record AnalysingScreen(string Song, string Name, IReadOnlyList<StepRow> Steps) : Screen("analysing");

public sealed record ResultScreen(
    string Song,
    string Title,
    string Subtitle,
    string Artist,
    double Seconds,
    int Tempo,
    IReadOnlyList<int> Meter,
    string MusicXml,
    string? Clicks,
    IReadOnlyList<SongBar> Bars) : Screen("result");

public sealed record ExportingScreen(
    string Song, string Title, string Subtitle, string Dest, IReadOnlyList<StepRow> Steps) : Screen("exporting");

public enum FailureReason
{
    Unreadable,
    Analysis,
    Export,
}

public sealed record FailedScreen(
    string Song, string Name, FailureReason Reason, string Title, string Description, string Details) : Screen("failed");

/// <summary>A kind this client does not know (a core from a newer release): shown as nothing new.</summary>
public sealed record UnknownScreen(string Name) : Screen(Name);

/// <summary>The core's whole state (<c>docs/bridge.md</c>, "States"). Python decides it; C#
/// only draws it.</summary>
public sealed record AppState(Screen Screen, Abilities Can)
{
    public static AppState Empty { get; } = new(new EmptyScreen(), new Abilities(Open: true));

    public static AppState Parse(string json) => Read(Json.Parse(json));

    internal static AppState Read(JsonElement s)
    {
        var kind = Json.Str(s, "kind");
        Screen screen = kind switch
        {
            "empty" => new EmptyScreen(),
            "consent" => new ConsentScreen(
                Json.OptStr(s, "song"), Json.List(s, "models", Model.Read), Json.Str(s, "total_size")),
            "setting_up" => new SettingUpScreen(Json.OptStr(s, "song"), Json.List(s, "steps", StepRow.Read)),
            "setup_failed" => new SetupFailedScreen(
                Json.OptStr(s, "song"),
                Json.List(s, "steps", StepRow.Read),
                Json.Str(s, "step"),
                Json.Str(s, "server"),
                Json.Str(s, "details")),
            "analysing" => new AnalysingScreen(
                Json.Str(s, "song"), Json.Str(s, "name"), Json.List(s, "steps", StepRow.Read)),
            "result" => new ResultScreen(
                Json.Str(s, "song"),
                Json.Str(s, "title"),
                Json.Str(s, "subtitle"),
                Json.Str(s, "artist"),
                Json.Double(s, "seconds"),
                Json.Int(s, "tempo"),
                Json.List(s, "meter", e => e.GetInt32()),
                Json.Str(s, "musicxml"),
                Json.OptStr(s, "clicks"),
                Json.OptList(s, "bars", SongBar.Read)),
            "exporting" => new ExportingScreen(
                Json.Str(s, "song"),
                Json.Str(s, "title"),
                Json.Str(s, "subtitle"),
                Json.Str(s, "dest"),
                Json.List(s, "steps", StepRow.Read)),
            "failed" => new FailedScreen(
                Json.Str(s, "song"),
                Json.Str(s, "name"),
                Json.Str(s, "reason") switch
                {
                    "unreadable" => FailureReason.Unreadable,
                    "analysis" => FailureReason.Analysis,
                    "export" => FailureReason.Export,
                    var other => throw new UnreadableLineException($"a failure's reason \"{other}\""),
                },
                Json.Str(s, "title"),
                Json.Str(s, "description"),
                Json.Str(s, "details")),
            _ => new UnknownScreen(kind),
        };
        return new AppState(screen, Abilities.Read(s));
    }
}
