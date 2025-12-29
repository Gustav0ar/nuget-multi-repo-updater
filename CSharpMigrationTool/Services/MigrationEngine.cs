using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;

namespace CSharpMigrationTool;

public class MigrationEngine
{
    public async Task<MigrationResult> ExecuteMigrationsAsync(List<string> targetFiles, List<MigrationRule> rules)
    {
        var result = new MigrationResult();
        
        foreach (var filePath in targetFiles)
        {
            try
            {
                await ProcessFileAsync(filePath, rules, result);
            }
            catch (Exception ex)
            {
                result.AddError($"Error processing file {filePath}: {ex.Message}");
            }
        }

        // Generate summary
        if (result.Errors.Any())
        {
            result.Success = false;
            result.Summary = $"Migration completed with {result.Errors.Count} errors.";
        }
        else if (result.ModifiedFiles.Any())
        {
            result.Success = true;
            result.Summary = $"Successfully applied {result.AppliedRules.Count} rules to {result.ModifiedFiles.Count} files.";
        }
        else
        {
            result.Success = true;
            result.Summary = "No changes were needed.";
        }

        return result;
    }

    private async Task ProcessFileAsync(string filePath, List<MigrationRule> rules, MigrationResult result)
    {
        var sourceCode = await File.ReadAllTextAsync(filePath);
        
        // Detect line endings to preserve them
        var useCrlf = sourceCode.Contains("\r\n");

        var syntaxTree = CSharpSyntaxTree.ParseText(sourceCode, path: filePath);
        
        // Create compilation with more comprehensive references
        var references = new List<MetadataReference>
        {
            MetadataReference.CreateFromFile(typeof(object).Assembly.Location),
            MetadataReference.CreateFromFile(typeof(Console).Assembly.Location),
            MetadataReference.CreateFromFile(typeof(System.Collections.Generic.List<>).Assembly.Location),
            MetadataReference.CreateFromFile(typeof(System.Linq.Enumerable).Assembly.Location),
        };

        // Add runtime assemblies
        try
        {
            var runtimePath = Path.GetDirectoryName(typeof(object).Assembly.Location)!;
            var runtimeAssemblies = new[]
            {
                "System.Runtime.dll",
                "System.Collections.dll",
                "System.Linq.dll",
                "System.Private.CoreLib.dll",
                "netstandard.dll"
            };

            foreach (var assembly in runtimeAssemblies)
            {
                var assemblyPath = Path.Combine(runtimePath, assembly);
                if (File.Exists(assemblyPath))
                {
                    references.Add(MetadataReference.CreateFromFile(assemblyPath));
                }
            }
        }
        catch
        {
            // Continue with basic references if runtime assembly loading fails
        }

        var compilation = CSharpCompilation.Create(
            assemblyName: "TempAssembly",
            syntaxTrees: new[] { syntaxTree },
            references: references,
            options: new CSharpCompilationOptions(OutputKind.DynamicallyLinkedLibrary)
        );
        
        var semanticModel = compilation.GetSemanticModel(syntaxTree);
        var root = await syntaxTree.GetRootAsync();

        var modified = false;
        var newRoot = root;

        foreach (var rule in rules)
        {
            try
            {
                var (updatedRoot, hasChanges) = ApplyRule(newRoot, rule, filePath, result, semanticModel);
                
                if (hasChanges)
                {
                    newRoot = updatedRoot;
                    modified = true;
                    result.AddAppliedRule(rule.Name);
                }
            }
            catch (Exception ex)
            {
                result.AddError($"An unexpected error occurred while applying rule '{rule.Name}' to {filePath}: {ex.Message}\nStack Trace: {ex.StackTrace}");
            }
        }

        if (modified)
        {
            var modifiedCode = newRoot.ToFullString();

            // Preserve original line endings (CRLF vs LF) regardless of what Roslyn produced.
            // Normalize to LF first, then re-apply the original newline if needed.
            modifiedCode = NormalizeNewlines(modifiedCode, useCrlf ? "\r\n" : "\n");

            await File.WriteAllTextAsync(filePath, modifiedCode);
            result.AddModifiedFile(filePath);
        }
    }

    private static string NormalizeNewlines(string text, string newline)
    {
        // Canonicalize to LF first (handles CRLF and lone CR), then optionally expand to CRLF.
        var normalized = text.Replace("\r\n", "\n").Replace("\r", "\n");
        return newline == "\r\n" ? normalized.Replace("\n", "\r\n") : normalized;
    }

    private (SyntaxNode, bool) ApplyRule(SyntaxNode root, MigrationRule rule, string filePath, MigrationResult result, SemanticModel semanticModel)
    {
        var hasChangesOverall = false;
        var currentRoot = root;

        foreach (var targetNode in rule.TargetNodes)
        {
            try
            {
                var (updatedRoot, hasChanges) = ApplyTargetNodeRule(currentRoot, targetNode, rule.Action, filePath, result, semanticModel);
                if (hasChanges)
                {
                    currentRoot = updatedRoot;
                    hasChangesOverall = true;
                }
            }
            catch (Exception ex)
            {
                var lineSpan = currentRoot.GetLocation().GetLineSpan();
                result.AddError($"Error applying target node rule in {filePath} at line {lineSpan.StartLinePosition.Line + 1}: {ex.Message}\nStack Trace: {ex.StackTrace}");
            }
        }
        
        return (currentRoot, hasChangesOverall);
    }

    private (SyntaxNode, bool) ApplyTargetNodeRule(SyntaxNode root, TargetNode targetNode, MigrationAction action, string filePath, MigrationResult result, SemanticModel semanticModel)
    {
        try
        {
            return targetNode.Type.ToLowerInvariant() switch
            {
                "invocationexpression" => ApplyInvocationRule(root, targetNode, action, filePath, result, semanticModel),
                "methoddeclaration" => ApplyMethodDeclarationRule(root, targetNode, action),
                "classdeclaration" => ApplyClassDeclarationRule(root, targetNode, action),
                "fielddeclaration" => ApplyFieldDeclarationRule(root, targetNode, action),
                "parameterdeclaration" => ApplyParameterDeclarationRule(root, targetNode, action),
                _ => (root, false)
            };
        }
        catch (Exception ex)
        {
            result.AddError($"Error applying target node rule for type '{targetNode.Type}' in {filePath}: {ex.Message}\nStack Trace: {ex.StackTrace}");
            return (root, false);
        }
    }

    private (SyntaxNode, bool) ApplyInvocationRule(SyntaxNode root, TargetNode targetNode, MigrationAction action, string filePath, MigrationResult result, SemanticModel semanticModel)
    {
        var invocations = root.DescendantNodes()
            .OfType<InvocationExpressionSyntax>()
            .Where(inv => IsMatchingInvocation(inv, targetNode, semanticModel))
            .ToList();

        // Safety: if method_name is specified, enforce it via syntax too.
        // This prevents accidental removals if semantic binding yields unexpected candidates.
        if (!string.IsNullOrWhiteSpace(targetNode.MethodName))
        {
            invocations = invocations
                .Where(inv =>
                {
                    var invokedName = TryGetInvokedMethodName(inv);
                    return invokedName != null &&
                           string.Equals(invokedName, targetNode.MethodName, StringComparison.OrdinalIgnoreCase);
                })
                .ToList();
        }

        if (!invocations.Any())
            return (root, false);

        try
        {
            return action.Type.ToLowerInvariant() switch
            {
                "remove_invocation" => ApplyRemoveInvocation(root, invocations, action, filePath, result),
                "replace_invocation" => ApplyReplaceInvocation(root, invocations, action, filePath, result),
                _ => (root, false)
            };
        }
        catch (Exception ex)
        {
            foreach (var invocation in invocations)
            {
                var lineSpan = invocation.GetLocation().GetLineSpan();
                result.AddError($"Error applying invocation rule '{action.Type}' in {filePath} at line {lineSpan.StartLinePosition.Line + 1}: {ex.Message}\nStack Trace: {ex.StackTrace}");
            }
            return (root, false);
        }
    }

    private static string? TryGetInvokedMethodName(InvocationExpressionSyntax invocation)
    {
        return invocation.Expression switch
        {
            MemberAccessExpressionSyntax memberAccess => memberAccess.Name.Identifier.ValueText,
            IdentifierNameSyntax identifier => identifier.Identifier.ValueText,
            _ => null
        };
    }

    private bool IsMatchingInvocation(InvocationExpressionSyntax invocation, TargetNode targetNode, SemanticModel semanticModel)
    {
        IMethodSymbol? methodSymbol = null;

        try
        {
            if (invocation.Expression is MemberAccessExpressionSyntax memberAccess)
            {
                var symbolInfo = semanticModel.GetSymbolInfo(memberAccess);
                methodSymbol = symbolInfo.Symbol as IMethodSymbol;

                if (methodSymbol == null && symbolInfo.CandidateSymbols.Any())
                {
                    methodSymbol = symbolInfo.CandidateSymbols.OfType<IMethodSymbol>().FirstOrDefault();
                }
            }
            else
            {
                var symbolInfo = semanticModel.GetSymbolInfo(invocation);
                methodSymbol = symbolInfo.Symbol as IMethodSymbol;
            }
        }
        catch
        {
            // Fall back to syntax-based matching if semantic analysis fails
            methodSymbol = null;
        }

        // If semantic analysis succeeded, use it
        if (methodSymbol != null)
        {
            // For extension methods, the symbol needs to be reduced
            if (methodSymbol.IsExtensionMethod)
            {
                methodSymbol = methodSymbol.ReducedFrom ?? methodSymbol;
            }

            if (!string.IsNullOrEmpty(targetNode.MethodName) && 
                !string.Equals(methodSymbol.Name, targetNode.MethodName, StringComparison.OrdinalIgnoreCase))
            {
                return false;
            }

            if (!string.IsNullOrEmpty(targetNode.ContainingType) && 
                !string.Equals(methodSymbol.ContainingType.Name, targetNode.ContainingType, StringComparison.OrdinalIgnoreCase))
            {
                return false;
            }

            if (!string.IsNullOrEmpty(targetNode.ContainingNamespace) && 
                !string.Equals(methodSymbol.ContainingNamespace.ToDisplayString(), targetNode.ContainingNamespace, StringComparison.OrdinalIgnoreCase))
            {
                return false;
            }

            return true;
        }

        // Fall back to syntax-based matching
        return IsMatchingInvocationSyntaxBased(invocation, targetNode);
    }

    private bool IsMatchingInvocationSyntaxBased(InvocationExpressionSyntax invocation, TargetNode targetNode)
    {
        // Extract method name from syntax
        string? methodName = null;
        
        if (invocation.Expression is MemberAccessExpressionSyntax memberAccess)
        {
            methodName = memberAccess.Name.Identifier.ValueText;
        }
        else if (invocation.Expression is IdentifierNameSyntax identifier)
        {
            methodName = identifier.Identifier.ValueText;
        }

        // Match method name
        if (!string.IsNullOrEmpty(targetNode.MethodName))
        {
            if (string.IsNullOrEmpty(methodName) || 
                !string.Equals(methodName, targetNode.MethodName, StringComparison.OrdinalIgnoreCase))
            {
                return false;
            }
        }

        // For syntax-based matching, we can't reliably match containing type/namespace
        // without semantic analysis, so we'll be more permissive
        return true;
    }

    private (SyntaxNode, bool) ApplyRemoveInvocation(SyntaxNode root, List<InvocationExpressionSyntax> invocations, MigrationAction action, string filePath, MigrationResult result)
    {
        // Track the nodes so we can find them in the modified tree
        var currentRoot = root.TrackNodes(invocations);
        var hasChanges = false;

        foreach (var invocation in invocations)
        {
            try
            {
                // Find the current version of the invocation in the modified tree
                var currentInvocation = currentRoot.GetCurrentNode(invocation);
                
                // If the node is gone (e.g. removed as part of a previous removal), skip it
                if (currentInvocation == null)
                {
                    continue;
                }

                var (updatedRoot, changed) = RemoveInvocationSmartly(currentRoot, currentInvocation, action);
                if (changed)
                {
                    currentRoot = updatedRoot;
                    hasChanges = true;
                }
            }
            catch (Exception ex)
            {
                var lineSpan = invocation.GetLocation().GetLineSpan();
                result.AddError($"Error removing invocation in {filePath} at line {lineSpan.StartLinePosition.Line + 1}: {ex.Message}\nStack Trace: {ex.StackTrace}");
            }
        }

        return (currentRoot, hasChanges);
    }

    private (SyntaxNode, bool) RemoveInvocationSmartly(SyntaxNode root, InvocationExpressionSyntax invocation, MigrationAction action)
    {
        var parent = invocation.Parent;

        if (parent is ExpressionStatementSyntax statement)
        {
            // This is a standalone statement, remove the entire statement
            var newRoot = root.RemoveNode(statement, SyntaxRemoveOptions.KeepNoTrivia);
            return (newRoot ?? root, newRoot != null);
        }
        else if (parent is MemberAccessExpressionSyntax memberAccess && memberAccess.Expression == invocation)
        {
            // This invocation is part of a chain: someObject.ThisMethod().NextMethod()
            // We need to replace the entire member access with just the next part
            
            if (invocation.Expression is MemberAccessExpressionSyntax mae)
            {
                var newMemberAccess = memberAccess.WithExpression(mae.Expression);
                return (root.ReplaceNode(memberAccess, newMemberAccess), true);
            }
            else if (invocation.Expression is NameSyntax)
            {
                // Case: Method().Next() -> Next()
                // Replace the member access (Method().Next) with just the name (Next)
                // This effectively removes the Method() call and makes Next() the primary invocation
                return (root.ReplaceNode(memberAccess, memberAccess.Name), true);
            }
        }
        else if (invocation.Expression is MemberAccessExpressionSyntax chainedAccess)
        {
            // This invocation is at the end of a chain: someObject.Method1().ThisMethod()
            // Replace with just the object and previous methods
            return (root.ReplaceNode(invocation, chainedAccess.Expression), true);
        }

        return (root, false);
    }

    private (SyntaxNode, bool) ApplyReplaceInvocation(SyntaxNode root, List<InvocationExpressionSyntax> invocations, MigrationAction action, string filePath, MigrationResult result)
    {
        if (string.IsNullOrEmpty(action.ReplacementMethod))
            return (root, false);

        // Track the nodes so we can find them in the modified tree
        var currentRoot = root.TrackNodes(invocations);
        var hasChanges = false;

        foreach (var invocation in invocations)
        {
            try
            {
                // Find the current version of the invocation in the modified tree
                var currentInvocation = currentRoot.GetCurrentNode(invocation);
                
                // If the node is gone, skip it
                if (currentInvocation == null)
                    continue;

                var newInvocation = ReplaceMethodName(currentInvocation, action.ReplacementMethod);
                currentRoot = currentRoot.ReplaceNode(currentInvocation, newInvocation);
                hasChanges = true;
            }
            catch (Exception ex)
            {
                var lineSpan = invocation.GetLocation().GetLineSpan();
                result.AddError($"Error replacing invocation in {filePath} at line {lineSpan.StartLinePosition.Line + 1}: {ex.Message}\nStack Trace: {ex.StackTrace}");
            }
        }

        return (currentRoot, hasChanges);
    }

    private InvocationExpressionSyntax ReplaceMethodName(InvocationExpressionSyntax invocation, string newMethodName)
    {
        var newExpression = invocation.Expression switch
        {
            IdentifierNameSyntax identifier => SyntaxFactory.IdentifierName(newMethodName),
            MemberAccessExpressionSyntax memberAccess => memberAccess.WithName(SyntaxFactory.IdentifierName(newMethodName)),
            _ => invocation.Expression
        };

        return invocation.WithExpression(newExpression);
    }

    // Declaration rule implementations
    private (SyntaxNode, bool) ApplyMethodDeclarationRule(SyntaxNode root, TargetNode targetNode, MigrationAction action)
    {
        var methods = root.DescendantNodes()
            .OfType<MethodDeclarationSyntax>()
            .Where(method => IsMatchingMethodDeclaration(method, targetNode))
            .ToList();

        if (!methods.Any())
            return (root, false);

        return action.Type.ToLowerInvariant() switch
        {
            "rename_method" => ApplyRenameMethod(root, methods, action),
            "replace_method_signature" => ApplyReplaceMethodSignature(root, methods, action),
            "add_attribute" => ApplyAddAttributeToMethod(root, methods, action),
            "remove_attribute" => ApplyRemoveAttributeFromMethod(root, methods, action),
            "replace_return_type" => ApplyReplaceMethodReturnType(root, methods, action),
            _ => (root, false)
        };
    }

    private (SyntaxNode, bool) ApplyClassDeclarationRule(SyntaxNode root, TargetNode targetNode, MigrationAction action)
    {
        var classes = root.DescendantNodes()
            .OfType<ClassDeclarationSyntax>()
            .Where(cls => IsMatchingClassDeclaration(cls, targetNode))
            .ToList();

        if (!classes.Any())
            return (root, false);

        return action.Type.ToLowerInvariant() switch
        {
            "rename_class" => ApplyRenameClass(root, classes, action),
            "add_attribute" => ApplyAddAttributeToClass(root, classes, action),
            "remove_attribute" => ApplyRemoveAttributeFromClass(root, classes, action),
            "change_base_class" => ApplyChangeBaseClass(root, classes, action),
            "add_interface" => ApplyAddInterface(root, classes, action),
            _ => (root, false)
        };
    }

    private (SyntaxNode, bool) ApplyFieldDeclarationRule(SyntaxNode root, TargetNode targetNode, MigrationAction action)
    {
        var fields = root.DescendantNodes()
            .OfType<FieldDeclarationSyntax>()
            .Where(field => IsMatchingFieldDeclaration(field, targetNode))
            .ToList();

        if (!fields.Any())
            return (root, false);

        return action.Type.ToLowerInvariant() switch
        {
            "replace_field_type" => ApplyReplaceFieldType(root, fields, action),
            "rename_field" => ApplyRenameField(root, fields, action),
            "add_attribute" => ApplyAddAttributeToField(root, fields, action),
            "remove_attribute" => ApplyRemoveAttributeFromField(root, fields, action),
            "change_accessibility" => ApplyChangeFieldAccessibility(root, fields, action),
            _ => (root, false)
        };
    }

    private (SyntaxNode, bool) ApplyParameterDeclarationRule(SyntaxNode root, TargetNode targetNode, MigrationAction action)
    {
        var parameters = root.DescendantNodes()
            .OfType<ParameterSyntax>()
            .Where(param => IsMatchingParameterDeclaration(param, targetNode))
            .ToList();

        if (!parameters.Any())
            return (root, false);

        return action.Type.ToLowerInvariant() switch
        {
            "replace_parameter_type" => ApplyReplaceParameterType(root, parameters, action),
            "rename_parameter" => ApplyRenameParameter(root, parameters, action),
            "add_attribute" => ApplyAddAttributeToParameter(root, parameters, action),
            "remove_attribute" => ApplyRemoveAttributeFromParameter(root, parameters, action),
            _ => (root, false)
        };
    }

    // Helper methods for matching declarations
    private bool IsMatchingMethodDeclaration(MethodDeclarationSyntax method, TargetNode targetNode)
    {
        // Check method name match
        if (!string.IsNullOrEmpty(targetNode.MethodName) && 
            !string.Equals(method.Identifier.ValueText, targetNode.MethodName, StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        // Check containing class if specified
        if (!string.IsNullOrEmpty(targetNode.ContainingType))
        {
            var containingClass = method.FirstAncestorOrSelf<ClassDeclarationSyntax>();
            if (containingClass == null || 
                !string.Equals(containingClass.Identifier.ValueText, targetNode.ContainingType, StringComparison.OrdinalIgnoreCase))
            {
                return false;
            }
        }

        // Check attributes if specified
        if (targetNode.Attributes != null && targetNode.Attributes.Any())
        {
            var methodAttributes = method.AttributeLists.SelectMany(al => al.Attributes).Select(a => a.Name.ToString()).ToList();
            foreach (var requiredAttribute in targetNode.Attributes)
            {
                if (!methodAttributes.Any(ma => ma.Contains(requiredAttribute)))
                {
                    return false;
                }
            }
        }

        // Check parameters if specified
        if (targetNode.Parameters != null && targetNode.Parameters.Any())
        {
            var methodParams = method.ParameterList.Parameters;
            if (methodParams.Count != targetNode.Parameters.Count)
            {
                return false;
            }

            for (int i = 0; i < targetNode.Parameters.Count; i++)
            {
                var expectedParam = targetNode.Parameters[i];
                var actualParam = methodParams[i];
                
                if (!string.IsNullOrEmpty(expectedParam.Type) && 
                    !actualParam.Type?.ToString().Contains(expectedParam.Type) == true)
                {
                    return false;
                }

                if (!string.IsNullOrEmpty(expectedParam.Name) && 
                    !string.Equals(actualParam.Identifier.ValueText, expectedParam.Name, StringComparison.OrdinalIgnoreCase))
                {
                    return false;
                }
            }
        }

        return true;
    }

    private bool IsMatchingClassDeclaration(ClassDeclarationSyntax cls, TargetNode targetNode)
    {
        // Check class name match
        if (!string.IsNullOrEmpty(targetNode.ClassName) && 
            !string.Equals(cls.Identifier.ValueText, targetNode.ClassName, StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        // Check attributes if specified
        if (targetNode.Attributes != null && targetNode.Attributes.Any())
        {
            var classAttributes = cls.AttributeLists.SelectMany(al => al.Attributes).Select(a => a.Name.ToString()).ToList();
            foreach (var requiredAttribute in targetNode.Attributes)
            {
                if (!classAttributes.Any(ca => ca.Contains(requiredAttribute)))
                {
                    return false;
                }
            }
        }

        return true;
    }

    private bool IsMatchingFieldDeclaration(FieldDeclarationSyntax field, TargetNode targetNode)
    {
        // Check field name match (fields can have multiple variables)
        if (!string.IsNullOrEmpty(targetNode.Identifier))
        {
            var fieldNames = field.Declaration.Variables.Select(v => v.Identifier.ValueText);
            if (!fieldNames.Any(fn => string.Equals(fn, targetNode.Identifier, StringComparison.OrdinalIgnoreCase)))
            {
                return false;
            }
        }

        // Check containing class if specified
        if (!string.IsNullOrEmpty(targetNode.ContainingType))
        {
            var containingClass = field.FirstAncestorOrSelf<ClassDeclarationSyntax>();
            if (containingClass == null || 
                !string.Equals(containingClass.Identifier.ValueText, targetNode.ContainingType, StringComparison.OrdinalIgnoreCase))
            {
                return false;
            }
        }

        // Check attributes if specified
        if (targetNode.Attributes != null && targetNode.Attributes.Any())
        {
            var fieldAttributes = field.AttributeLists.SelectMany(al => al.Attributes).Select(a => a.Name.ToString()).ToList();
            foreach (var requiredAttribute in targetNode.Attributes)
            {
                if (!fieldAttributes.Any(fa => fa.Contains(requiredAttribute)))
                {
                    return false;
                }
            }
        }

        return true;
    }

    private bool IsMatchingParameterDeclaration(ParameterSyntax parameter, TargetNode targetNode)
    {
        // Check parameter name match
        if (!string.IsNullOrEmpty(targetNode.Identifier) && 
            !string.Equals(parameter.Identifier.ValueText, targetNode.Identifier, StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        // Check parameter type if specified
        if (targetNode.Parameters != null && targetNode.Parameters.Any())
        {
            var expectedType = targetNode.Parameters.First().Type;
            if (!string.IsNullOrEmpty(expectedType) && 
                !parameter.Type?.ToString().Contains(expectedType) == true)
            {
                return false;
            }
        }

        return true;
    }

    // Method declaration transformation implementations
    private (SyntaxNode, bool) ApplyRenameMethod(SyntaxNode root, List<MethodDeclarationSyntax> methods, MigrationAction action)
    {
        if (string.IsNullOrEmpty(action.ReplacementMethod))
            return (root, false);

        var newRoot = root;
        var hasChanges = false;

        foreach (var method in methods)
        {
            var newMethod = method.WithIdentifier(SyntaxFactory.Identifier(action.ReplacementMethod));
            newRoot = newRoot.ReplaceNode(method, newMethod);
            hasChanges = true;
        }

        return (newRoot, hasChanges);
    }

    private (SyntaxNode, bool) ApplyReplaceMethodSignature(SyntaxNode root, List<MethodDeclarationSyntax> methods, MigrationAction action)
    {
        if (string.IsNullOrEmpty(action.ReplacementCode))
            return (root, false);

        var newRoot = root;
        var hasChanges = false;

        foreach (var method in methods)
        {
            try
            {
                // Parse the replacement signature
                var newSignature = SyntaxFactory.ParseMemberDeclaration($"public {action.ReplacementCode}") as MethodDeclarationSyntax;
                if (newSignature != null)
                {
                    // Preserve the method body and accessibility modifiers
                    var newMethod = newSignature
                        .WithModifiers(method.Modifiers)
                        .WithBody(method.Body)
                        .WithExpressionBody(method.ExpressionBody)
                        .WithSemicolonToken(method.SemicolonToken);
                    
                    newRoot = newRoot.ReplaceNode(method, newMethod);
                    hasChanges = true;
                }
            }
            catch
            {
                // If parsing fails, skip this transformation
            }
        }

        return (newRoot, hasChanges);
    }

    private (SyntaxNode, bool) ApplyAddAttributeToMethod(SyntaxNode root, List<MethodDeclarationSyntax> methods, MigrationAction action)
    {
        if (string.IsNullOrEmpty(action.AttributeName))
            return (root, false);

        var newRoot = root;
        var hasChanges = false;

        foreach (var method in methods)
        {
            var attribute = SyntaxFactory.Attribute(SyntaxFactory.IdentifierName(action.AttributeName));
            var attributeList = SyntaxFactory.AttributeList(SyntaxFactory.SingletonSeparatedList(attribute));
            var newMethod = method.WithAttributeLists(method.AttributeLists.Add(attributeList));
            
            newRoot = newRoot.ReplaceNode(method, newMethod);
            hasChanges = true;
        }

        return (newRoot, hasChanges);
    }

    private (SyntaxNode, bool) ApplyRemoveAttributeFromMethod(SyntaxNode root, List<MethodDeclarationSyntax> methods, MigrationAction action)
    {
        if (string.IsNullOrEmpty(action.AttributeName))
            return (root, false);

        var newRoot = root;
        var hasChanges = false;

        foreach (var method in methods)
        {
            var filteredAttributeLists = method.AttributeLists
                .Where(al => !al.Attributes.Any(a => a.Name.ToString().Contains(action.AttributeName)))
                .ToList();

            if (filteredAttributeLists.Count != method.AttributeLists.Count)
            {
                var newMethod = method.WithAttributeLists(SyntaxFactory.List(filteredAttributeLists));
                newRoot = newRoot.ReplaceNode(method, newMethod);
                hasChanges = true;
            }
        }

        return (newRoot, hasChanges);
    }

    private (SyntaxNode, bool) ApplyReplaceMethodReturnType(SyntaxNode root, List<MethodDeclarationSyntax> methods, MigrationAction action)
    {
        if (string.IsNullOrEmpty(action.ReplacementType))
            return (root, false);

        var newRoot = root;
        var hasChanges = false;

        foreach (var method in methods)
        {
            var newReturnType = SyntaxFactory.ParseTypeName(action.ReplacementType);
            var newMethod = method.WithReturnType(newReturnType);
            
            newRoot = newRoot.ReplaceNode(method, newMethod);
            hasChanges = true;
        }

        return (newRoot, hasChanges);
    }

    // Class declaration transformation implementations
    private (SyntaxNode, bool) ApplyRenameClass(SyntaxNode root, List<ClassDeclarationSyntax> classes, MigrationAction action)
    {
        if (string.IsNullOrEmpty(action.ReplacementCode))
            return (root, false);

        var newRoot = root;
        var hasChanges = false;

        foreach (var cls in classes)
        {
            var newClass = cls.WithIdentifier(SyntaxFactory.Identifier(action.ReplacementCode));
            newRoot = newRoot.ReplaceNode(cls, newClass);
            hasChanges = true;
        }

        return (newRoot, hasChanges);
    }

    private (SyntaxNode, bool) ApplyAddAttributeToClass(SyntaxNode root, List<ClassDeclarationSyntax> classes, MigrationAction action)
    {
        if (string.IsNullOrEmpty(action.AttributeName))
            return (root, false);

        var newRoot = root;
        var hasChanges = false;

        foreach (var cls in classes)
        {
            var attribute = SyntaxFactory.Attribute(SyntaxFactory.IdentifierName(action.AttributeName));
            var attributeList = SyntaxFactory.AttributeList(SyntaxFactory.SingletonSeparatedList(attribute))
                .WithTrailingTrivia(SyntaxFactory.EndOfLine("\n"));
            var newClass = cls.WithAttributeLists(cls.AttributeLists.Add(attributeList));
            
            newRoot = newRoot.ReplaceNode(cls, newClass);
            hasChanges = true;
        }

        return (newRoot, hasChanges);
    }

    private (SyntaxNode, bool) ApplyRemoveAttributeFromClass(SyntaxNode root, List<ClassDeclarationSyntax> classes, MigrationAction action)
    {
        if (string.IsNullOrEmpty(action.AttributeName))
            return (root, false);

        var newRoot = root;
        var hasChanges = false;

        foreach (var cls in classes)
        {
            var filteredAttributeLists = cls.AttributeLists
                .Where(al => !al.Attributes.Any(a => a.Name.ToString().Contains(action.AttributeName)))
                .ToList();

            if (filteredAttributeLists.Count != cls.AttributeLists.Count)
            {
                var newClass = cls.WithAttributeLists(SyntaxFactory.List(filteredAttributeLists));
                newRoot = newRoot.ReplaceNode(cls, newClass);
                hasChanges = true;
            }
        }

        return (newRoot, hasChanges);
    }

    private (SyntaxNode, bool) ApplyChangeBaseClass(SyntaxNode root, List<ClassDeclarationSyntax> classes, MigrationAction action)
    {
        if (string.IsNullOrEmpty(action.ReplacementType))
            return (root, false);

        var newRoot = root;
        var hasChanges = false;

        foreach (var cls in classes)
        {
            var newBaseType = SyntaxFactory.SimpleBaseType(SyntaxFactory.ParseTypeName(action.ReplacementType));
            
            if (cls.BaseList == null)
            {
                var newClass = cls.WithBaseList(SyntaxFactory.BaseList(SyntaxFactory.SingletonSeparatedList<BaseTypeSyntax>(newBaseType)));
                newRoot = newRoot.ReplaceNode(cls, newClass);
                hasChanges = true;
            }
            else
            {
                // Replace the first base type (assuming it's the base class)
                var newBaseList = cls.BaseList.WithTypes(
                    cls.BaseList.Types.Replace(cls.BaseList.Types.First(), newBaseType));
                var newClass = cls.WithBaseList(newBaseList);
                newRoot = newRoot.ReplaceNode(cls, newClass);
                hasChanges = true;
            }
        }

        return (newRoot, hasChanges);
    }

    private (SyntaxNode, bool) ApplyAddInterface(SyntaxNode root, List<ClassDeclarationSyntax> classes, MigrationAction action)
    {
        if (string.IsNullOrEmpty(action.ReplacementType))
            return (root, false);

        var newRoot = root;
        var hasChanges = false;

        foreach (var cls in classes)
        {
            var newInterface = SyntaxFactory.SimpleBaseType(SyntaxFactory.ParseTypeName(action.ReplacementType));
            
            if (cls.BaseList == null)
            {
                var newClass = cls.WithBaseList(SyntaxFactory.BaseList(SyntaxFactory.SingletonSeparatedList<BaseTypeSyntax>(newInterface)));
                newRoot = newRoot.ReplaceNode(cls, newClass);
                hasChanges = true;
            }
            else
            {
                var newBaseList = cls.BaseList.WithTypes(cls.BaseList.Types.Add(newInterface));
                var newClass = cls.WithBaseList(newBaseList);
                newRoot = newRoot.ReplaceNode(cls, newClass);
                hasChanges = true;
            }
        }

        return (newRoot, hasChanges);
    }

    // Field declaration transformation implementations
    private (SyntaxNode, bool) ApplyReplaceFieldType(SyntaxNode root, List<FieldDeclarationSyntax> fields, MigrationAction action)
    {
        if (string.IsNullOrEmpty(action.ReplacementType))
            return (root, false);

        var newRoot = root;
        var hasChanges = false;

        foreach (var field in fields)
        {
            var newType = SyntaxFactory.ParseTypeName(action.ReplacementType).WithTrailingTrivia(SyntaxFactory.Space);
            var newDeclaration = field.Declaration.WithType(newType);
            var newField = field.WithDeclaration(newDeclaration);
            
            newRoot = newRoot.ReplaceNode(field, newField);
            hasChanges = true;
        }

        return (newRoot, hasChanges);
    }

    private (SyntaxNode, bool) ApplyRenameField(SyntaxNode root, List<FieldDeclarationSyntax> fields, MigrationAction action)
    {
        if (string.IsNullOrEmpty(action.ReplacementCode))
            return (root, false);

        var newRoot = root;
        var hasChanges = false;

        foreach (var field in fields)
        {
            var newVariables = field.Declaration.Variables.Select(v => 
                v.WithIdentifier(SyntaxFactory.Identifier(action.ReplacementCode)));
            var newDeclaration = field.Declaration.WithVariables(SyntaxFactory.SeparatedList(newVariables));
            var newField = field.WithDeclaration(newDeclaration);
            
            newRoot = newRoot.ReplaceNode(field, newField);
            hasChanges = true;
        }

        return (newRoot, hasChanges);
    }

    private (SyntaxNode, bool) ApplyAddAttributeToField(SyntaxNode root, List<FieldDeclarationSyntax> fields, MigrationAction action)
    {
        if (string.IsNullOrEmpty(action.AttributeName))
            return (root, false);

        var newRoot = root;
        var hasChanges = false;

        foreach (var field in fields)
        {
            var attribute = SyntaxFactory.Attribute(SyntaxFactory.IdentifierName(action.AttributeName));
            var attributeList = SyntaxFactory.AttributeList(SyntaxFactory.SingletonSeparatedList(attribute));
            var newField = field.WithAttributeLists(field.AttributeLists.Add(attributeList));
            
            newRoot = newRoot.ReplaceNode(field, newField);
            hasChanges = true;
        }

        return (newRoot, hasChanges);
    }

    private (SyntaxNode, bool) ApplyRemoveAttributeFromField(SyntaxNode root, List<FieldDeclarationSyntax> fields, MigrationAction action)
    {
        if (string.IsNullOrEmpty(action.AttributeName))
            return (root, false);

        var newRoot = root;
        var hasChanges = false;

        foreach (var field in fields)
        {
            var filteredAttributeLists = field.AttributeLists
                .Where(al => !al.Attributes.Any(a => a.Name.ToString().Contains(action.AttributeName)))
                .ToList();

            if (filteredAttributeLists.Count != field.AttributeLists.Count)
            {
                var newField = field.WithAttributeLists(SyntaxFactory.List(filteredAttributeLists));
                newRoot = newRoot.ReplaceNode(field, newField);
                hasChanges = true;
            }
        }

        return (newRoot, hasChanges);
    }

    private (SyntaxNode, bool) ApplyChangeFieldAccessibility(SyntaxNode root, List<FieldDeclarationSyntax> fields, MigrationAction action)
    {
        if (string.IsNullOrEmpty(action.ReplacementCode))
            return (root, false);

        var newRoot = root;
        var hasChanges = false;

        foreach (var field in fields)
        {
            var newModifiers = SyntaxFactory.TokenList();
            
            // Parse the new accessibility modifier
            switch (action.ReplacementCode.ToLowerInvariant())
            {
                case "public":
                    newModifiers = newModifiers.Add(SyntaxFactory.Token(SyntaxKind.PublicKeyword));
                    break;
                case "private":
                    newModifiers = newModifiers.Add(SyntaxFactory.Token(SyntaxKind.PrivateKeyword));
                    break;
                case "protected":
                    newModifiers = newModifiers.Add(SyntaxFactory.Token(SyntaxKind.ProtectedKeyword));
                    break;
                case "internal":
                    newModifiers = newModifiers.Add(SyntaxFactory.Token(SyntaxKind.InternalKeyword));
                    break;
                default:
                    continue; // Skip unknown modifiers
            }

            // Preserve non-accessibility modifiers
            foreach (var modifier in field.Modifiers)
            {
                if (!modifier.IsKind(SyntaxKind.PublicKeyword) && 
                    !modifier.IsKind(SyntaxKind.PrivateKeyword) && 
                    !modifier.IsKind(SyntaxKind.ProtectedKeyword) && 
                    !modifier.IsKind(SyntaxKind.InternalKeyword))
                {
                    newModifiers = newModifiers.Add(modifier);
                }
            }

            var newField = field.WithModifiers(newModifiers);
            newRoot = newRoot.ReplaceNode(field, newField);
            hasChanges = true;
        }

        return (newRoot, hasChanges);
    }

    // Parameter declaration transformation implementations
    private (SyntaxNode, bool) ApplyReplaceParameterType(SyntaxNode root, List<ParameterSyntax> parameters, MigrationAction action)
    {
        if (string.IsNullOrEmpty(action.ReplacementType))
            return (root, false);

        var newRoot = root;
        var hasChanges = false;

        foreach (var parameter in parameters)
        {
            var newType = SyntaxFactory.ParseTypeName(action.ReplacementType);
            var newParameter = parameter.WithType(newType);
            
            newRoot = newRoot.ReplaceNode(parameter, newParameter);
            hasChanges = true;
        }

        return (newRoot, hasChanges);
    }

    private (SyntaxNode, bool) ApplyRenameParameter(SyntaxNode root, List<ParameterSyntax> parameters, MigrationAction action)
    {
        if (string.IsNullOrEmpty(action.ReplacementCode))
            return (root, false);

        var newRoot = root;
        var hasChanges = false;

        foreach (var parameter in parameters)
        {
            var newParameter = parameter.WithIdentifier(SyntaxFactory.Identifier(action.ReplacementCode));
            newRoot = newRoot.ReplaceNode(parameter, newParameter);
            hasChanges = true;
        }

        return (newRoot, hasChanges);
    }

    private (SyntaxNode, bool) ApplyAddAttributeToParameter(SyntaxNode root, List<ParameterSyntax> parameters, MigrationAction action)
    {
        if (string.IsNullOrEmpty(action.AttributeName))
            return (root, false);

        var newRoot = root;
        var hasChanges = false;

        foreach (var parameter in parameters)
        {
            var attribute = SyntaxFactory.Attribute(SyntaxFactory.IdentifierName(action.AttributeName));
            var attributeList = SyntaxFactory.AttributeList(SyntaxFactory.SingletonSeparatedList(attribute));
            var newParameter = parameter.WithAttributeLists(parameter.AttributeLists.Add(attributeList));
            
            newRoot = newRoot.ReplaceNode(parameter, newParameter);
            hasChanges = true;
        }

        return (newRoot, hasChanges);
    }

    private (SyntaxNode, bool) ApplyRemoveAttributeFromParameter(SyntaxNode root, List<ParameterSyntax> parameters, MigrationAction action)
    {
        if (string.IsNullOrEmpty(action.AttributeName))
            return (root, false);

        var newRoot = root;
        var hasChanges = false;

        foreach (var parameter in parameters)
        {
            var filteredAttributeLists = parameter.AttributeLists
                .Where(al => !al.Attributes.Any(a => a.Name.ToString().Contains(action.AttributeName)))
                .ToList();

            if (filteredAttributeLists.Count != parameter.AttributeLists.Count)
            {
                var newParameter = parameter.WithAttributeLists(SyntaxFactory.List(filteredAttributeLists));
                newRoot = newRoot.ReplaceNode(parameter, newParameter);
                hasChanges = true;
            }
        }

        return (newRoot, hasChanges);
    }
}