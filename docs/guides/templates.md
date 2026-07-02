# Templates

Copy-paste starting points for project-specific conventions that are useful but too layout-dependent for the universal Python best-practices pack.

## Use the Python best-practices pack

Bind the repo-local pack through `conventionSources`, then reference the rules you want:

```json
{
  "version": "v1",
  "conventionSources": {
    "bp": "./packs/python-best-practices.json"
  },
  "conventions": [
    "bp/init-files-are-barrels",
    "bp/absolute-imports-only",
    "bp/no-underscore-exports",
    "bp/docstrings-on-public-api",
    "bp/annotated-public-functions"
  ]
}
```

For paths-less pack rules, use the object form and supply your project paths:

```json
{
  "version": "v1",
  "conventionSources": {
    "bp": "./packs/python-best-practices.json"
  },
  "conventions": [
    {
      "use": "bp/class-name-matches-filename",
      "paths": "src/{name}_service.py"
    },
    {
      "use": "bp/exported-constants-are-upper-case",
      "paths": "src/constants/{name}.py"
    }
  ]
}
```

## Layered import-direction bans

A layered architecture often allows imports downward but not upward. Adjust package names to match your app.

```json
{
  "version": "v1",
  "conventions": [
    {
      "name": "domain-independent-of-application",
      "description": "Domain code must not depend on application services.",
      "paths": "src/myapp/domain/**/*.py",
      "mustNot": {
        "importFrom": "myapp.application"
      }
    },
    {
      "name": "domain-independent-of-infrastructure",
      "description": "Domain code must not depend on infrastructure adapters.",
      "paths": "src/myapp/domain/**/*.py",
      "mustNot": {
        "importFrom": "myapp.infrastructure"
      }
    },
    {
      "name": "application-independent-of-api",
      "description": "Application services must not depend on API handlers.",
      "paths": "src/myapp/application/**/*.py",
      "mustNot": {
        "importFrom": "myapp.api"
      }
    },
    {
      "name": "absolute-imports-in-layers",
      "description": "Layered packages should use absolute imports for stable boundaries.",
      "paths": [
        "src/myapp/domain/**/*.py",
        "src/myapp/application/**/*.py",
        "src/myapp/infrastructure/**/*.py",
        "!**/__init__.py"
      ],
      "mustNot": {
        "importFromCurrentDir": true,
        "importFromParents": true
      }
    }
  ]
}
```

## DDD package layout

Require every bounded context to expose the same internal folders.

```json
{
  "version": "v1",
  "conventions": [
    {
      "name": "bounded-context-layout",
      "description": "Each bounded context has domain, application, and infrastructure packages.",
      "paths": "src/myapp/{context}",
      "must": {
        "haveType": "directory",
        "haveFiles": [
          "__init__.py",
          "domain/__init__.py",
          "application/__init__.py",
          "infrastructure/__init__.py"
        ]
      }
    },
    {
      "name": "bounded-context-import-boundaries",
      "description": "A bounded context's domain layer does not import its outer layers.",
      "paths": "src/myapp/{context}/domain/**/*.py",
      "mustNot": {
        "importFrom": "myapp.${context}.infrastructure"
      }
    }
  ]
}
```

If your contexts use a flat module layout instead of folders, make the file contract explicit:

```json
{
  "version": "v1",
  "conventions": [
    {
      "name": "flat-context-layout",
      "description": "Each context exposes the same module set.",
      "paths": "src/myapp/{context}",
      "must": {
        "haveType": "directory",
        "haveFiles": [
          "__init__.py",
          "models.py",
          "service.py",
          "repository.py"
        ]
      }
    }
  ]
}
```

## Test-suite layout

Require paired tests for top-level source modules:

```json
{
  "version": "v1",
  "conventions": [
    {
      "name": "top-level-modules-have-tests",
      "description": "Every top-level source module has a matching test module.",
      "paths": [
        "src/myapp/{module}.py",
        "!src/myapp/__init__.py"
      ],
      "must": {
        "havePairedFile": "tests/test_${module}.py"
      }
    }
  ]
}
```

For one-level package modules, mirror the package path in `tests/`:

```json
{
  "version": "v1",
  "conventions": [
    {
      "name": "package-modules-have-tests",
      "description": "Every package module has a matching test module.",
      "paths": [
        "src/myapp/{packageName}/{module}.py",
        "!src/myapp/*/__init__.py"
      ],
      "must": {
        "havePairedFile": "tests/${packageName}/test_${module}.py"
      }
    }
  ]
}
```

Require every top-level test file to use a shared test helper:

```json
{
  "version": "v1",
  "conventions": [
    {
      "name": "tests-use-shared-support",
      "description": "Test modules import the shared test support package.",
      "paths": "tests",
      "must": [
        {
          "for": {
            "files": "test_*.py"
          },
          "must": {
            "importFrom": "tests.support"
          }
        }
      ]
    }
  ]
}
```
