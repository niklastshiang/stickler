namespace Stickler.Core;

/// <summary>Which core the Windows app starts and with what: the core the installer put next
/// to the app (SPEC.md, module <c>win-package</c>, scope 2), or in a Debug build the bridge
/// in a Stickler checkout (module <c>win-shell</c>, "Where the core is").</summary>
public static class CoreLaunch
{
    /// <summary>The installed core's folder next to <c>Stickler.exe</c>.</summary>
    public const string CoreFolder = "core";

    /// <summary>Variables of the user's that would make the installed core's Python or uv use
    /// something else than what the app brings: dropped before the core starts.</summary>
    public static readonly IReadOnlyList<string> Drops = ["PYTHON", "VIRTUAL_ENV", "CONDA", "UV_"];

    /// <summary>Whether <paramref name="appFolder"/> holds an installed core.</summary>
    public static bool HasInstalledCore(string appFolder) =>
        System.IO.Directory.Exists(Path.Combine(appFolder, CoreFolder));

    /// <summary>The installed core in <paramref name="appFolder"/> (the installer's layout,
    /// SPEC.md, module <c>win-package</c>, scope 1): its Python runs the bridge as a module,
    /// with Stickler's own <c>uv</c>, ffmpeg and ffprobe first on the <c>PATH</c> and then
    /// only Windows' own folders, so a <c>uv</c> or ffmpeg of the user's is never taken. The
    /// core finds its adapters' sources below its Python itself (module <c>win-spike</c>).
    /// A missing part is named and the core not started.</summary>
    public static CoreClient Installed(
        string appFolder, IReadOnlyDictionary<string, string?> environment, IEnumerable<string> languages)
    {
        ArgumentNullException.ThrowIfNull(environment);
        var core = Path.Combine(appFolder, CoreFolder);
        var bin = Path.Combine(core, "bin");
        var python = Path.Combine(core, "python", "python.exe");
        var system = environment.TryGetValue("SystemRoot", out var root) && !string.IsNullOrEmpty(root)
            ? root
            : @"C:\Windows";
        var path = string.Join(';', bin, Path.Combine(system, "System32"), system,
            Path.Combine(system, "System32", "Wbem"));
        return new CoreClient(
            python,
            ["-m", "stickler_app.bridge"],
            core,
            new Dictionary<string, string>
            {
                ["STICKLER_PACKAGED"] = "windows",
                ["LANGUAGE"] = GettextLanguages(languages),
                ["UV_SYSTEM_CERTS"] = "1",
                ["PYTHONUTF8"] = "1",
                ["PATH"] = path,
            },
            needs:
            [
                python,
                Path.Combine(bin, "uv.exe"),
                Path.Combine(bin, "ffmpeg.exe"),
                Path.Combine(bin, "ffprobe.exe"),
                Path.Combine(core, "python", "share", "stickler", "adapters"),
            ],
            drops: Drops);
    }

    /// <summary>The variable a development build reads the Stickler checkout from.</summary>
    public const string CheckoutVariable = "STICKLER_CHECKOUT";

    /// <summary>The checkout to run the core from: <c>STICKLER_CHECKOUT</c> when it is set,
    /// else the first folder at or above <paramref name="start"/> that holds
    /// <c>pyproject.toml</c> and <c>adapters</c> (a build inside the checkout finds it by
    /// itself); null when there is none.</summary>
    public static string? FindCheckout(IReadOnlyDictionary<string, string?> environment, string start)
    {
        ArgumentNullException.ThrowIfNull(environment);
        if (environment.TryGetValue(CheckoutVariable, out var named) && !string.IsNullOrEmpty(named))
        {
            return IsCheckout(named) ? Path.GetFullPath(named) : null;
        }
        for (var folder = new DirectoryInfo(start); folder is not null; folder = folder.Parent)
        {
            if (IsCheckout(folder.FullName))
            {
                return folder.FullName;
            }
        }
        return null;
    }

    public static bool IsCheckout(string folder) =>
        File.Exists(Path.Combine(folder, "pyproject.toml")) && Directory.Exists(Path.Combine(folder, "adapters"));

    /// <summary>Where <c>uv</c> is: on the <c>PATH</c>, else where winget and uv's own
    /// installer put it; null when it is nowhere.</summary>
    public static string? FindUv(IReadOnlyDictionary<string, string?> environment, bool windows)
    {
        ArgumentNullException.ThrowIfNull(environment);
        var name = windows ? "uv.exe" : "uv";
        var separator = windows ? ';' : ':';
        var folders = new List<string>();
        if (environment.TryGetValue("PATH", out var path) && path is not null)
        {
            folders.AddRange(path.Split(separator, StringSplitOptions.RemoveEmptyEntries));
        }
        if (windows && environment.TryGetValue("LOCALAPPDATA", out var local) && !string.IsNullOrEmpty(local))
        {
            folders.Add(Path.Combine(local, "Microsoft", "WinGet", "Links"));
        }
        var home = environment.TryGetValue(windows ? "USERPROFILE" : "HOME", out var found) ? found : null;
        if (!string.IsNullOrEmpty(home))
        {
            folders.Add(Path.Combine(home, ".local", "bin"));
        }
        return folders.Select(folder => Path.Combine(folder.Trim('"'), name)).FirstOrDefault(File.Exists);
    }

    /// <summary><c>LANGUAGE</c> as gettext reads it, from the user's languages (BCP 47, best
    /// first): <c>de-DE</c> becomes <c>de_DE</c>, and the list ends with <c>en</c> at the
    /// first English entry, as the Mac app does.</summary>
    public static string GettextLanguages(IEnumerable<string> languages)
    {
        var translated = languages
            .TakeWhile(language => language != "en" && !language.StartsWith("en-", StringComparison.Ordinal))
            .Select(language => language.Replace('-', '_'));
        return string.Join(":", translated.Append("en"));
    }

    /// <summary>A development build's core: the bridge in <paramref name="checkout"/>'s
    /// environment, as an installed app (<c>STICKLER_PACKAGED=windows</c>: its files under
    /// <c>%LOCALAPPDATA%\Stickler</c>, its models set up from the checkout's adapters). It runs
    /// as <c>python -m stickler_app.bridge</c>, not through the <c>stickler-bridge.exe</c>
    /// uv writes for the entry point: that small program has a hash of its own, which an
    /// antivirus like the owner's holds back for a while, while the environment's
    /// <c>python.exe</c> is the same file in every environment of one uv release (found
    /// 2026-11-25). uv trusts the system's certificates, so a company network that inspects
    /// TLS does not stop it (SPEC.md, module <c>win-shell</c>, assumption 3).
    /// <para><paramref name="ownModels"/>: the models are set up elsewhere already
    /// (<c>STICKLER_ADAPTERS</c>, such as the stand-ins of the screenshots). The core then runs
    /// as the checkout's tests run it, not as an installed one: an installed core copies the
    /// checkout's adapters over those models and wants uv's Python in its own folders, which
    /// models set up elsewhere were not made with (found 2026-11-26 on the runner).</para></summary>
    public static CoreClient Checkout(string checkout, string uv, IEnumerable<string> languages, bool ownModels = false)
    {
        var adapters = Path.Combine(checkout, "adapters");
        var environment = new Dictionary<string, string>
        {
            ["LANGUAGE"] = GettextLanguages(languages),
            ["UV_SYSTEM_CERTS"] = "1",
            ["PYTHONUTF8"] = "1",
        };
        if (!ownModels)
        {
            environment["STICKLER_PACKAGED"] = "windows";
            environment["STICKLER_ADAPTER_SOURCES"] = adapters;
        }
        return new CoreClient(
            uv,
            ["run", "--project", checkout, "python", "-m", "stickler_app.bridge"],
            checkout,
            environment,
            needs: [uv, adapters]);
    }

    /// <summary>The app's core for this process: the installed core next to the app; else, in a
    /// Debug build (<paramref name="development"/>), the checkout it finds; else a core that
    /// ends at once and says what is missing. A Release build never reads
    /// <c>STICKLER_CHECKOUT</c>.</summary>
    public static CoreClient ForApp(
        IReadOnlyDictionary<string, string?> environment,
        string start,
        bool windows,
        IEnumerable<string> languages,
        bool development)
    {
        if (HasInstalledCore(start))
        {
            return Installed(start, environment, languages);
        }
        if (!development)
        {
            return new CoreClient(
                Path.Combine(start, CoreFolder, "python", "python.exe"),
                [],
                needs: [$"this Stickler is incomplete: its folder \"{CoreFolder}\" is missing next to Stickler.exe; install Stickler again"]);
        }
        var checkout = FindCheckout(environment, start);
        var uv = FindUv(environment, windows);
        if (checkout is null || uv is null)
        {
            var missing = new List<string>();
            if (checkout is null)
            {
                missing.Add($"no Stickler checkout found: set {CheckoutVariable}");
            }
            if (uv is null)
            {
                missing.Add("uv not found on PATH");
            }
            return new CoreClient(uv ?? "uv", ["run", "stickler-bridge"], needs: missing);
        }
        var ownModels = environment.TryGetValue("STICKLER_ADAPTERS", out var models) && !string.IsNullOrEmpty(models);
        return Checkout(checkout, uv, languages, ownModels);
    }
}
