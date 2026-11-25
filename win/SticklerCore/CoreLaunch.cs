namespace Stickler.Core;

/// <summary>Which core the Windows app starts and with what (SPEC.md, module <c>win-shell</c>,
/// "Where the core is"). Until <c>win-package</c> the app runs <c>uv run stickler-bridge</c>
/// in a Stickler checkout; the installer's own core comes with that module.</summary>
public static class CoreLaunch
{
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
    /// TLS does not stop it (SPEC.md, module <c>win-shell</c>, assumption 3).</summary>
    public static CoreClient Checkout(string checkout, string uv, IEnumerable<string> languages)
    {
        var adapters = Path.Combine(checkout, "adapters");
        return new CoreClient(
            uv,
            ["run", "--project", checkout, "python", "-m", "stickler_app.bridge"],
            checkout,
            new Dictionary<string, string>
            {
                ["STICKLER_PACKAGED"] = "windows",
                ["STICKLER_ADAPTER_SOURCES"] = adapters,
                ["LANGUAGE"] = GettextLanguages(languages),
                ["UV_SYSTEM_CERTS"] = "1",
                ["PYTHONUTF8"] = "1",
            },
            needs: [uv, adapters]);
    }

    /// <summary>The app's core for this process: the checkout it finds, or a core that ends at
    /// once and says what is missing.</summary>
    public static CoreClient ForApp(
        IReadOnlyDictionary<string, string?> environment, string start, bool windows, IEnumerable<string> languages)
    {
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
        return Checkout(checkout, uv, languages);
    }
}
