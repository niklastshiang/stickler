using System.Text.Json;

namespace Stickler.Core;

/// <summary>What the app itself remembers about its window, in a small <c>window.json</c> beside
/// the core's <c>settings.json</c> (SPEC.md, module <c>win-corrections</c>, scope 3).</summary>
public sealed record WindowSettings(bool CorrectionsShown)
{
    private const string FileName = "window.json";
    private const string Field = "corrections_shown";

    /// <summary>The file in the core's config folder, by the rules of <c>paths.config_home</c>:
    /// <c>$XDG_CONFIG_HOME/stickler</c>, else <c>%LOCALAPPDATA%\Stickler\config</c>, else
    /// <c>&lt;home&gt;\AppData\Local\Stickler\config</c>.</summary>
    public static string PathFor(IReadOnlyDictionary<string, string?> env)
    {
        var xdg = Value(env, "XDG_CONFIG_HOME");
        if (xdg is not null)
        {
            return Path.Combine(xdg, "stickler", FileName);
        }

        var local = Value(env, "LOCALAPPDATA")
            ?? Path.Combine(
                Value(env, "USERPROFILE") ?? Value(env, "HOME") ?? Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
                "AppData",
                "Local");
        return Path.Combine(local, "Stickler", "config", FileName);
    }

    /// <summary>The stored settings; the default for a missing, unreadable or malformed file or
    /// a field of the wrong type. Never throws.</summary>
    public static WindowSettings Load(string path)
    {
        try
        {
            using var document = JsonDocument.Parse(File.ReadAllBytes(path));
            return document.RootElement is { ValueKind: JsonValueKind.Object } root
                && root.TryGetProperty(Field, out var value)
                && value.ValueKind is JsonValueKind.True or JsonValueKind.False
                ? new WindowSettings(value.GetBoolean())
                : new WindowSettings(false);
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException or JsonException)
        {
            return new WindowSettings(false);
        }
    }

    /// <summary>Writes the file (a temporary file in the same folder, moved over the target);
    /// false when the folder or file cannot be written.</summary>
    public bool Save(string path)
    {
        var temp = "";
        try
        {
            var folder = Path.GetDirectoryName(Path.GetFullPath(path))!;
            Directory.CreateDirectory(folder);
            temp = Path.Combine(folder, $"{Path.GetFileName(path)}.{Guid.NewGuid():N}.tmp");
            File.WriteAllText(temp, $"{{\"{Field}\": {(CorrectionsShown ? "true" : "false")}}}\n");
            File.Move(temp, path, overwrite: true);
            return true;
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException)
        {
            if (temp.Length > 0)
            {
                File.Delete(temp);
            }

            return false;
        }
    }

    private static string? Value(IReadOnlyDictionary<string, string?> env, string key) =>
        env.TryGetValue(key, out var value) && !string.IsNullOrEmpty(value) ? value : null;
}
