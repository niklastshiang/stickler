namespace Stickler.Core.Tests;

/// <summary>The client against small fake cores written in Python, and against the real bridge
/// with the stand-in models (<c>scripts/bridge_stand_ins.py</c>, as the Mac's tests).</summary>
[TestClass]
public sealed class CoreClientTests
{
    [TestMethod]
    [Timeout(120_000, CooperativeCancellation = true)]
    public async Task RepliesFindTheirCommandsEvenOutOfOrder()
    {
        // answers the second command first; the events come in order before the replies
        using var core = Repo.FakeCore(Repo.Hello() + """
            got = [json.loads(raw) for _, raw in zip(range(2), lines())]
            say({'event': 'state', 'seq': 1, 'state': {'kind': 'empty', 'can_open': True}})
            say({'event': 'notice', 'seq': 2, 'text': 'hi', 'opens': None})
            say({'id': got[1]['id'], 'ok': True, 'which': got[1]['cmd']})
            say({'id': got[0]['id'], 'ok': True, 'which': got[0]['cmd']})
            """);
        var recorder = new Recorder();
        recorder.Start(core);
        var first = core.SendAsync(Command.Cancel);
        var second = core.SendAsync(Command.Close);
        Assert.AreEqual("cancel", (await first).Fields.GetProperty("which").GetString());
        Assert.AreEqual("close", (await second).Fields.GetProperty("which").GetString());
        Assert.IsTrue(await Recorder.Eventually(() => recorder.Ended is not null));
        var events = recorder.Events;
        Assert.IsInstanceOfType<HelloLine>(events[0]);
        Assert.AreEqual(AppState.Empty, ((StateEvent)events[1]).State);
        Assert.AreEqual(new Notice("hi", null), ((NoticeEvent)events[2]).Notice);
        Assert.AreEqual(CoreEndReason.Exited, recorder.Ended!.Reason);
        Assert.AreEqual(0, recorder.Ended.Code);
    }

    [TestMethod]
    [Timeout(120_000, CooperativeCancellation = true)]
    public async Task AnErrorReplyIsRefusedWithTheCoresReason()
    {
        using var core = Repo.FakeCore(Repo.Hello() + """
            for raw in lines():
                cmd = json.loads(raw)
                say({'id': cmd['id'], 'ok': False, 'error': {'code': 'not_now', 'message': 'Not now.'}})
            """);
        new Recorder().Start(core);
        var refused = await Assert.ThrowsExactlyAsync<CoreRefusedException>(() => core.SendAsync(Command.Retry));
        Assert.AreEqual(new BridgeError("not_now", "Not now."), refused.Error);
        await core.QuitAsync(1);
    }

    [TestMethod]
    [Timeout(120_000, CooperativeCancellation = true)]
    public async Task TheClientWritesOnlyNewlinesAndKeepsWhatTheCoreSaid()
    {
        // the core reports whether a line it got held "\r", writes a line it cannot read and
        // text on stderr, then exits with 3
        using var core = Repo.FakeCore(Repo.Hello() + """
            raw = next(lines())
            say({'id': json.loads(raw)['id'], 'ok': True, 'crlf': raw.endswith(b'\r\n')})
            sys.stdout.buffer.write(b'garbage\n'); sys.stdout.buffer.flush()
            sys.stderr.write('Traceback: something broke\n'); sys.stderr.flush()
            sys.exit(3)
            """);
        var recorder = new Recorder();
        recorder.Start(core);
        var reply = await core.SendAsync(Command.Open("C:\\Songs\\ä ö.flac"));
        Assert.IsFalse(reply.Fields.GetProperty("crlf").GetBoolean());
        Assert.IsTrue(await Recorder.Eventually(() => recorder.Ended is not null));
        var end = recorder.Ended!;
        Assert.AreEqual(CoreEndReason.Exited, end.Reason);
        Assert.AreEqual(3, end.Code);
        Assert.Contains("Traceback: something broke", end.Details);
        Assert.Contains("unreadable line from the core: garbage", end.Details);
        Assert.StartsWith("The core exited with status 3.", end.TechnicalDetails);
        Assert.IsFalse(end.NeverStarted);
        await Assert.ThrowsExactlyAsync<CoreNotRunningException>(() => core.SendAsync(Command.Cancel));
    }

    [TestMethod]
    [Timeout(120_000, CooperativeCancellation = true)]
    public async Task ACoreOfAnotherProtocolIsEnded()
    {
        using var core = Repo.FakeCore(Repo.Hello(protocol: 2) + "time.sleep(60)\n");
        var recorder = new Recorder();
        recorder.Start(core);
        Assert.IsTrue(await Recorder.Eventually(() => recorder.Ended is not null));
        Assert.AreEqual(CoreEndReason.WrongProtocol, recorder.Ended!.Reason);
        Assert.AreEqual("The core speaks protocol 2; this app speaks 1.", recorder.Ended.Summary);
        Assert.IsEmpty(recorder.Events); // the wrong hello is not handed on
    }

    [TestMethod]
    [Timeout(120_000, CooperativeCancellation = true)]
    public async Task ACoreThatIgnoresQuitIsEndedAtTheDeadlineWithItsChildren()
    {
        using var core = Repo.FakeCore(Repo.Hello() + """
            import signal, subprocess
            child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
            say({'event': 'notice', 'seq': 1, 'text': str(child.pid), 'opens': None})
            for raw in lines():
                pass  # never answers, and keeps running after stdin closes
            time.sleep(60)
            """);
        var recorder = new Recorder();
        recorder.Start(core);
        Assert.IsTrue(await Recorder.Eventually(() => recorder.Events.OfType<NoticeEvent>().Any()));
        var child = int.Parse(recorder.Events.OfType<NoticeEvent>().Single().Notice.Text, System.Globalization.CultureInfo.InvariantCulture);
        var started = DateTime.UtcNow;
        await core.QuitAsync(1);
        Assert.IsLessThan(10, (DateTime.UtcNow - started).TotalSeconds);
        Assert.IsFalse(core.IsRunning);
        Assert.IsNull(core.ProcessId);
        Assert.IsTrue(await Recorder.Eventually(() => !Alive(child), 10), "the core's child was left running");
    }

    [TestMethod]
    public async Task ACoreThatCannotStartSaysWhy()
    {
        using var nowhere = new CoreClient(Path.Combine(Path.GetTempPath(), "no-such-uv.exe"), ["run"]);
        var recorder = new Recorder();
        recorder.Start(nowhere);
        Assert.AreEqual(CoreEndReason.NotStarted, recorder.Ended!.Reason);
        Assert.IsTrue(recorder.Ended.NeverStarted);
        await Assert.ThrowsExactlyAsync<CoreNotRunningException>(() => nowhere.SendAsync(Command.Start));
        await nowhere.QuitAsync(0.1); // nothing to end

        using var partial = Repo.FakeCore("", needs: [Path.Combine(Path.GetTempPath(), "no-such-folder")]);
        var missing = new Recorder();
        missing.Start(partial);
        Assert.AreEqual("The core could not be started: parts of it are missing", missing.Ended!.Summary);
        Assert.StartsWith("missing: ", missing.Ended.Details.Single());
    }

    [TestMethod]
    [Timeout(120_000, CooperativeCancellation = true)]
    public async Task ACancelledWaitDropsItsReply()
    {
        using var core = Repo.FakeCore(Repo.Hello() + "for raw in lines():\n    pass\n");
        new Recorder().Start(core);
        using var cancel = new CancellationTokenSource(TimeSpan.FromMilliseconds(300));
        await Assert.ThrowsAsync<OperationCanceledException>(() => core.SendAsync(Command.Start, cancel.Token));
        core.Terminate();
    }

    [TestMethod]
    [Timeout(300_000, CooperativeCancellation = true)]
    public async Task TheRealBridgeTurnsASongIntoAResultAndQuits()
    {
        var (_, song) = Repo.StandIns.Value;
        using var core = Repo.Bridge();
        var recorder = new Recorder();
        recorder.Start(core);
        await core.SendAsync(Command.Start);
        Assert.IsTrue(await Recorder.Eventually(() => recorder.States().Any(s => s.Screen is EmptyScreen)));
        Assert.AreEqual(BridgeProtocol.Version, recorder.Events.OfType<HelloLine>().Single().Hello.Protocol);
        await core.SendAsync(Command.Open(song));
        Assert.IsTrue(
            await Recorder.Eventually(() => recorder.States().Any(s => s.Screen is ResultScreen or FailedScreen), 240),
            "no result");
        var last = recorder.States().Last(s => s.Screen is ResultScreen or FailedScreen);
        Assert.IsInstanceOfType<ResultScreen>(last.Screen, (last.Screen as FailedScreen)?.Details);
        Assert.IsTrue(last.Can.Export);
        await core.QuitAsync(5);
        Assert.IsTrue(await Recorder.Eventually(() => recorder.Ended is not null));
        Assert.AreEqual(0, recorder.Ended!.Code);
    }

    [TestMethod]
    [Timeout(120_000, CooperativeCancellation = true)]
    public async Task OnlyTheLastLinesAreKeptAndAWaitingCommandLearnsTheCoreIsGone()
    {
        using var core = Repo.FakeCore(Repo.Hello() + """
            next(lines())
            for i in range(45):
                sys.stderr.write(f'line {i}\n')
            for i in range(7):
                sys.stdout.buffer.write(f'garbage {i}\n'.encode())
            sys.stderr.flush(); sys.stdout.buffer.flush()
            sys.exit(1)
            """);
        var recorder = new Recorder();
        recorder.Start(core);
        await Assert.ThrowsExactlyAsync<CoreNotRunningException>(() => core.SendAsync(Command.Start));
        Assert.IsTrue(await Recorder.Eventually(() => recorder.Ended is not null));
        var details = recorder.Ended!.Details;
        Assert.HasCount(CoreClient.DetailLines + 5, details);
        Assert.AreEqual("line 5", details[0]);
        Assert.AreEqual("unreadable line from the core: garbage 6", details[^1]);
    }

    [TestMethod]
    [Timeout(120_000, CooperativeCancellation = true)]
    public async Task TheAppsOwnVariablesThatWouldLeadTheCoreAwayAreDropped()
    {
        System.Environment.SetEnvironmentVariable("STICKLER_TEST_AWAY", "elsewhere");
        try
        {
            using var core = new CoreClient(
                Repo.Uv,
                ["run", "--no-project", "python", "-c",
                    "import os, sys, json; sys.stdout.write(json.dumps({'event': 'notice', 'seq': 1, "
                    + "'text': repr((os.environ.get('STICKLER_TEST_AWAY'), os.environ.get('STICKLER_TEST_ADDED'))), 'opens': None}) + '\\n')"],
                environment: new Dictionary<string, string> { ["STICKLER_TEST_ADDED"] = "here" },
                drops: ["STICKLER_TEST_AWAY"]);
            var recorder = new Recorder();
            recorder.Start(core);
            Assert.IsTrue(await Recorder.Eventually(() => recorder.Ended is not null));
            Assert.AreEqual("(None, 'here')", recorder.Events.OfType<NoticeEvent>().Single().Notice.Text);
        }
        finally
        {
            System.Environment.SetEnvironmentVariable("STICKLER_TEST_AWAY", null);
        }
    }

    [TestMethod]
    public void TheExceptionsCarryTheirMessages()
    {
        Assert.AreEqual("x", new CoreNotRunningException("x").Message);
        Assert.AreEqual("y", new CoreNotRunningException("x", new IOException("y")).InnerException!.Message);
        Assert.AreEqual(new BridgeError("internal", ""), new CoreRefusedException().Error);
        Assert.AreEqual(new BridgeError("internal", "z"), new CoreRefusedException("z").Error);
        Assert.AreEqual("z", new CoreRefusedException("z", new IOException()).Error.Message);
        Assert.AreEqual("u", new UnreadableLineException("u").Message);
        Assert.IsNotNull(new UnreadableLineException().Message);
    }

    private static bool Alive(int pid)
    {
        try
        {
            using var process = System.Diagnostics.Process.GetProcessById(pid);
            return !process.HasExited;
        }
        catch (ArgumentException)
        {
            return false;
        }
    }
}
