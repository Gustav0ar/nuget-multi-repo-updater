# Remove an Invocation Argument

This example removes a boolean flag argument from an invocation, and (when safe) also removes the local variable declaration if it becomes unused.

## Before

```csharp
public void ConfigureServices(IServiceCollection services)
{
    var isAnalyzerEnabled = configuration.GetValue<bool>("Analyzer:Enabled");

    services.AddAnalyzer(configuration, isAnalyzerEnabled);
}
```

## After

```csharp
public void ConfigureServices(IServiceCollection services)
{
    services.AddAnalyzer(configuration);
}
```

## Migration Rule (YAML)

```yaml
- name: 'Remove isAnalyzerEnabled argument from AddAnalyzer'
  target_nodes:
    - type: 'InvocationExpression'
      method_name: 'AddAnalyzer'
  action:
    type: 'remove_argument'
    argument_name: 'isAnalyzerEnabled'
```

## Migration Rule (JSON)

```json
{
  "rules": [
    {
      "name": "Remove isAnalyzerEnabled argument from AddAnalyzer",
      "target_nodes": [
        {
          "type": "InvocationExpression",
          "method_name": "AddAnalyzer"
        }
      ],
      "action": {
        "type": "remove_argument",
        "argument_name": "isAnalyzerEnabled"
      }
    }
  ]
}
```

## Notes

- The argument is removed only when it matches the identifier name given in `argument_name`.
- After the argument removal, the migration tool will remove `var isAnalyzerEnabled = ...;` only if that variable is not referenced anywhere else in the containing scope.
