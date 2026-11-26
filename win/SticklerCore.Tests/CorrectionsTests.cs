namespace Stickler.Core.Tests;

/// <summary>The corrections' logic (SPEC.md, "Mac corrections" and module <c>win-corrections</c>):
/// the state's <c>controls</c>, each change's command, the sheet's pages, the pane's decisions
/// and the export rule, with the core played by <see cref="FakeCore"/>. The Mac's
/// <c>AppModelTests</c>, <c>SheetModelTests</c> and <c>CorrectionsTests</c> ported.</summary>
[TestClass]
public sealed class CorrectionsTests
{
    private static readonly string Tables = Path.Combine(Repo.Root, "win", "Stickler", "Strings");

    private readonly List<FakeCore> cores = [];

    /// <summary>A result as the core sends it; <paramref name="controls"/> false is a core from
    /// before the corrections, <paramref name="exportable"/> false a line without <c>can_export</c>.</summary>
    private static string ResultLine(
        int seq,
        string song = "/m/e.flac",
        string tempo = "normal",
        bool simplify = true,
        bool correcting = false,
        int? sheet = 1,
        bool controls = true,
        bool exportable = true)
    {
        var corrected = tempo != "normal" || !simplify;
        var shown = "\"controls\": {\"tempo\": \"" + tempo + "\", \"beats_per_bar\": 4, \"fewer\": true, \"more\": true, "
            + "\"first_one\": 1, \"first_one_label\": \"Beat 1\", \"earlier\": false, \"later\": true, "
            + $"\"simplify\": {Flag(simplify)}, \"repeats\": true, \"corrected\": {Flag(corrected)}}}, ";
        var state = "{\"kind\": \"result\", \"song\": \"" + song + "\", \"title\": \"Eye of the Tiger\", "
            + "\"subtitle\": \"Survivor · ♩ = 109 · 4/4\", \"artist\": \"Survivor\", \"seconds\": 246.0, \"tempo\": 109, "
            + "\"meter\": [4, 4], \"musicxml\": \"/c/e.musicxml\", \"corrections\": {\"tempo\": \"" + tempo
            + "\", \"beats_per_bar\": null, \"first_downbeat\": null, \"simplify\": " + Flag(simplify) + ", \"repeats\": true}, "
            + $"\"correcting\": {Flag(correcting)}, "
            + (controls ? shown : "")
            + (sheet is { } number ? $"\"sheet\": {number}, " : "")
            + "\"can_open\": true, \"can_close\": true" + (exportable ? ", \"can_export\": true" : "") + "}";
        return $"{{\"event\": \"state\", \"seq\": {seq}, \"state\": {state}}}";
    }

    private static string Flag(bool value) => value ? "true" : "false";

    private static string ExportingLine(int seq) =>
        $"{{\"event\": \"state\", \"seq\": {seq}, \"state\": {{\"kind\": \"exporting\", \"song\": \"/m/e.flac\", \"title\": \"Eye of the Tiger\", \"subtitle\": \"Survivor\", \"dest\": \"/d/e.pdf\", \"steps\": []}}}}";

    private static string EmptyLine(int seq) => $"{{\"event\": \"state\", \"seq\": {seq}, \"state\": {{\"kind\": \"empty\", \"can_open\": true}}}}";

    private const string PagesReply =
        "\"ok\": true, \"zoom\": 1.0, \"pages\": [{\"svg\": \"<svg/>\", \"width\": 800.0, \"height\": 300.0, \"bars\": []}]";

    private static async Task<bool> Settled(Func<bool> condition) => await Recorder.Eventually(condition, 10);

    private (AppModel Model, FakeCore Core) Running(TimeSpan? settle = null)
    {
        var model = new AppModel(
            ["en"],
            _ =>
            {
                var core = new FakeCore();
                cores.Add(core);
                return core;
            },
            work => work(),
            settle ?? TimeSpan.FromMilliseconds(20));
        model.Launch();
        return (model, cores[^1]);
    }

    private (AppModel Model, FakeCore Core) Showing(string line)
    {
        var (model, core) = Running();
        core.Emit(line);
        return (model, core);
    }

    private static int PagesAsked(FakeCore core) =>
        core.All.Count(line => line.Contains("\"cmd\":\"pages\"", StringComparison.Ordinal));

    // decoding

    private static ResultScreen Read(string line) => (ResultScreen)((StateEvent)Incoming.Parse(line)).State.Screen;

    [TestMethod]
    public void AResultCarriesTheControlsTheCoreShowsAndWhetherACorrectionIsWritten()
    {
        var result = Read(ResultLine(1, tempo: "half", simplify: false, correcting: true, sheet: 4));
        Assert.AreEqual(
            new CorrectionControls(Tempo.Halved, 4, true, true, 1, "Beat 1", false, true, false, true, true),
            result.Controls);
        Assert.IsTrue(result.Correcting);
        Assert.AreEqual(4, result.Sheet);
        Assert.AreEqual(Tempo.Normal, Read(ResultLine(1)).Controls!.Tempo);
        Assert.AreEqual(Tempo.Doubled, Read(ResultLine(1, tempo: "double")).Controls!.Tempo);
        Assert.IsFalse(Read(ResultLine(1)).Controls!.Corrected);
        Assert.IsFalse(Read(ResultLine(1)).Correcting);
    }

    [TestMethod]
    public void AResultFromBeforeTheCorrectionsHasNoControlsAndNoSheet()
    {
        var result = Read(ResultLine(1, controls: false, sheet: null));
        Assert.IsNull(result.Controls);
        Assert.AreEqual(0, result.Sheet);
        Assert.IsFalse(result.Correcting);
    }

    [TestMethod]
    public void AnUnknownTempoOrAMissingControlFieldIsUnreadable()
    {
        Assert.ThrowsExactly<UnreadableLineException>(() => Incoming.Parse(ResultLine(1, tempo: "triple")));
        var missing = ResultLine(1).Replace("\"fewer\": true, ", "", StringComparison.Ordinal);
        Assert.ThrowsExactly<UnreadableLineException>(() => Incoming.Parse(missing));
    }

    [TestMethod]
    public void TheDocumentsResultExampleCarriesItsControls()
    {
        var document = File.ReadAllText(Path.Combine(Repo.Root, "docs", "bridge.md"));
        var line = document.Split('\n').Single(l => l.StartsWith("{\"kind\": \"result\"", StringComparison.Ordinal));
        var result = (ResultScreen)AppState.Parse(line).Screen;
        Assert.AreEqual(
            new CorrectionControls(Tempo.Normal, 4, true, true, 1, "Beat 1", false, true, true, true, false),
            result.Controls);
        Assert.IsFalse(result.Correcting);
    }

    // the commands

    [TestMethod]
    public async Task EachCorrectionSendsItsChangeInTheReadersOrderAndQuickStepsGoOutAsSteps()
    {
        var (model, core) = Running();
        Correction[] changes =
        [
            Correction.HalfTempo, Correction.BeatsPerBar(3), Correction.BeatsPerBarBy(1), Correction.BeatsPerBarBy(1),
            Correction.FirstOne(2), Correction.FirstOneBy(-1), Correction.Simplify(false), Correction.Repeats(false),
            Correction.Detected,
        ];
        foreach (var change in changes)
        {
            model.Correct(change);
        }
        Assert.IsTrue(await Settled(() => core.Sent.Count == changes.Length + 1));
        Assert.AreEqual(
            string.Join('\n', [Command.Start.Line(0), .. changes.Select(c => Command.Correct(c).Line(0))]),
            string.Join('\n', core.Sent));
        Assert.AreEqual(2, core.Sent.Count(line => line == Command.Correct(Correction.BeatsPerBarBy(1)).Line(0)));
    }

    [TestMethod]
    public async Task ARefusedCorrectionIsTheWindowsNotice()
    {
        var (model, core) = Running();
        core.Answer("correct", "\"ok\": false, \"error\": {\"code\": \"not_now\", \"message\": \"Das geht gerade nicht.\"}");
        model.Correct(Correction.Simplify(true));
        Assert.IsTrue(await Settled(() => model.Notice is not null));
        Assert.AreEqual("Das geht gerade nicht.", model.Notice!.Text);
    }

    [TestMethod]
    public async Task ACorrectionWithoutACoreSendsNothing()
    {
        var model = new AppModel(["en"], _ => new FakeCore(), work => work());
        model.Correct(Correction.Detected); // before Launch: no outbox
        await model.QuitAsync();
        Assert.IsNull(model.Notice);
    }

    // the sheet's pages

    [TestMethod]
    public async Task PagesAreFetchedOncePerNewSheetAndNotWhenACorrectionStarts()
    {
        var (model, core) = Running();
        core.Answer("pages", PagesReply);
        model.Sheet.Resize(800);
        core.Emit(ResultLine(1));
        Assert.IsTrue(await Settled(() => PagesAsked(core) == 1));
        core.Emit(ResultLine(2, correcting: true)); // the same music
        core.Emit(ExportingLine(3));
        core.Emit(ResultLine(4));
        await Task.Delay(100);
        Assert.AreEqual(1, PagesAsked(core));
        Assert.AreEqual(1, model.Sheet.Pages.Count); // an export keeps the sheet

        // a correction starts: the notes are still the old ones, so no new pages yet
        core.Emit(ResultLine(5, tempo: "double", correcting: true));
        await Task.Delay(100);
        Assert.AreEqual(1, PagesAsked(core));
        core.Emit(ResultLine(6, tempo: "double", sheet: 2)); // its notes
        Assert.IsTrue(await Settled(() => PagesAsked(core) == 2));
        core.Emit(ResultLine(7, song: "/m/other.flac", sheet: 3)); // a song
        Assert.IsTrue(await Settled(() => PagesAsked(core) == 3));
    }

    // the pane

    [TestMethod]
    public void OnlyAResultWithControlsCanBeCorrected()
    {
        var (empty, _) = Showing(EmptyLine(1));
        Assert.IsNull(CorrectionsPane.Controls(empty));
        Assert.IsFalse(CorrectionsPane.Enabled(empty));
        Assert.IsFalse(CorrectionsPane.Presented(true, empty)); // remembered, not shown
        Assert.IsFalse(CorrectionsPane.Correcting(empty));

        var (older, _) = Showing(ResultLine(1, controls: false));
        Assert.IsInstanceOfType<ResultScreen>(older.State.Screen);
        Assert.IsFalse(CorrectionsPane.Enabled(older)); // a core from before the corrections

        var (shown, _) = Showing(ResultLine(1, simplify: false));
        var controls = CorrectionsPane.Controls(shown)!;
        Assert.AreEqual("Beat 1", controls.FirstOneLabel);
        Assert.IsTrue(controls.Corrected);
        Assert.IsTrue(CorrectionsPane.Enabled(shown));
        Assert.IsTrue(CorrectionsPane.Presented(true, shown));
        Assert.IsFalse(CorrectionsPane.Presented(false, shown));
        Assert.IsFalse(CorrectionsPane.Correcting(shown));

        var (exporting, _) = Showing(ExportingLine(1));
        Assert.IsFalse(CorrectionsPane.Enabled(exporting)); // the core would refuse
    }

    [TestMethod]
    public void AStoppedCoreHasNothingToCorrect()
    {
        var (model, core) = Showing(ResultLine(1, correcting: true));
        Assert.IsTrue(CorrectionsPane.Enabled(model));
        Assert.IsTrue(CorrectionsPane.Correcting(model));
        core.Stop(new CoreEnd(CoreEndReason.Exited, 1, "", []));
        Assert.AreEqual(Phase.Stopped, model.Phase);
        Assert.IsFalse(CorrectionsPane.Enabled(model));
        Assert.IsFalse(CorrectionsPane.Correcting(model));
        Assert.IsFalse(WindowView.CanExport(model));
    }

    [TestMethod]
    public void TheMenuItemSaysWhatItDoesInTheReadersLanguage()
    {
        Assert.AreEqual("Show Corrections", CorrectionsPane.Title(false, Strings.English));
        Assert.AreEqual("Hide Corrections", CorrectionsPane.Title(true, Strings.English));
        var german = Strings.Load(Tables, ["de-DE"]);
        Assert.AreEqual("Korrekturen einblenden", CorrectionsPane.Title(false, german));
        Assert.AreEqual("Korrekturen ausblenden", CorrectionsPane.Title(true, german));
    }

    [TestMethod]
    public void TheSpinnerTurnsWhileACorrectionIsWritten()
    {
        var (writing, _) = Showing(ResultLine(1, tempo: "half", correcting: true));
        Assert.IsTrue(CorrectionsPane.Correcting(writing));
        var (written, _) = Showing(ResultLine(1, tempo: "half"));
        Assert.IsFalse(CorrectionsPane.Correcting(written));
    }

    [TestMethod]
    public void EveryTextOfTheCorrectionsIsTranslated()
    {
        var german = Strings.Load(Tables, ["de-DE"]);
        string[] texts =
        [
            "Corrections", "Beat", "Tempo", "Half", "As Detected", "Double", "Beats per bar", "First “one”",
            "Beats before it are a pickup", "Easier to Read", "Simplify", "Nearly equal bars get one pattern",
            "Repeat signs", "Equal bars are written once", "Back to Detected", "Show Corrections", "Hide Corrections",
        ];
        foreach (var text in texts.Where(t => t is not ("Beat" or "Tempo"))) // German says them the same
        {
            Assert.AreNotEqual(text, german.Text(text), text);
        }
    }

    // exports

    [TestMethod]
    public void ExportIsOffWhileACorrectionIsWrittenAndFlowsFindNoResultThen()
    {
        var (writing, _) = Showing(ResultLine(1, tempo: "half", correcting: true));
        Assert.IsFalse(WindowView.CanExport(writing));
        Assert.IsNull(new Flows(writing, null!, Strings.English).Result);
        var (written, _) = Showing(ResultLine(1, tempo: "half"));
        Assert.IsTrue(WindowView.CanExport(written));
        Assert.IsNotNull(new Flows(written, null!, Strings.English).Result);
        var (refused, _) = Showing(ResultLine(1, exportable: false));
        Assert.IsFalse(WindowView.CanExport(refused)); // the core's own say
        var (exporting, _) = Showing(ExportingLine(1));
        Assert.IsFalse(WindowView.CanExport(exporting));
        Assert.IsFalse(WindowView.CanExport(Running().Model));
    }
}
