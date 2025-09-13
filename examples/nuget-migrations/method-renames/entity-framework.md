# Entity Framework Core Method Renames

## Overview

Entity Framework Core often renames methods between major versions. This example shows how to migrate from old method names to new ones, such as the common rename from `FromSql` to `FromSqlRaw`.

## Before Migration

```csharp
using Microsoft.EntityFrameworkCore;
using System.Linq;

public class UserRepository
{
    private readonly ApplicationDbContext _context;

    public UserRepository(ApplicationDbContext context)
    {
        _context = context;
    }

    public IQueryable<User> GetUsersByRole(string role)
    {
        return _context.Users
            .FromSql($"SELECT * FROM Users WHERE Role = {role}")
            .Where(u => u.IsActive);
    }

    public IQueryable<User> GetUsersByDepartment(int departmentId)
    {
        return _context.Users
            .FromSql($"SELECT * FROM Users WHERE DepartmentId = {departmentId}");
    }
}
```

## After Migration

```csharp
using Microsoft.EntityFrameworkCore;
using System.Linq;

public class UserRepository
{
    private readonly ApplicationDbContext _context;

    public UserRepository(ApplicationDbContext context)
    {
        _context = context;
    }

    public IQueryable<User> GetUsersByRole(string role)
    {
        return _context.Users
            .FromSqlRaw($"SELECT * FROM Users WHERE Role = {role}")
            .Where(u => u.IsActive);
    }

    public IQueryable<User> GetUsersByDepartment(int departmentId)
    {
        return _context.Users
            .FromSqlRaw($"SELECT * FROM Users WHERE DepartmentId = {departmentId}");
    }
}
```

## Migration Rules

```json
{
  "rules": [
    {
      "name": "Rename FromSql to FromSqlRaw",
      "target_nodes": [
        {
          "type": "invocationexpression",
          "method_name": "FromSql"
        }
      ],
      "action": {
        "type": "replace_invocation",
        "replacement_method": "FromSqlRaw",
        "preserve_parameters": true
      }
    }
  ]
}
```

## Additional EF Core Renames

Here are other common Entity Framework Core method renames you might encounter:

### Multiple Method Renames

```json
{
  "rules": [
    {
      "name": "Rename FromSql to FromSqlRaw",
      "target_nodes": [
        {
          "type": "invocationexpression",
          "method_name": "FromSql"
        }
      ],
      "action": {
        "type": "replace_invocation",
        "replacement_method": "FromSqlRaw",
        "preserve_parameters": true
      }
    },
    {
      "name": "Rename FromSqlInterpolated to FromSqlRaw",
      "target_nodes": [
        {
          "type": "invocationexpression",
          "method_name": "FromSqlInterpolated"
        }
      ],
      "action": {
        "type": "replace_invocation",
        "replacement_method": "FromSqlRaw",
        "preserve_parameters": true
      }
    },
    {
      "name": "Rename ExecuteSqlCommand to ExecuteSqlRaw",
      "target_nodes": [
        {
          "type": "invocationexpression",
          "method_name": "ExecuteSqlCommand"
        }
      ],
      "action": {
        "type": "replace_invocation",
        "replacement_method": "ExecuteSqlRaw",
        "preserve_parameters": true
      }
    }
  ]
}
```

## What This Migration Does

1. **Locates** all method calls with the old name
2. **Replaces** the method name with the new name
3. **Preserves** all parameters and arguments
4. **Maintains** the method chain structure
5. **Keeps** code formatting intact

## Testing After Migration

1. **Compile** your project to ensure syntax is correct
2. **Run unit tests** to verify functionality
3. **Test database queries** to ensure they still work as expected
4. **Check for any behavioral differences** in the new methods
