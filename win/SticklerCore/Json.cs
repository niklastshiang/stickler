using System.Globalization;
using System.Text.Json;

namespace Stickler.Core;

/// <summary>A line or a field the client cannot read: the core and the app disagree.</summary>
public sealed class UnreadableLineException : Exception
{
    public UnreadableLineException() { }

    public UnreadableLineException(string message) : base(message) { }

    public UnreadableLineException(string message, Exception inner) : base(message, inner) { }
}

/// <summary>Reading the protocol's fields from a parsed line, without reflection: a missing or
/// mistyped required field is an <see cref="UnreadableLineException"/>.</summary>
internal static class Json
{
    public static JsonElement Field(JsonElement obj, string name) =>
        obj.ValueKind == JsonValueKind.Object && obj.TryGetProperty(name, out var value)
            ? value
            : throw new UnreadableLineException($"no field \"{name}\"");

    public static bool Has(JsonElement obj, string name) =>
        obj.ValueKind == JsonValueKind.Object
        && obj.TryGetProperty(name, out var value)
        && value.ValueKind != JsonValueKind.Null;

    public static string Str(JsonElement obj, string name) =>
        Field(obj, name) is { ValueKind: JsonValueKind.String } value
            ? value.GetString()!
            : throw new UnreadableLineException($"\"{name}\" is not text");

    public static string? OptStr(JsonElement obj, string name) =>
        Has(obj, name) ? Str(obj, name) : null;

    public static bool Bool(JsonElement obj, string name) =>
        Field(obj, name).ValueKind switch
        {
            JsonValueKind.True => true,
            JsonValueKind.False => false,
            _ => throw new UnreadableLineException($"\"{name}\" is not true or false"),
        };

    /// <summary>A flag the core does not send means "not allowed".</summary>
    public static bool Flag(JsonElement obj, string name) => Has(obj, name) && Bool(obj, name);

    public static int Int(JsonElement obj, string name) =>
        Field(obj, name) is { ValueKind: JsonValueKind.Number } value && value.TryGetInt32(out var number)
            ? number
            : throw new UnreadableLineException($"\"{name}\" is not a whole number");

    public static int? OptInt(JsonElement obj, string name) => Has(obj, name) ? Int(obj, name) : null;

    public static long Long(JsonElement obj, string name) =>
        Field(obj, name) is { ValueKind: JsonValueKind.Number } value && value.TryGetInt64(out var number)
            ? number
            : throw new UnreadableLineException($"\"{name}\" is not a whole number");

    public static double Double(JsonElement obj, string name) =>
        Field(obj, name) is { ValueKind: JsonValueKind.Number } value
            ? value.GetDouble()
            : throw new UnreadableLineException($"\"{name}\" is not a number");

    public static double? OptDouble(JsonElement obj, string name) =>
        Has(obj, name) ? Double(obj, name) : null;

    public static IReadOnlyList<T> List<T>(JsonElement obj, string name, Func<JsonElement, T> read) =>
        Field(obj, name) is { ValueKind: JsonValueKind.Array } array
            ? array.EnumerateArray().Select(read).ToList()
            : throw new UnreadableLineException($"\"{name}\" is not a list");

    public static IReadOnlyList<T> OptList<T>(JsonElement obj, string name, Func<JsonElement, T> read) =>
        Has(obj, name) ? List(obj, name, read) : [];

    public static JsonElement Parse(string line)
    {
        try
        {
            using var document = JsonDocument.Parse(line);
            return document.RootElement.Clone();
        }
        catch (JsonException error)
        {
            throw new UnreadableLineException("not JSON", error);
        }
    }

    public static string Number(double value) => value.ToString("R", CultureInfo.InvariantCulture);
}
