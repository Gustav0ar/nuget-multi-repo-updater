# System.Text.Json Migration from Newtonsoft.Json

## Overview

When migrating from Newtonsoft.Json to System.Text.Json, many type and method names change. This example shows how to automatically update common patterns.

## Before Migration

```csharp
using Newtonsoft.Json;
using Newtonsoft.Json.Serialization;
using System.Collections.Generic;

public class JsonService
{
    private readonly JsonSerializerSettings _settings;

    public JsonService()
    {
        _settings = new JsonSerializerSettings
        {
            ContractResolver = new CamelCasePropertyNamesContractResolver(),
            NullValueHandling = NullValueHandling.Ignore,
            DateFormatHandling = DateFormatHandling.IsoDateFormat
        };
    }

    public string SerializeObject(object data)
    {
        return JsonConvert.SerializeObject(data, _settings);
    }

    public T DeserializeObject<T>(string json)
    {
        return JsonConvert.DeserializeObject<T>(json, _settings);
    }

    public List<T> DeserializeList<T>(string json)
    {
        return JsonConvert.DeserializeObject<List<T>>(json, _settings);
    }
}
```

## After Migration

```csharp
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Collections.Generic;

public class JsonService
{
    private readonly JsonSerializerOptions _options;

    public JsonService()
    {
        _options = new JsonSerializerOptions
        {
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
            DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
            PropertyNameCaseInsensitive = true
        };
    }

    public string SerializeObject(object data)
    {
        return JsonSerializer.Serialize(data, _options);
    }

    public T DeserializeObject<T>(string json)
    {
        return JsonSerializer.Deserialize<T>(json, _options);
    }

    public List<T> DeserializeList<T>(string json)
    {
        return JsonSerializer.Deserialize<List<T>>(json, _options);
    }
}
```

## Migration Rules

```json
{
  "rules": [
    {
      "name": "Replace JsonConvert.SerializeObject with JsonSerializer.Serialize",
      "target_nodes": [
        {
          "type": "invocationexpression",
          "method_name": "SerializeObject",
          "containing_type": "JsonConvert"
        }
      ],
      "action": {
        "type": "replace_invocation",
        "replacement_code": "JsonSerializer.Serialize",
        "preserve_parameters": true
      }
    },
    {
      "name": "Replace JsonConvert.DeserializeObject with JsonSerializer.Deserialize",
      "target_nodes": [
        {
          "type": "invocationexpression",
          "method_name": "DeserializeObject",
          "containing_type": "JsonConvert"
        }
      ],
      "action": {
        "type": "replace_invocation",
        "replacement_code": "JsonSerializer.Deserialize",
        "preserve_parameters": true
      }
    },
    {
      "name": "Replace JsonSerializerSettings with JsonSerializerOptions",
      "target_nodes": [
        {
          "type": "classdeclaration",
          "class_name": "JsonSerializerSettings"
        }
      ],
      "action": {
        "type": "replace_type",
        "replacement_type": "JsonSerializerOptions"
      }
    }
  ]
}
```

## Manual Steps Required

After running the automated migration, you'll need to manually update:

1. **Property names** in serializer options (CamelCasePropertyNamesContractResolver → JsonNamingPolicy.CamelCase)
2. **Attribute names** ([JsonProperty] → [JsonPropertyName])
3. **Enum handling** (different approaches between libraries)
4. **Custom converters** (completely different base classes)
5. **Using statements** (update namespace references)

## Complete Example Migration

### Before (Newtonsoft.Json)

```csharp
using Newtonsoft.Json;

public class User
{
    [JsonProperty("user_id")]
    public int Id { get; set; }

    [JsonProperty("full_name")]
    public string Name { get; set; }
}
```

### After (System.Text.Json)

```csharp
using System.Text.Json.Serialization;

public class User
{
    [JsonPropertyName("user_id")]
    public int Id { get; set; }

    [JsonPropertyName("full_name")]
    public string Name { get; set; }
}
```

## Testing Considerations

1. **Serialization output format** may differ slightly
2. **Date/time handling** has different defaults
3. **Null handling** behavior may change
4. **Performance characteristics** are different
5. **Error messages** will be different

Always test thoroughly with your actual data models and use cases.
