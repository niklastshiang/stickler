namespace Stickler.Core.Tests;

/// <summary>The Playback menu (SPEC.md, <c>win-playback</c>, scope 6; the Mac's
/// <c>ControlsMenuTests</c>), with the core played by the fakes of the playback tests.</summary>
[TestClass]
public sealed class PlaybackMenuTests
{
    private static readonly string Tables = Path.Combine(Repo.Root, "win", "Stickler", "Strings");

    private static async Task<PlaybackHarness> Ready(FakePlayer? player = null)
    {
        var harness = PlaybackHarness.Playing(player ?? new FakePlayer());
        harness.Core.Emit(PlaybackHarness.PlayingResult(1));
        Assert.IsTrue(await harness.Settled(() => PlaybackMenu.Enabled(harness.Model)));
        return harness;
    }

    [TestMethod]
    public async Task TheEntriesAndTheirKeysAreInTheMenusOrder()
    {
        var harness = await Ready();
        var entries = harness.Read(() => PlaybackMenu.Entries(harness.Playback, Strings.English));
        Assert.AreEqual("Play|Previous Bar|Next Bar|Go to the Start", string.Join('|', entries.Select(e => e.Title)));
        Assert.AreEqual("Space|Left|Right|Home", string.Join('|', entries.Select(e => e.Key)));
        Assert.AreEqual("Space|Left|Right|Home", string.Join('|', entries.Select(e => e.KeyName)));
        var hearing = harness.Read(() => PlaybackMenu.Hearing(harness.Playback, Strings.English));
        Assert.AreEqual("Song|Hits|Both", string.Join('|', hearing.Select(c => c.Title)));
        Assert.AreEqual("Song|Hits|Both", string.Join('|', hearing.Select(c => c.Hear)));
        Assert.AreEqual("Playback", PlaybackMenu.MenuTitle(Strings.English));
    }

    [TestMethod]
    public async Task TheCurrentHearingIsTheCheckedOne()
    {
        var harness = await Ready();
        Assert.AreEqual(Hear.Both, harness.Playback.Hear);
        Assert.AreEqual(Hear.Both, harness.Read(() => PlaybackMenu.Hearing(harness.Playback, Strings.English)).Single(c => c.IsChecked).Hear);
        harness.Ui(() => harness.Playback.SetHear(Hear.Hits));
        Assert.AreEqual(Hear.Hits, harness.Read(() => PlaybackMenu.Hearing(harness.Playback, Strings.English)).Single(c => c.IsChecked).Hear);
        harness.Ui(() => harness.Playback.SetHear(Hear.Song));
        Assert.AreEqual(Hear.Song, harness.Read(() => PlaybackMenu.Hearing(harness.Playback, Strings.English)).Single(c => c.IsChecked).Hear);
    }

    [TestMethod]
    public async Task TheFirstEntrySaysWhatSpaceDoesNow()
    {
        var harness = await Ready();
        Assert.AreEqual("Play", PlaybackMenu.PlayTitle(harness.Playback, Strings.English));
        Assert.IsTrue(harness.Read(() => PlaybackMenu.Press(harness.Model, PlaybackKey.Space)));
        Assert.IsTrue(await harness.Settled(() => harness.Playback.Playing));
        Assert.AreEqual("Pause", harness.Read(() => PlaybackMenu.PlayTitle(harness.Playback, Strings.English)));
        Assert.AreEqual("Pause", harness.Read(() => PlaybackMenu.Entries(harness.Playback, Strings.English))[0].Title);
        Assert.IsTrue(harness.Read(() => PlaybackMenu.Press(harness.Model, PlaybackKey.Space)));
        Assert.IsFalse(harness.Read(() => harness.Playback.Playing));
    }

    [TestMethod]
    public async Task TheTitlesAreInTheReadersLanguage()
    {
        var harness = await Ready();
        var german = Strings.Load(Tables, ["de-DE"]);
        var entries = harness.Read(() => PlaybackMenu.Entries(harness.Playback, german));
        Assert.AreEqual("Abspielen|Vorheriger Takt|Nächster Takt|Zum Anfang", string.Join('|', entries.Select(e => e.Title)));
        Assert.AreEqual("Song|Schläge", string.Join('|', PlaybackMenu.Hearing(harness.Playback, german).Take(2).Select(c => c.Title)));
        Assert.AreEqual("Wiedergabe", PlaybackMenu.MenuTitle(german));
        harness.Ui(harness.Playback.Toggle);
        Assert.IsTrue(await harness.Settled(() => harness.Playback.Playing));
        Assert.AreEqual("Pausieren", harness.Read(() => PlaybackMenu.PlayTitle(harness.Playback, german)));
    }

    [TestMethod]
    public async Task EachKeyTellsThePlaybackModel()
    {
        var player = new FakePlayer();
        var harness = await Ready(player);
        harness.Core.Answer("step", "\"ok\": true, \"seconds\": 4.0");
        Assert.IsTrue(harness.Read(() => PlaybackMenu.Press(harness.Model, PlaybackKey.Right)));
        Assert.IsTrue(await harness.Settled(() => harness.Playback.Position == 4));
        Assert.IsTrue(harness.Read(() => PlaybackMenu.Press(harness.Model, PlaybackKey.Left)));
        Assert.IsTrue(await harness.Settled(() => harness.Count("step") == 2));
        Assert.AreEqual(Command.StepBy(4, -1).Line(0), harness.Core.Asked("step")[1]);
        harness.Ui(() => harness.Playback.Seek(9));
        Assert.IsTrue(harness.Read(() => PlaybackMenu.Press(harness.Model, PlaybackKey.Home)));
        Assert.AreEqual(0, harness.Read(() => harness.Playback.Position));
    }

    [TestMethod]
    public async Task TheEntriesWorkOnlyWithAResult()
    {
        var harness = await Ready();
        Assert.IsTrue(harness.Read(() => PlaybackMenu.Enabled(harness.Model)));
        harness.Core.Emit(PlaybackHarness.EmptyEvent(2));
        Assert.IsTrue(await harness.Settled(() => !PlaybackMenu.Enabled(harness.Model)), "no result");
        Assert.IsFalse(harness.Read(() => PlaybackMenu.Press(harness.Model, PlaybackKey.Space)));

        var before = new PlaybackHarness(new FakePlayer());
        Assert.IsFalse(before.Read(() => PlaybackMenu.Enabled(before.Model)), "before the launch");
        var silent = new PlaybackHarness(null);
        silent.Ui(silent.Model.Launch);
        silent.Core.Emit(PlaybackHarness.PlayingResult(1));
        Assert.IsTrue(await silent.Settled(() => silent.Playback.Length == 12));
        Assert.IsFalse(silent.Read(() => PlaybackMenu.Enabled(silent.Model)), "no player");
    }

    [TestMethod]
    public async Task TypingKeepsTheKeys()
    {
        var player = new FakePlayer();
        var harness = await Ready(player);
        foreach (var key in Enum.GetValues<PlaybackKey>())
        {
            Assert.IsFalse(PlaybackMenu.Handles(key, typing: true), key.ToString());
            Assert.IsTrue(PlaybackMenu.Handles(key, typing: false), key.ToString());
            Assert.IsFalse(harness.Read(() => PlaybackMenu.Press(harness.Model, key, typing: true)), key.ToString());
        }
        Assert.IsFalse(PlaybackMenu.Handles((PlaybackKey)99, typing: false));
        Assert.IsFalse(harness.Read(() => harness.Playback.Playing));
        Assert.IsEmpty(player.Loads);
        Assert.AreEqual(0, harness.Playback.Position);
    }
}
