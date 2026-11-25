using System.Text.Json;
using System.Text.RegularExpressions;

namespace Stickler.Core;

/// <summary>The app's own texts in the reader's language, from the tables
/// <c>scripts/winstrings.py</c> writes from <c>po/</c> (SPEC.md, module <c>win-shell</c>,
/// scope 1). The key is the English text; placeholders are named (<c>{name}</c>,
/// <c>{size:n}</c>) and filled by name; a text with a count has <c>one</c> and <c>other</c>,
/// chosen by the rule <c>n != 1</c>. A text without a translation stays English, as gettext
/// does.</summary>
public sealed partial class Strings
{
    private readonly IReadOnlyDictionary<string, JsonElement> table;
    private readonly IReadOnlyDictionary<string, JsonElement> english;

    private Strings(string language, IReadOnlyDictionary<string, JsonElement> table, IReadOnlyDictionary<string, JsonElement> english)
    {
        Language = language;
        this.table = table;
        this.english = english;
    }

    /// <summary>The language chosen: the reader's first preferred one that has a table, else <c>en</c>.</summary>
    public string Language { get; }

    /// <summary>Reads the tables in <paramref name="folder"/> and picks by <paramref name="preferred"/>
    /// (BCP 47, best first; <c>de-DE</c> takes <c>de</c>). English first means English.</summary>
    public static Strings Load(string folder, IEnumerable<string> preferred)
    {
        ArgumentNullException.ThrowIfNull(preferred);
        var english = Read(Path.Combine(folder, "en.json"));
        foreach (var language in preferred)
        {
            var main = language.Split('-', '_')[0].ToLowerInvariant();
            if (main == "en")
            {
                break;
            }
            var file = Path.Combine(folder, $"{main}.json");
            if (File.Exists(file))
            {
                return new Strings(main, Read(file), english);
            }
        }
        return new Strings("en", new Dictionary<string, JsonElement>(), english);
    }

    /// <summary>English only: for tests and for a build without its tables.</summary>
    public static Strings English { get; } =
        new("en", new Dictionary<string, JsonElement>(), new Dictionary<string, JsonElement>());

    /// <summary><paramref name="english"/> in the chosen language, its placeholders filled.</summary>
    public string Text(string english, params (string Name, string Value)[] values)
    {
        var found = table.TryGetValue(english, out var value) && value.ValueKind == JsonValueKind.String
            ? value.GetString()!
            : english;
        return Fill(found, values);
    }

    /// <summary>The form of <paramref name="singular"/> for <paramref name="count"/>, its
    /// placeholders filled (<c>{count}</c> among them when given).</summary>
    public string Plural(string singular, int count, params (string Name, string Value)[] values)
    {
        var form = count == 1 ? "one" : "other";
        var found = Form(table, singular, form) ?? Form(english, singular, form) ?? singular;
        return Fill(found, values);
    }

    private static string? Form(IReadOnlyDictionary<string, JsonElement> source, string key, string form) =>
        source.TryGetValue(key, out var value)
        && value.ValueKind == JsonValueKind.Object
        && value.TryGetProperty(form, out var text)
            ? text.GetString()
            : null;

    private static string Fill(string text, (string Name, string Value)[] values) =>
        Placeholder().Replace(text, match =>
        {
            foreach (var (name, value) in values)
            {
                if (name == match.Groups[1].Value)
                {
                    return value;
                }
            }
            return match.Value; // a name nobody gave stays visible rather than vanish
        });

    private static Dictionary<string, JsonElement> Read(string file)
    {
        if (!File.Exists(file))
        {
            return [];
        }
        using var document = JsonDocument.Parse(File.ReadAllText(file));
        return document.RootElement.EnumerateObject().ToDictionary(p => p.Name, p => p.Value.Clone());
    }

    [GeneratedRegex(@"\{(\w+)(?::[^}]*)?\}")]
    private static partial Regex Placeholder();
}
