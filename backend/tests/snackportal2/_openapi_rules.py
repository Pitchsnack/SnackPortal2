"""The OpenAPI standing-rules validator — the hard contract gate for every service.

The 3-day plan makes ``app.openapi()`` the implementation contract (§1.1) and enumerates
the rules a generated document must satisfy (§1.2, §1.3, §3.5). This module implements
those rules once so all fourteen services are judged by the same code, and so a rule can
never quietly hold for thirteen services and lapse on the fourteenth.

A violation is returned as a string rather than raised, so a failing service reports every
problem it has in one run instead of one per re-run.

Pure stdlib. Runnable standalone:  python tests/snackportal2/_openapi_rules.py
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Set

#: HTTP methods that carry an OpenAPI Operation Object.
_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")

#: An explicit operationId is camelCase with no underscores. FastAPI's auto-generated ids
#: are ``<function>_<path>_<method>`` and always contain underscores, so this single
#: pattern mechanically separates "declared by us" from "invented by the framework".
_EXPLICIT_OPERATION_ID = re.compile(r"\A[a-z][A-Za-z0-9]*\Z")

#: Titles/versions FastAPI supplies when the application does not.
_FRAMEWORK_DEFAULT_TITLE = "FastAPI"
_FRAMEWORK_DEFAULT_VERSION = "0.1.0"

#: The success-response description FastAPI invents when a route does not set
#: ``response_description``. Rejecting it forces every operation to say what it returns.
_FRAMEWORK_DEFAULT_RESPONSE_DESCRIPTION = "Successful Response"


def _operations(schema: Mapping[str, Any]) -> Iterable[tuple[str, str, Mapping[str, Any]]]:
    """Yield ``(path, method, operation)`` for every operation in the document."""
    for path, item in schema.get("paths", {}).items():
        for method in _METHODS:
            operation = item.get(method)
            if isinstance(operation, dict):
                yield path, method, operation


def _success_responses(operation: Mapping[str, Any]) -> Iterable[tuple[str, Mapping[str, Any]]]:
    """Yield the 2xx responses of an operation."""
    for status, response in operation.get("responses", {}).items():
        if str(status).startswith("2") and isinstance(response, dict):
            yield str(status), response


def _has_content_schema(response: Mapping[str, Any]) -> bool:
    """True when a response declares a non-empty schema for at least one media type.

    ``"schema": {}`` is exactly the failure the plan names (§1.2): the document claims a
    body exists while saying nothing whatever about its shape.
    """
    content = response.get("content")
    if not isinstance(content, dict) or not content:
        return False
    for media in content.values():
        if not isinstance(media, dict):
            return False
        schema = media.get("schema")
        if not isinstance(schema, dict) or not schema:
            return False
    return True


def _described(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def check_document(
    schema: Mapping[str, Any],
    *,
    service: str,
    expected_paths: Sequence[str] = (),
    expected_schemas: Sequence[str] = (),
    public_paths: Sequence[str] = ("/health", "/readiness"),
    required_security_schemes: Sequence[str] = (),
    no_content_statuses: Sequence[int] = (204,),
) -> List[str]:
    """Validate one service's generated document against every standing rule.

    ``public_paths`` are the operations that must NOT declare security. Everything else
    must — that is the inverse check the plan calls for (§1.3: "public routes do not
    accidentally inherit protected security", "protected routes declare the required
    security"). The rule is driven by an explicit list precisely because the false rule
    "GET is public, POST is authenticated" is forbidden (§1.2): a private read stays
    authenticated, and the only way to know which reads are private is to name them.
    """
    problems: List[str] = []

    def fail(message: str) -> None:
        problems.append(service + ": " + message)

    # --- document level -------------------------------------------------------------
    version = str(schema.get("openapi", ""))
    if not version.startswith("3.1"):
        fail("openapi version is " + repr(version) + ", expected 3.1.x")

    info = schema.get("info", {})
    title = info.get("title")
    if not _described(title) or title == _FRAMEWORK_DEFAULT_TITLE:
        fail("info.title is not explicit: " + repr(title))
    doc_version = info.get("version")
    if not _described(doc_version) or doc_version == _FRAMEWORK_DEFAULT_VERSION:
        fail("info.version is not explicit: " + repr(doc_version))

    paths = schema.get("paths", {})
    for expected in expected_paths:
        if expected not in paths:
            fail("expected path is missing: " + expected)

    components = schema.get("components", {})
    component_schemas = components.get("schemas", {})
    for expected in expected_schemas:
        if expected not in component_schemas:
            fail("expected component schema is missing: " + expected)

    security_schemes = components.get("securitySchemes", {})
    for expected in required_security_schemes:
        if expected not in security_schemes:
            fail("required security scheme is missing from components.securitySchemes: " + expected)

    # --- operation level ------------------------------------------------------------
    seen_operation_ids: Set[str] = set()
    public = set(public_paths)
    no_content = {str(status) for status in no_content_statuses}

    for path, method, operation in _operations(schema):
        where = method.upper() + " " + path

        operation_id = operation.get("operationId")
        if not _described(operation_id):
            fail(where + " has no operationId")
        elif not _EXPLICIT_OPERATION_ID.match(str(operation_id)):
            fail(where + " has a framework-generated operationId: " + repr(operation_id))
        elif operation_id in seen_operation_ids:
            fail(where + " reuses operationId " + repr(operation_id))
        else:
            seen_operation_ids.add(str(operation_id))

        if not _described(operation.get("summary")):
            fail(where + " has no summary")
        if not _described(operation.get("description")):
            fail(where + " has no description")
        tags = operation.get("tags")
        if not isinstance(tags, list) or not tags or not all(_described(tag) for tag in tags):
            fail(where + " has no tags")

        successes = list(_success_responses(operation))
        if not successes:
            fail(where + " declares no successful response")
        for status, response in successes:
            if not _described(response.get("description")):
                fail(where + " success response " + status + " has no description")
            elif response.get("description") == _FRAMEWORK_DEFAULT_RESPONSE_DESCRIPTION:
                fail(where + " success response " + status + " uses the framework default description")
            if status in no_content:
                continue
            if not _has_content_schema(response):
                fail(where + " success response " + status + " has an empty or missing schema")

        # Every parameter is part of the published contract, so every parameter is
        # described. FastAPI supplies none by default, so this only passes when the route
        # declares them with ``Path(..., description=...)`` / ``Query(..., description=...)``.
        for parameter in operation.get("parameters", []) or []:
            if not isinstance(parameter, dict):
                fail(where + " has a malformed parameter entry")
                continue
            if not _described(parameter.get("description")):
                fail(where + " parameter " + str(parameter.get("name")) + " has no description")

        # An operation that accepts input can fail validation at runtime. Unless it
        # declares 422 explicitly, FastAPI publishes its own ``HTTPValidationError`` shape
        # — a list-valued ``detail`` that echoes the submitted input and contradicts the
        # canonical ErrorResponse the handlers actually return (§9).
        takes_input = bool(operation.get("parameters")) or bool(operation.get("requestBody"))
        if takes_input and "422" not in {str(code) for code in operation.get("responses", {})}:
            fail(where + " accepts input but declares no 422 response")

        for status, response in operation.get("responses", {}).items():
            if str(status).startswith("2"):
                continue
            if not _described(response.get("description")):
                fail(where + " error response " + str(status) + " has no description")
            if not _has_content_schema(response):
                fail(where + " error response " + str(status) + " has no response schema")

        declared_security = operation.get("security")
        if path in public:
            if declared_security:
                fail(where + " is a public route but declares security " + repr(declared_security))
        else:
            if not declared_security:
                fail(where + " is a protected route but declares no security")

    # A document-level ``security`` entry would apply to every operation including the
    # public probes, which is exactly the accidental inheritance the plan warns about.
    if schema.get("security"):
        fail("document-level security is set; security must be declared per operation")

    # --- schema property level --------------------------------------------------------
    for name, definition in component_schemas.items():
        if not isinstance(definition, dict):
            continue
        properties = definition.get("properties")
        if not isinstance(properties, dict):
            continue
        for prop_name, prop in properties.items():
            if not isinstance(prop, dict):
                fail("schema " + name + "." + prop_name + " is not an object")
                continue
            if not _described(prop.get("description")):
                fail("schema property " + name + "." + prop_name + " has no description")

    return problems


def assert_document(schema: Mapping[str, Any], **kwargs: Any) -> None:
    """Raise ``AssertionError`` listing every violation, or return silently."""
    problems = check_document(schema, **kwargs)
    assert not problems, "OpenAPI contract violations:\n  " + "\n  ".join(problems)


# --- self-test ------------------------------------------------------------------------
# The validator is the gate, so the gate itself is tested: a deliberately broken document
# must produce the specific violations, or a real service could pass by accident.


def _self_test() -> None:
    broken: Dict[str, Any] = {
        "openapi": "3.0.2",
        "info": {"title": "FastAPI", "version": "0.1.0"},
        "paths": {
            "/thing/{ref}": {
                "get": {
                    "operationId": "read_thing_thing_get",
                    "parameters": [{"name": "ref", "in": "path"}],
                    "responses": {
                        "200": {
                            "description": "Successful Response",
                            "content": {"application/json": {"schema": {}}},
                        }
                    },
                }
            },
            "/health": {
                "get": {
                    "operationId": "getHealth",
                    "summary": "s",
                    "description": "d",
                    "tags": ["Health"],
                    "security": [{"ClientBearer": []}],
                    "responses": {"200": {"description": "ok", "content": {"application/json": {"schema": {"type": "object"}}}}},
                }
            },
        },
        "components": {"schemas": {"Thing": {"properties": {"a": {"type": "string"}}}}},
    }
    problems = check_document(broken, service="selftest", expected_paths=["/missing"], required_security_schemes=["X"])
    joined = "\n".join(problems)
    for fragment in (
        "openapi version is",
        "info.title is not explicit",
        "info.version is not explicit",
        "expected path is missing: /missing",
        "required security scheme is missing",
        "framework-generated operationId",
        "has no summary",
        "has no description",
        "has no tags",
        "empty or missing schema",
        "public route but declares security",
        "protected route but declares no security",
        "schema property Thing.a has no description",
        "parameter ref has no description",
        "uses the framework default description",
        "accepts input but declares no 422 response",
    ):
        assert fragment in joined, "validator failed to detect: " + fragment + "\n" + joined

    healthy: Dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {"title": "SnackPortal2 Thing Service", "version": "1.0.0"},
        "paths": {
            "/health": {
                "get": {
                    "operationId": "getThingHealth",
                    "summary": "Get service liveness",
                    "description": "Report that this service process is alive.",
                    "tags": ["Health"],
                    "responses": {
                        "200": {
                            "description": "The service is alive.",
                            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/HealthResponse"}}},
                        }
                    },
                }
            }
        },
        "components": {
            "schemas": {"HealthResponse": {"properties": {"status": {"type": "string", "description": "State."}}}},
            "securitySchemes": {"ClientBearer": {"type": "http", "scheme": "bearer"}},
        },
    }
    assert check_document(healthy, service="selftest", required_security_schemes=["ClientBearer"]) == []
    print("openapi rule validator self-test: PASS")


def test_validator_self_test() -> None:
    """pytest entry point for the self-test above."""
    _self_test()


if __name__ == "__main__":
    _self_test()


__all__ = ["assert_document", "check_document"]
