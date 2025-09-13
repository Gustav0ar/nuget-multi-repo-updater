# Microsoft.AspNetCore Namespace Consolidation

## Overview

In ASP.NET Core updates, some types moved from separate packages into the main Microsoft.AspNetCore namespace. This example shows how to update using statements and references.

## Before Migration

```csharp
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Primitives;
using Microsoft.AspNetCore.Hosting;
using Microsoft.Extensions.Hosting;

namespace WebApp.Controllers
{
    [ApiController]
    [Route("api/[controller]")]
    public class UsersController : ControllerBase
    {
        private readonly IWebHostEnvironment _environment;

        public UsersController(IWebHostEnvironment environment)
        {
            _environment = environment;
        }

        [HttpGet]
        [Authorize]
        public IActionResult GetUsers()
        {
            if (_environment.IsDevelopment())
            {
                // Development logic
            }

            return Ok();
        }
    }
}
```

## After Migration

```csharp
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Primitives;
using Microsoft.AspNetCore.Hosting;
using Microsoft.Extensions.Hosting;

namespace WebApp.Controllers
{
    [ApiController]
    [Route("api/[controller]")]
    public class UsersController : ControllerBase
    {
        private readonly IWebHostEnvironment _environment;

        public UsersController(IWebHostEnvironment environment)
        {
            _environment = environment;
        }

        [HttpGet]
        [Authorize]
        public IActionResult GetUsers()
        {
            if (_environment.IsDevelopment())
            {
                // Development logic
            }

            return Ok();
        }
    }
}
```

## Migration Rules for Namespace Updates

```json
{
  "rules": [
    {
      "name": "Update IWebHostEnvironment to IHostEnvironment",
      "target_nodes": [
        {
          "type": "fielddeclaration",
          "identifier": "IWebHostEnvironment"
        }
      ],
      "action": {
        "type": "replace_field_type",
        "replacement_type": "IHostEnvironment"
      }
    },
    {
      "name": "Update IWebHostEnvironment parameter types",
      "target_nodes": [
        {
          "type": "parameterdeclaration",
          "type": "IWebHostEnvironment"
        }
      ],
      "action": {
        "type": "replace_parameter_type",
        "replacement_type": "IHostEnvironment"
      }
    }
  ]
}
```

## Common Namespace Migrations

### ASP.NET Core 2.x to 3.x+

| Old Namespace                                       | New Namespace                                           | Notes                               |
| --------------------------------------------------- | ------------------------------------------------------- | ----------------------------------- |
| `Microsoft.AspNetCore.Hosting.IHostingEnvironment`  | `Microsoft.Extensions.Hosting.IHostEnvironment`         | Environment interface consolidation |
| `Microsoft.AspNetCore.Hosting.IApplicationLifetime` | `Microsoft.Extensions.Hosting.IHostApplicationLifetime` | Application lifetime events         |
| `Microsoft.AspNetCore.Http.Features`                | `Microsoft.AspNetCore.Http`                             | HTTP features moved                 |

### Entity Framework Core Namespace Changes

| Old Namespace                                     | New Namespace                   | Notes                |
| ------------------------------------------------- | ------------------------------- | -------------------- |
| `Microsoft.EntityFrameworkCore.Metadata.Builders` | `Microsoft.EntityFrameworkCore` | Model builder types  |
| `Microsoft.EntityFrameworkCore.Storage`           | `Microsoft.EntityFrameworkCore` | Storage abstractions |

## Migration Strategy

1. **Identify moved types** using compilation errors
2. **Update using statements** to new namespaces
3. **Remove unnecessary using statements** for consolidated namespaces
4. **Update package references** if types moved to different packages
5. **Test compilation** and runtime behavior

## Example Complete Migration

### Before

```csharp
using Microsoft.AspNetCore.Hosting;
using Microsoft.Extensions.DependencyInjection;

public class Startup
{
    public void Configure(IApplicationBuilder app, IHostingEnvironment env)
    {
        if (env.IsDevelopment())
        {
            app.UseDeveloperExceptionPage();
        }
    }
}
```

### After

```csharp
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.DependencyInjection;

public class Startup
{
    public void Configure(IApplicationBuilder app, IHostEnvironment env)
    {
        if (env.IsDevelopment())
        {
            app.UseDeveloperExceptionPage();
        }
    }
}
```

## Automated Using Statement Cleanup

Consider using tools like:

- **Remove and Sort Usings** in Visual Studio
- **dotnet format** command-line tool
- **EditorConfig** rules for consistent using organization

## Testing

1. **Compile the project** to identify missing references
2. **Run unit tests** to ensure functionality is preserved
3. **Test runtime behavior** as some implementations may have changed
4. **Verify dependency injection** still resolves types correctly
