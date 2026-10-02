using System.Text.Json;

namespace NoseCalibration;
internal static class Telemetry
{
    static readonly HashSet<string> Types = new("pointermove pointerdown pointerup keydown keyup wheel scroll focus selection input grade question".Split(' '));
    static bool Number(JsonElement e, string key, double min, double max) => e.TryGetProperty(key, out var v) && v.TryGetDouble(out var n) && double.IsFinite(n) && n >= min && n <= max;
    internal static bool Valid(JsonElement e)
    {
        if (e.ValueKind != JsonValueKind.Object || !e.TryGetProperty("type", out var type) || type.ValueKind != JsonValueKind.String || !Types.Contains(type.GetString()!)) return false;
        if (!Number(e, "id", 1, 250000) || !Number(e, "t", 0, 1801000) || !e.TryGetProperty("viewport", out var viewport) || viewport.ValueKind != JsonValueKind.Object || !Number(viewport, "width", 1, 8192) || !Number(viewport, "height", 1, 8192)) return false;
        foreach (var property in e.EnumerateObject())
            if (property.Value.ValueKind == JsonValueKind.String && property.Value.GetString()!.Length > 80) return false;
        if (type.GetString()!.StartsWith("pointer") && (!Number(e, "x", -1, 8193) || !Number(e, "y", -1, 8193))) return false;
        return true;
    }
}
