namespace Stickler.Core.Tests;

[TestClass]
public sealed class IncomingTests
{
    [TestMethod]
    [DataRow("not json")]
    [DataRow("[1, 2]")]
    [DataRow("{\"id\": 3}")]
    [DataRow("{\"event\": \"state\", \"seq\": 1, \"state\": {\"can_open\": true}}")]
    [DataRow("{\"event\": \"state\", \"seq\": 1, \"state\": {\"kind\": \"analysing\", \"song\": 3}}")]
    [DataRow("{\"event\": \"state\", \"seq\": 1, \"state\": {\"kind\": \"failed\", \"song\": \"/a\", \"name\": \"a\", \"reason\": \"lost\", \"title\": \"\", \"description\": \"\", \"details\": \"\"}}")]
    [DataRow("{\"event\": \"state\", \"seq\": 1, \"state\": {\"kind\": \"setting_up\", \"song\": null, \"steps\": [{\"id\": \"a\", \"label\": \"\", \"detail\": \"\", \"state\": \"paused\"}]}}")]
    [DataRow("{\"event\": \"recent\", \"seq\": 1, \"rows\": 3}")]
    [DataRow("{\"event\": \"hello\", \"protocol\": \"one\", \"version\": \"11\", \"language\": \"en\"}")]
    [DataRow("{\"id\": 1, \"ok\": \"yes\"}")]
    public void ALineTheClientCannotReadSaysSo(string line) =>
        Assert.ThrowsExactly<UnreadableLineException>(() => Incoming.Parse(line));

    [TestMethod]
    public void AnUnknownEventAndAnUnknownKindAreKeptAsSuch()
    {
        Assert.AreEqual(new UnknownEvent(4, "progress"), Incoming.Parse("{\"event\": \"progress\", \"seq\": 4}"));
        var state = (StateEvent)Incoming.Parse("{\"event\": \"state\", \"seq\": 5, \"state\": {\"kind\": \"correcting\"}}");
        Assert.AreEqual(new UnknownScreen("correcting"), state.State.Screen);
        Assert.AreEqual(new Abilities(), state.State.Can); // a field not sent means "not allowed"
    }

    [TestMethod]
    public void AReplyWithoutAnIdOrErrorStillReads()
    {
        var bad = Reply.Parse("{\"id\": null, \"ok\": false, \"error\": {\"code\": \"bad_request\", \"message\": \"No.\"}}");
        Assert.IsNull(bad.Id);
        Assert.IsFalse(bad.Ok);
        Assert.AreEqual("bad_request", bad.Error!.Code);
        var bare = Reply.Parse("{\"id\": 2, \"ok\": false}");
        Assert.AreEqual(new BridgeError("internal", ""), bare.Error);
    }

    [TestMethod]
    public void AnOlderResultWithoutClicksOrBarsPlaysNothing()
    {
        var state = AppState.Parse(
            "{\"kind\": \"result\", \"song\": \"/a.flac\", \"title\": \"A\", \"subtitle\": \"\", \"artist\": \"\", "
            + "\"seconds\": 1.5, \"tempo\": 90, \"meter\": [3, 4], \"musicxml\": \"/a.musicxml\", \"can_export\": true}");
        var result = (ResultScreen)state.Screen;
        Assert.IsNull(result.Clicks);
        Assert.IsEmpty(result.Bars);
        Assert.IsTrue(state.Can.Export);
    }

    [TestMethod]
    public void EveryFailureReasonAndStepStateReads()
    {
        foreach (var (name, reason) in new[] { ("unreadable", FailureReason.Unreadable), ("analysis", FailureReason.Analysis), ("export", FailureReason.Export) })
        {
            var state = AppState.Parse(
                $"{{\"kind\": \"failed\", \"song\": \"/a\", \"name\": \"a\", \"reason\": \"{name}\", \"title\": \"T\", \"description\": \"D\", \"details\": \"x\"}}");
            Assert.AreEqual(reason, ((FailedScreen)state.Screen).Reason);
        }
        var steps = (SettingUpScreen)AppState.Parse(
            "{\"kind\": \"setting_up\", \"song\": \"/s.flac\", \"steps\": ["
            + "{\"id\": \"a\", \"label\": \"A\", \"detail\": \"\", \"state\": \"done\"},"
            + "{\"id\": \"b\", \"label\": \"B\", \"detail\": \"\", \"state\": \"waiting\"}]}").Screen;
        Assert.AreEqual("/s.flac", steps.Song);
        CollectionAssert.AreEqual(new[] { StepProgress.Done, StepProgress.Waiting }, steps.Steps.Select(s => s.State).ToArray());
    }
}

[TestClass]
public sealed class CommandTests
{
    [TestMethod]
    public void ALineIsCompactJsonWithIdAndNameFirst()
    {
        Assert.AreEqual("{\"id\":7,\"cmd\":\"open\",\"path\":\"C:\\\\Music\\\\a.flac\"}", Command.Open(@"C:\Music\a.flac").Line(7));
        Assert.AreEqual("{\"id\":1,\"cmd\":\"remove_models\",\"everything\":true}", Command.RemoveModels(true).Line(1));
        Assert.DoesNotContain("\n", Command.Open("a\nb").Line(1));
    }

    [TestMethod]
    public void OptionalArgumentsAreLeftOutWhenNotGiven()
    {
        Assert.AreEqual("{\"id\":1,\"cmd\":\"pages\",\"width\":800}", Command.Pages(800).Line(1));
        Assert.AreEqual("{\"id\":1,\"cmd\":\"volumes\",\"hear\":\"both\"}", Command.Volumes("both").Line(1));
        Assert.AreEqual("{\"id\":1,\"cmd\":\"volumes\",\"hear\":\"hits\",\"hits\":0.5}", Command.Volumes("hits", hits: 0.5).Line(1));
        Assert.AreEqual("{\"id\":0,\"cmd\":\"quit\"}", Command.Quit.ToString());
        Assert.HasCount(0, Command.Quit.Arguments);
    }
}
