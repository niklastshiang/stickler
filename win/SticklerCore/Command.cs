using System.Text;
using System.Text.Json;

namespace Stickler.Core;

/// <summary>One command to the core (<c>docs/bridge.md</c>, "Commands"): its name and its
/// arguments in the order they are written.</summary>
public sealed class Command
{
    private readonly (string Name, object? Value)[] arguments;

    private Command(string name, params (string, object?)[] arguments)
    {
        Name = name;
        this.arguments = arguments;
    }

    public string Name { get; }

    public IReadOnlyList<(string Name, object? Value)> Arguments => arguments;

    public static Command Start { get; } = new("start");
    public static Command Agree { get; } = new("agree");
    public static Command NotNow { get; } = new("not_now");
    public static Command RetrySetup { get; } = new("retry_setup");
    public static Command Cancel { get; } = new("cancel");
    public static Command Retry { get; } = new("retry");
    public static Command Close { get; } = new("close");
    public static Command A4Pages { get; } = new("a4_pages");
    public static Command DrumTrackCost { get; } = new("drum_track_cost");
    public static Command Settings { get; } = new("settings");
    public static Command ZoomIn { get; } = new("zoom_in");
    public static Command ZoomOut { get; } = new("zoom_out");
    public static Command ActualSize { get; } = new("actual_size");
    public static Command RemovalSizes { get; } = new("removal_sizes");
    public static Command UninstallSizes { get; } = new("uninstall_sizes");
    public static Command Playable { get; } = new("playable");
    public static Command Quit { get; } = new("quit");

    public static Command Open(string path) => new("open", ("path", path));

    public static Command ExportMusicXml(string dest) => new("export_musicxml", ("dest", dest));

    public static Command ExportDrumTrack(string dest) => new("export_drum_track", ("dest", dest));

    public static Command ForgetRecent(string path) => new("forget_recent", ("path", path));

    public static Command Pages(double width, double? zoom = null) =>
        zoom is null ? new("pages", ("width", width)) : new("pages", ("width", width), ("zoom", zoom));

    public static Command SetZoom(double zoom) => new("set_zoom", ("zoom", zoom));

    public static Command RemoveModels(bool everything) => new("remove_models", ("everything", everything));

    public static Command BackUp(string dest) => new("back_up", ("dest", dest));

    public static Command BackupSummary(string src) => new("backup_summary", ("src", src));

    public static Command Restore(string src) => new("restore", ("src", src));

    public static Command Uninstall(bool everything) => new("uninstall", ("everything", everything));

    public static Command Jump(int bar, double at) => new("jump", ("bar", bar), ("at", at));

    public static Command StepBy(double at, int by) => new("step", ("at", at), ("by", by));

    /// <summary><c>correct</c>: exactly one change from the corrections controls.</summary>
    public static Command Correct(Correction change) => new("correct", (change.Key, change.Value));

    /// <summary><c>volumes</c>: <paramref name="hear"/> is <c>song</c>, <c>hits</c> or <c>both</c>;
    /// a slider's new value only when it moved.</summary>
    public static Command Volumes(string hear, double? song = null, double? hits = null)
    {
        var given = new List<(string, object?)> { ("hear", hear) };
        if (song is not null)
        {
            given.Add(("song", song));
        }
        if (hits is not null)
        {
            given.Add(("hits", hits));
        }
        return new Command("volumes", [.. given]);
    }

    /// <summary><c>volumes</c> for what to hear: its wire name is the lower-case one of <paramref name="hear"/>.</summary>
    public static Command Volumes(Hear hear, double? song = null, double? hits = null) =>
        Volumes(hear switch { Hear.Song => "song", Hear.Hits => "hits", _ => "both" }, song, hits);

    /// <summary>The command as one UTF-8 JSON line for <paramref name="id"/>, without the
    /// newline (the client adds <c>\n</c>, never <c>\r\n</c>).</summary>
    public string Line(int id)
    {
        using var buffer = new MemoryStream();
        using (var writer = new Utf8JsonWriter(buffer))
        {
            writer.WriteStartObject();
            writer.WriteNumber("id", id);
            writer.WriteString("cmd", Name);
            foreach (var (name, value) in arguments)
            {
                switch (value)
                {
                    case string text:
                        writer.WriteString(name, text);
                        break;
                    case bool flag:
                        writer.WriteBoolean(name, flag);
                        break;
                    case int number:
                        writer.WriteNumber(name, number);
                        break;
                    case double number:
                        writer.WriteNumber(name, number);
                        break;
                    default:
                        writer.WriteNull(name);
                        break;
                }
            }
            writer.WriteEndObject();
        }
        return Encoding.UTF8.GetString(buffer.ToArray());
    }

    public override string ToString() => Line(0);
}

/// <summary>One change of <c>correct</c> (as the Mac's <c>Correction</c>): a value, a stepper's
/// step (counted by the core from its newest values, so quick clicks are never lost), or Back
/// to Detected.</summary>
public sealed class Correction
{
    private Correction(string key, object value)
    {
        Key = key;
        Value = value;
    }

    public string Key { get; }

    public object Value { get; }

    public static Correction Detected { get; } = new("detected", true);

    public static Correction HalfTempo { get; } = new("tempo", "half");

    public static Correction NormalTempo { get; } = new("tempo", "normal");

    public static Correction DoubleTempo { get; } = new("tempo", "double");

    public static Correction BeatsPerBar(int beats) => new("beats_per_bar", beats);

    public static Correction BeatsPerBarBy(int step) => new("beats_per_bar_by", step);

    public static Correction FirstOne(int beat) => new("first_one", beat);

    public static Correction FirstOneBy(int step) => new("first_one_by", step);

    public static Correction Simplify(bool on) => new("simplify", on);

    public static Correction Repeats(bool on) => new("repeats", on);
}
