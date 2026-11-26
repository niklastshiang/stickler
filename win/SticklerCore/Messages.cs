using System.Text.Json;

namespace Stickler.Core;

/// <summary>The protocol this client speaks (<c>docs/bridge.md</c>).</summary>
public static class BridgeProtocol
{
    public const int Version = 1;
}

/// <summary>The core's first line.</summary>
public sealed record Hello(int Protocol, string Version, string Language);

/// <summary>A recent song (<c>recent</c>): a missing one can only be removed.</summary>
public sealed record RecentRow(string Path, string Title, string Detail, bool Missing)
{
    internal static RecentRow Read(JsonElement s) =>
        new(Json.Str(s, "path"), Json.Str(s, "title"), Json.Str(s, "detail"), Json.Bool(s, "missing"));
}

/// <summary>A short message (the flyout after saving, other notes); <c>Opens</c> a file just saved.</summary>
public sealed record Notice(string Text, string? Opens);

/// <summary>An error reply (<c>docs/bridge.md</c>, "Errors"); the message is translated.</summary>
public sealed record BridgeError(string Code, string Message);

/// <summary>One line from the core.</summary>
public abstract record Incoming
{
    /// <summary>Reads one line; a line that is neither an event nor a reply is an
    /// <see cref="UnreadableLineException"/>.</summary>
    public static Incoming Parse(string line)
    {
        try
        {
            return Read(Json.Parse(line));
        }
        catch (Exception error) when (error is InvalidOperationException or FormatException or KeyNotFoundException)
        {
            throw new UnreadableLineException("a field of an unexpected kind", error);
        }
    }

    private static Incoming Read(JsonElement root)
    {
        if (root.ValueKind != JsonValueKind.Object)
        {
            throw new UnreadableLineException("not a JSON object");
        }
        if (Json.Has(root, "event"))
        {
            var name = Json.Str(root, "event");
            if (name == "hello")
            {
                // only the protocol is needed to tell a core of another release
                return new HelloLine(new Hello(Json.Int(root, "protocol"), Json.OptStr(root, "version") ?? "", Json.OptStr(root, "language") ?? ""));
            }
            var seq = Json.OptInt(root, "seq") ?? 0;
            return name switch
            {
                "state" => new StateEvent(seq, AppState.Read(Json.Field(root, "state"))),
                "recent" => new RecentEvent(seq, Json.List(root, "rows", RecentRow.Read)),
                "notice" => new NoticeEvent(seq, new Notice(Json.Str(root, "text"), Json.OptStr(root, "opens"))),
                _ => new UnknownEvent(seq, name),
            };
        }
        if (Json.Has(root, "ok"))
        {
            return new ReplyLine(Reply.Read(root));
        }
        throw new UnreadableLineException("neither an event nor a reply");
    }
}

public sealed record HelloLine(Hello Hello) : Incoming;

public sealed record StateEvent(int Seq, AppState State) : Incoming;

public sealed record RecentEvent(int Seq, IReadOnlyList<RecentRow> Rows) : Incoming;

public sealed record NoticeEvent(int Seq, Notice Notice) : Incoming;

/// <summary>An event this client does not know (a core from a newer release).</summary>
public sealed record UnknownEvent(int Seq, string Name) : Incoming;

public sealed record ReplyLine(Reply Reply) : Incoming;

/// <summary>The answer to one command. Its fields beyond <c>id</c>, <c>ok</c> and <c>error</c>
/// depend on the command: read them with the payload types' <c>From</c>.</summary>
public sealed class Reply
{
    private Reply(int? id, BridgeError? error, JsonElement fields)
    {
        Id = id;
        Error = error;
        Fields = fields;
    }

    /// <summary><c>null</c> when the core could not read the command's <c>id</c>.</summary>
    public int? Id { get; }

    public BridgeError? Error { get; }

    public bool Ok => Error is null;

    /// <summary>The whole reply as the core sent it.</summary>
    public JsonElement Fields { get; }

    public static Reply Parse(string line) => Read(Json.Parse(line));

    internal static Reply Read(JsonElement root)
    {
        BridgeError? error = null;
        if (!Json.Bool(root, "ok"))
        {
            error = Json.Has(root, "error")
                ? new BridgeError(Json.Str(Json.Field(root, "error"), "code"), Json.Str(Json.Field(root, "error"), "message"))
                : new BridgeError("internal", "");
        }
        return new Reply(Json.OptInt(root, "id"), error, root);
    }
}

/// <summary><c>drum_track_cost</c>: what saving the drum track costs, said before it starts.</summary>
public sealed record DrumTrackCost(int Minutes, string Text, bool Download)
{
    public static DrumTrackCost From(Reply reply) =>
        new(Json.Int(reply.Fields, "minutes"), Json.Str(reply.Fields, "text"), Json.Bool(reply.Fields, "download"));
}

/// <summary><c>removal_sizes</c>: what "Remove Downloaded Models…" frees.</summary>
public sealed record RemovalSizes(long Models, long Everything, string ModelsText, string EverythingText)
{
    public static RemovalSizes From(Reply reply) => new(
        Json.Long(reply.Fields, "models"),
        Json.Long(reply.Fields, "everything"),
        Json.Str(reply.Fields, "models_text"),
        Json.Str(reply.Fields, "everything_text"));
}

/// <summary><c>uninstall_sizes</c>: what "Uninstall Stickler…" frees.</summary>
public sealed record UninstallSizes(long Keep, long Everything, string KeepText, string EverythingText)
{
    public static UninstallSizes From(Reply reply) => new(
        Json.Long(reply.Fields, "keep"),
        Json.Long(reply.Fields, "everything"),
        Json.Str(reply.Fields, "keep_text"),
        Json.Str(reply.Fields, "everything_text"));
}

/// <summary><c>backup_summary</c>: what a backup holds, with the restore's question.</summary>
public sealed record BackupSummary(string Created, int Songs, long Size, string Text)
{
    public static BackupSummary From(Reply reply) => new(
        Json.Str(reply.Fields, "created"),
        Json.Int(reply.Fields, "songs"),
        Json.Long(reply.Fields, "size"),
        Json.Str(reply.Fields, "text"));
}

/// <summary>A written bar's rectangle on a page, in page pixels.</summary>
public sealed record BarBox(int Bar, double X, double Y, double Width, double Height)
{
    internal static BarBox Read(JsonElement s) => new(
        Json.Int(s, "bar"), Json.Double(s, "x"), Json.Double(s, "y"), Json.Double(s, "width"), Json.Double(s, "height"));
}

/// <summary>One engraved page: its SVG, its size in CSS pixels and its bars.</summary>
public sealed record SheetPage(string Svg, double Width, double Height, IReadOnlyList<BarBox> Bars)
{
    internal static SheetPage Read(JsonElement s) => new(
        Json.Str(s, "svg"), Json.Double(s, "width"), Json.Double(s, "height"), Json.List(s, "bars", BarBox.Read));
}

/// <summary><c>pages</c>: the sheet music at a width and note size.</summary>
public sealed record Pages(double Zoom, IReadOnlyList<SheetPage> Sheets)
{
    public static Pages From(Reply reply) =>
        new(Json.Double(reply.Fields, "zoom"), Json.List(reply.Fields, "pages", SheetPage.Read));
}

/// <summary><c>a4_pages</c>: the pages of the PDF (each A4 in its proportions) and its title.</summary>
public sealed record A4Pages(string Title, IReadOnlyList<SheetPage> Sheets)
{
    public static A4Pages From(Reply reply) =>
        new(Json.Str(reply.Fields, "title"), Json.List(reply.Fields, "pages", SheetPage.Read));
}

/// <summary><c>set_zoom</c>, <c>zoom_in</c>, <c>zoom_out</c>, <c>actual_size</c>: the new note size.</summary>
public sealed record Zoom(double Size, string Percent)
{
    public static Zoom From(Reply reply) =>
        new(Json.Double(reply.Fields, "zoom"), Json.Str(reply.Fields, "percent"));
}

/// <summary><c>settings</c>: the stored note size as the menu shows it (the other settings are
/// the playback's).</summary>
public sealed record SheetSettings(double Zoom, string Percent)
{
    public static SheetSettings From(Reply reply) =>
        new(Json.Double(reply.Fields, "zoom"), Json.Str(reply.Fields, "percent"));
}
