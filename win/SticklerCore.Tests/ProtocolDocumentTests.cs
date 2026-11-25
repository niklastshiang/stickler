using System.Text.Json;
using System.Text.RegularExpressions;

namespace Stickler.Core.Tests;

/// <summary>Every example line of <c>docs/bridge.md</c> (the same lines the Python doc test
/// checks) reads as the client means it, and every command the client writes is the
/// document's line.</summary>
[TestClass]
public sealed partial class ProtocolDocumentTests
{
    private static readonly string Document =
        File.ReadAllText(Path.Combine(Repo.Root, "docs", "bridge.md")).Replace("\r\n", "\n", StringComparison.Ordinal);

    /// <summary>The example blocks under each <c>##</c> section: (section, the block's lines).</summary>
    private static IEnumerable<(string Section, string Heading, string[] Lines)> Blocks()
    {
        var section = "";
        var heading = "";
        foreach (Match match in Parts().Matches(Document))
        {
            if (match.Groups["section"].Success)
            {
                section = match.Groups["section"].Value.Trim();
            }
            else if (match.Groups["heading"].Success)
            {
                heading = match.Groups["heading"].Value.Trim().Trim('`');
            }
            else
            {
                var lines = match.Groups["json"].Value.Split('\n', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
                yield return (section, heading, lines);
            }
        }
    }

    [TestMethod]
    public void EveryEventReadsAsItsKind()
    {
        var events = Blocks().Where(b => b.Section == "Events").SelectMany(b => b.Lines).ToList();
        Assert.HasCount(4, events);
        foreach (var line in events)
        {
            var incoming = Incoming.Parse(line);
            Assert.IsNotInstanceOfType<UnknownEvent>(incoming, line);
            Assert.IsNotInstanceOfType<ReplyLine>(incoming, line);
        }
        var state = (StateEvent)Incoming.Parse(events[1]);
        Assert.AreEqual(1, state.Seq);
        Assert.AreEqual(AppState.Empty, state.State);
    }

    [TestMethod]
    public void EveryStateReadsAsAKnownScreenWithItsAbilities()
    {
        var states = Blocks().Where(b => b.Section == "States").ToList();
        Assert.HasCount(8, states);
        foreach (var (_, heading, lines) in states)
        {
            var state = AppState.Parse(lines.Single());
            Assert.AreEqual(heading, state.Screen.Kind);
            Assert.IsNotInstanceOfType<UnknownScreen>(state.Screen);
            Assert.IsTrue(state.Can.Open, heading);
        }
        var result = (ResultScreen)AppState.Parse(states.Single(s => s.Heading == "result").Lines[0]).Screen;
        Assert.AreEqual("Survivor · ♩ = 109 · 4/4", result.Subtitle);
        Assert.AreEqual(2.51, result.Bars[1].Start);
        Assert.AreEqual("4/4", string.Join("/", result.Meter));
    }

    [TestMethod]
    public void EveryCommandIsTheDocumentsLineAndItsReplyReads()
    {
        var commands = Blocks().Where(b => b.Section == "Commands").ToList();
        Assert.IsGreaterThanOrEqualTo(30, commands.Count);
        foreach (var (_, name, lines) in commands)
        {
            using var sent = JsonDocument.Parse(lines[0]);
            var id = sent.RootElement.GetProperty("id").GetInt32();
            var command = Build(name, sent.RootElement);
            Assert.AreEqual(name, command.Name);
            using var written = JsonDocument.Parse(command.Line(id));
            Assert.IsTrue(JsonElement.DeepEquals(sent.RootElement, written.RootElement), $"{lines[0]} ≠ {command.Line(id)}");
            var reply = Reply.Parse(lines[1]);
            Assert.AreEqual(id, reply.Id);
            Assert.IsTrue(reply.Ok, name);
        }
    }

    [TestMethod]
    public void TheRepliesWithFieldsReadAsTheirPayloads()
    {
        string ReplyOf(string name) => Blocks().Single(b => b.Section == "Commands" && b.Heading == name).Lines[1];
        Assert.AreEqual(8, DrumTrackCost.From(Reply.Parse(ReplyOf("drum_track_cost"))).Minutes);
        Assert.AreEqual(2213400000, RemovalSizes.From(Reply.Parse(ReplyOf("removal_sizes"))).Everything);
        Assert.AreEqual(12, BackupSummary.From(Reply.Parse(ReplyOf("backup_summary"))).Songs);
        Assert.StartsWith("This removes", UninstallSizes.From(Reply.Parse(ReplyOf("uninstall_sizes"))).KeepText);
    }

    [TestMethod]
    public void TheErrorReplyOfTheLifetimeSectionReads()
    {
        var replies = Blocks().First(b => b.Section == "Lines and lifetime").Lines;
        Assert.IsTrue(Reply.Parse(replies[0]).Ok);
        var refused = Reply.Parse(replies[1]);
        Assert.AreEqual(new BridgeError("not_now", "This is not possible right now."), refused.Error);
    }

    /// <summary>The client's command for a document line, built from its arguments.</summary>
    private static Command Build(string name, JsonElement line)
    {
        string S(string key) => line.GetProperty(key).GetString()!;
        double D(string key) => line.GetProperty(key).GetDouble();
        bool B(string key) => line.GetProperty(key).GetBoolean();
        int I(string key) => line.GetProperty(key).GetInt32();
        double? Opt(string key) => line.TryGetProperty(key, out var value) ? value.GetDouble() : null;
        return name switch
        {
            "start" => Command.Start,
            "agree" => Command.Agree,
            "not_now" => Command.NotNow,
            "retry_setup" => Command.RetrySetup,
            "open" => Command.Open(S("path")),
            "cancel" => Command.Cancel,
            "retry" => Command.Retry,
            "close" => Command.Close,
            "pages" => Command.Pages(D("width"), Opt("zoom")),
            "a4_pages" => Command.A4Pages,
            "export_musicxml" => Command.ExportMusicXml(S("dest")),
            "drum_track_cost" => Command.DrumTrackCost,
            "export_drum_track" => Command.ExportDrumTrack(S("dest")),
            "forget_recent" => Command.ForgetRecent(S("path")),
            "settings" => Command.Settings,
            "set_zoom" => Command.SetZoom(D("zoom")),
            "zoom_in" => Command.ZoomIn,
            "zoom_out" => Command.ZoomOut,
            "actual_size" => Command.ActualSize,
            "removal_sizes" => Command.RemovalSizes,
            "remove_models" => Command.RemoveModels(B("everything")),
            "back_up" => Command.BackUp(S("dest")),
            "backup_summary" => Command.BackupSummary(S("src")),
            "restore" => Command.Restore(S("src")),
            "uninstall_sizes" => Command.UninstallSizes,
            "uninstall" => Command.Uninstall(B("everything")),
            "jump" => Command.Jump(I("bar"), D("at")),
            "step" => Command.StepBy(D("at"), I("by")),
            "volumes" => Command.Volumes(S("hear"), Opt("song"), Opt("hits")),
            "playable" => Command.Playable,
            "quit" => Command.Quit,
            _ => throw new AssertFailedException($"the client has no command \"{name}\""),
        };
    }

    [GeneratedRegex(@"^## (?<section>[^\n]+)$|^### (?<heading>[^\n]+)$|```json\n(?<json>.*?)```", RegexOptions.Multiline | RegexOptions.Singleline)]
    private static partial Regex Parts();
}
