using Newtonsoft.Json;

namespace CSharpMigrationTool;

public class MigrationRulesContainer
{
    [JsonProperty("rules")]
    public List<MigrationRule> Rules { get; set; } = new();
}

public class MigrationRule
{
    [JsonProperty("name")]
    public string Name { get; set; } = string.Empty;

    [JsonProperty("target_nodes")]
    public List<TargetNode> TargetNodes { get; set; } = new();

    [JsonProperty("action")]
    public MigrationAction Action { get; set; } = new();
}

public class TargetNode
{
    [JsonProperty("type")]
    public string Type { get; set; } = string.Empty;

    [JsonProperty("method_name")]
    public string? MethodName { get; set; }

    [JsonProperty("class_name")]
    public string? ClassName { get; set; }

    [JsonProperty("identifier")]
    public string? Identifier { get; set; }

    [JsonProperty("containing_type")]
    public string? ContainingType { get; set; }

    [JsonProperty("containing_namespace")]
    public string? ContainingNamespace { get; set; }

    [JsonProperty("attributes")]
    public List<string>? Attributes { get; set; }

    [JsonProperty("parameters")]
    public List<ParameterInfo>? Parameters { get; set; }
}

public class ParameterInfo
{
    [JsonProperty("type")]
    public string Type { get; set; } = string.Empty;

    [JsonProperty("name")]
    public string? Name { get; set; }
}

public class MigrationAction
{
    [JsonProperty("type")]
    public string Type { get; set; } = string.Empty;

    [JsonProperty("strategy")]
    public string? Strategy { get; set; }

    [JsonProperty("replacement_method")]
    public string? ReplacementMethod { get; set; }

    [JsonProperty("replacement_code")]
    public string? ReplacementCode { get; set; }

    [JsonProperty("replacement_type")]
    public string? ReplacementType { get; set; }

    [JsonProperty("attribute_name")]
    public string? AttributeName { get; set; }

    [JsonProperty("preserve_parameters")]
    public bool? PreserveParameters { get; set; }

    [JsonProperty("preserve_variable_names")]
    public bool? PreserveVariableNames { get; set; }

    [JsonProperty("argument_name")]
    public string? ArgumentName { get; set; }
}

public class MigrationResult
{
    [JsonProperty("success")]
    public bool Success { get; set; } = true;

    [JsonProperty("modified_files")]
    public List<string> ModifiedFiles { get; set; } = new();

    [JsonProperty("applied_rules")]
    public List<string> AppliedRules { get; set; } = new();

    [JsonProperty("errors")]
    public List<string> Errors { get; set; } = new();

    [JsonProperty("summary")]
    public string Summary { get; set; } = string.Empty;

    public static MigrationResult CreateSuccess(List<string> modifiedFiles, List<string> appliedRules, string summary)
    {
        return new MigrationResult
        {
            Success = true,
            ModifiedFiles = modifiedFiles,
            AppliedRules = appliedRules,
            Summary = summary
        };
    }

    public static MigrationResult CreateFailed(string error)
    {
        return new MigrationResult
        {
            Success = false,
            Errors = new List<string> { error },
            Summary = "Migration failed"
        };
    }

    public void AddError(string error)
    {
        Errors.Add(error);
        Success = false;
    }

    public void AddAppliedRule(string ruleName)
    {
        if (!AppliedRules.Contains(ruleName))
        {
            AppliedRules.Add(ruleName);
        }
    }

    public void AddModifiedFile(string filePath)
    {
        if (!ModifiedFiles.Contains(filePath))
        {
            ModifiedFiles.Add(filePath);
        }
    }
}
