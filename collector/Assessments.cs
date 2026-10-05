using System.Text.Json;

namespace NoseCalibration;

// Known assessments. A recording is bound to exactly one {testId, testVersion, questionCount} tuple.
// web/questions.js and tools/validate_bundle.py keep the same table; an unknown or mismatched tuple is
// rejected, never trusted from a client count. Manifest schemaVersion 1 (written before test selection)
// carries no test fields and always means the original five-question test; it is never reinterpreted.
internal static class Assessments
{
    internal sealed record Test(string Id, int Version, int QuestionCount);
    internal static readonly Test Legacy = new("practice-js-5", 1, 5);
    internal static readonly Test Extended = new("practice-js-13", 1, 13);
    static readonly Test[] Known = { Legacy, Extended };
    internal const int ManifestVersion = 2;
    static readonly string[] Fields = { "testId", "testVersion", "questionCount" };

    static Test? Find(string? id, int version, int count) => Known.FirstOrDefault(t => t.Id == id && t.Version == version && t.QuestionCount == count);

    // Exact tuple from a page request, manifest or answers object.
    internal static Test Require(JsonElement e)
    {
        if (e.ValueKind != JsonValueKind.Object ||
            !e.TryGetProperty("testId", out var id) || id.ValueKind != JsonValueKind.String ||
            !e.TryGetProperty("testVersion", out var version) || version.ValueKind != JsonValueKind.Number || !version.TryGetInt32(out int v) ||
            !e.TryGetProperty("questionCount", out var count) || count.ValueKind != JsonValueKind.Number || !count.TryGetInt32(out int n))
            throw new InvalidDataException("A known test ID, version and question count are required.");
        return Find(id.GetString(), v, n) ?? throw new InvalidDataException("Unknown or mismatched test ID, version or question count.");
    }

    internal static Test FromManifest(JsonElement m)
    {
        int schema = m.GetProperty("schemaVersion").GetInt32();
        if (schema == 1)
        {
            if (Fields.Any(f => m.TryGetProperty(f, out _))) throw new InvalidDataException("Legacy manifest must not name a test.");
            return Legacy;
        }
        if (schema == ManifestVersion) return Require(m);
        throw new InvalidDataException("Unsupported manifest version.");
    }

    // Answers written by this page name the session's test and hold one value per question. Legacy
    // answers (no test fields) are accepted only for the legacy test; any stated total must match.
    internal static bool AnswersMatch(JsonElement a, Test test)
    {
        try
        {
            if (a.ValueKind != JsonValueKind.Object) return false;
            bool named = a.TryGetProperty("testId", out _) || a.TryGetProperty("testVersion", out _) || a.TryGetProperty("questionCount", out _);
            if (named ? Require(a) != test : test != Legacy) return false;
            if (a.TryGetProperty("total", out var total) && (!total.TryGetInt32(out int t) || t != test.QuestionCount)) return false;
            if (a.TryGetProperty("values", out var values) && (values.ValueKind != JsonValueKind.Array || (named ? values.GetArrayLength() != test.QuestionCount : values.GetArrayLength() > test.QuestionCount))) return false;
            if (a.TryGetProperty("score", out var score) && (!score.TryGetInt32(out int s) || s < 0 || s > test.QuestionCount)) return false;
            if (a.TryGetProperty("grades", out var grades))
            {
                if (grades.ValueKind != JsonValueKind.Object) return false;
                foreach (var g in grades.EnumerateObject())
                    if (!int.TryParse(g.Name, System.Globalization.NumberStyles.None, System.Globalization.CultureInfo.InvariantCulture, out int i) || i >= test.QuestionCount || g.Name != i.ToString(System.Globalization.CultureInfo.InvariantCulture)) return false;
            }
            return true;
        }
        catch (InvalidDataException) { return false; }
        catch (InvalidOperationException) { return false; }
    }

    // Full pass: every question graded and passed, with the stated score and total.
    internal static bool Complete(JsonElement a, Test test)
    {
        try
        {
            if (!AnswersMatch(a, test)) return false;
            var grades = a.GetProperty("grades");
            return a.GetProperty("score").GetInt32() == test.QuestionCount && a.GetProperty("total").GetInt32() == test.QuestionCount &&
                grades.EnumerateObject().Count() == test.QuestionCount &&
                Enumerable.Range(0, test.QuestionCount).All(i => grades.GetProperty(i.ToString(System.Globalization.CultureInfo.InvariantCulture)).GetProperty("passed").ValueKind == JsonValueKind.True);
        }
        catch (KeyNotFoundException) { return false; }
        catch (InvalidOperationException) { return false; }
        catch (FormatException) { return false; }
    }
}
