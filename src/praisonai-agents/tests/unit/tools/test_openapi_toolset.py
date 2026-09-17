"""An OpenAPI spec must become callable agent tools.

PraisonAI emitted OpenAPI specs in four places and consumed one nowhere, so
pointing an agent at an existing REST API meant hand-writing a function per
endpoint. Google ADK ships OpenAPIToolset; this is the equivalent.

The tests assert the ARGUMENT-TO-REQUEST BINDING, which is where the bugs
live: a path parameter substituted into the URL, a query parameter in the
query string, everything else in the JSON body, and $refs resolved against
components/schemas so the model sees real field names rather than a pointer.
"""
import pytest

from praisonaiagents.tools.openapi_toolset import OpenAPIOperation, OpenAPIToolset

SPEC = {
    "openapi": "3.0.0",
    "servers": [{"url": "https://api.example.com/v1"}],
    "components": {"schemas": {"Pet": {
        "type": "object",
        "properties": {"name": {"type": "string"}, "tag": {"type": "string"}},
        "required": ["name"]}}},
    "paths": {
        "/pets/{petId}": {"get": {
            "operationId": "getPet", "summary": "Fetch one pet",
            "parameters": [
                {"name": "petId", "in": "path", "required": True,
                 "schema": {"type": "string"}},
                {"name": "verbose", "in": "query", "schema": {"type": "boolean"}}]}},
        "/pets": {"post": {
            "operationId": "createPet", "summary": "Create a pet",
            "requestBody": {"content": {"application/json": {
                "schema": {"$ref": "#/components/schemas/Pet"}}}}}},
    },
}


@pytest.fixture
def tools():
    ts = OpenAPIToolset(spec_dict=SPEC, auth={"type": "bearer", "token": "T0K3N"})
    return {t.name: t for t in ts.get_tools()}


class TestSpecBecomesTools:

    def test_one_tool_per_operation(self, tools):
        assert set(tools) == {"getPet", "createPet"}

    def test_the_base_url_is_taken_from_the_spec(self):
        assert OpenAPIToolset(spec_dict=SPEC).base_url == "https://api.example.com/v1"

    def test_the_summary_becomes_the_description(self, tools):
        assert "Fetch one pet" in tools["getPet"].__doc__

    def test_a_tool_looks_like_a_tool_to_the_agent(self, tools):
        """Agent inspects __name__/__qualname__/__doc__ to recognise a tool."""
        tool = tools["getPet"]
        assert tool.__name__ == "getPet" and tool.__qualname__ == "getPet"
        assert callable(tool)

    def test_an_operation_without_an_operationid_still_gets_a_stable_name(self):
        spec = {"paths": {"/health": {"get": {"summary": "health"}}}}
        names = [t.name for t in OpenAPIToolset(spec_dict=spec).get_tools()]
        assert names == ["get_health"]


class TestArgumentBinding:

    def test_a_path_parameter_is_substituted_into_the_url(self, tools):
        request = tools["getPet"].build_request(petId="p1")
        assert request["url"] == "https://api.example.com/v1/pets/p1"
        assert "{petId}" not in request["url"]

    def test_a_query_parameter_goes_to_the_query_string(self, tools):
        request = tools["getPet"].build_request(petId="p1", verbose=True)
        assert request["params"] == {"verbose": True}

    def test_a_path_parameter_never_leaks_into_the_body(self, tools):
        request = tools["getPet"].build_request(petId="p1")
        assert "json" not in request

    def test_body_fields_go_to_the_json_body(self, tools):
        request = tools["createPet"].build_request(name="Rex", tag="dog")
        assert request["json"] == {"name": "Rex", "tag": "dog"}
        assert request["method"] == "POST"

    def test_the_auth_header_is_attached(self, tools):
        assert tools["getPet"].build_request(petId="p")["headers"]["Authorization"] \
            == "Bearer T0K3N"

    def test_an_api_key_auth_uses_its_own_header_name(self):
        ts = OpenAPIToolset(spec_dict=SPEC,
                            auth={"type": "api_key", "key": "K", "name": "X-Custom"})
        tool = next(t for t in ts.get_tools() if t.name == "getPet")
        assert tool.build_request(petId="p")["headers"]["X-Custom"] == "K"


class TestSchemas:

    def test_a_ref_is_resolved_to_real_fields(self, tools):
        """A model shown a $ref cannot fill the arguments in."""
        schema = tools["createPet"].input_schema
        assert set(schema["properties"]) == {"name", "tag"}
        assert schema["required"] == ["name"]

    def test_path_and_query_parameters_are_both_declared(self, tools):
        assert set(tools["getPet"].input_schema["properties"]) == {"petId", "verbose"}

    def test_required_follows_the_spec(self, tools):
        assert tools["getPet"].input_schema["required"] == ["petId"]

    def test_a_cyclic_ref_does_not_hang(self):
        spec = {"components": {"schemas": {"Node": {
                    "type": "object",
                    "properties": {"child": {"$ref": "#/components/schemas/Node"}}}}},
                "paths": {"/n": {"post": {"operationId": "mk", "requestBody": {
                    "content": {"application/json": {
                        "schema": {"$ref": "#/components/schemas/Node"}}}}}}}}
        tools = OpenAPIToolset(spec_dict=spec).get_tools()
        assert tools[0].input_schema["properties"]

    def test_it_produces_a_usable_openai_tool_dict(self, tools):
        dict_ = tools["createPet"].to_openai_tool()
        assert dict_["type"] == "function"
        assert dict_["function"]["name"] == "createPet"


class TestSelection:

    def test_tool_filter_excludes_operations(self):
        ts = OpenAPIToolset(spec_dict=SPEC,
                            tool_filter=lambda name, method, path: method == "get")
        assert [t.name for t in ts.get_tools()] == ["getPet"]

    def test_a_prefix_is_applied(self):
        ts = OpenAPIToolset(spec_dict=SPEC, tool_name_prefix="petstore_")
        assert all(t.name.startswith("petstore_") for t in ts.get_tools())

    def test_no_spec_at_all_is_refused(self):
        with pytest.raises(ValueError):
            OpenAPIToolset()

    def test_swagger_2_host_and_basepath(self):
        spec = {"swagger": "2.0", "host": "api.old.com", "basePath": "/v2",
                "schemes": ["https"], "paths": {}}
        assert OpenAPIToolset(spec_dict=spec).base_url == "https://api.old.com/v2"


class TestPathParameterSafety:
    """A model-supplied path value must not be able to change the host."""

    def test_an_absolute_value_cannot_hijack_the_url(self, tools):
        from urllib.parse import urlparse

        request = tools["getPet"].build_request(petId="https://attacker.example/x")
        assert request["url"].startswith("https://api.example.com/v1/pets/")
        # The value is encoded into a single path segment; the host stays ours.
        assert urlparse(request["url"]).netloc == "api.example.com"

    def test_traversal_stays_one_segment(self, tools):
        request = tools["getPet"].build_request(petId="../../admin")
        assert request["url"].startswith("https://api.example.com/v1/pets/")
        assert "/admin" not in request["url"]

    def test_a_query_or_fragment_in_a_path_value_is_encoded(self, tools):
        request = tools["getPet"].build_request(petId="a?b#c")
        assert request["url"].endswith("/pets/a%3Fb%23c")


class TestSwagger2Body:
    """Swagger 2 declares the body as an in:body parameter, not requestBody."""

    SWAGGER = {
        "swagger": "2.0", "host": "api.old.com", "basePath": "/v2",
        "schemes": ["https"],
        "paths": {"/pets": {"post": {
            "operationId": "createPet",
            "parameters": [{"name": "pet", "in": "body", "required": True,
                            "schema": {"type": "object", "properties": {
                                "name": {"type": "string"}}}}]}}},
    }

    def _tool(self):
        ts = OpenAPIToolset(spec_dict=self.SWAGGER)
        return next(t for t in ts.get_tools() if t.name == "createPet")

    def test_the_body_argument_is_exposed(self):
        assert "pet" in self._tool().input_schema["properties"]

    def test_the_body_argument_becomes_the_json_body(self):
        request = self._tool().build_request(pet={"name": "Rex"})
        assert request["json"] == {"name": "Rex"}


class TestRelativeServer:
    """A relative server URL in a remotely loaded spec must be resolved."""

    def test_a_relative_server_is_resolved_against_the_spec_url(self):
        spec = {"openapi": "3.0.0", "servers": [{"url": "/v1"}], "paths": {}}
        ts = OpenAPIToolset(spec_dict=spec,
                            spec_url="https://api.example.com/openapi.json")
        assert ts.base_url == "https://api.example.com/v1"


class TestBodyDoesNotLeakFrameworkArgs:
    """Framework-injected kwargs (idempotency_key) must not reach the body."""

    def test_an_undeclared_argument_is_dropped_from_the_body(self, tools):
        request = tools["createPet"].build_request(
            name="Rex", tag="dog", idempotency_key="abc-123")
        assert request["json"] == {"name": "Rex", "tag": "dog"}
        assert "idempotency_key" not in request["json"]


class TestCleartextAuthRefused:
    """Credentials must never be attached to an http:// endpoint."""

    def test_auth_over_http_is_refused(self):
        spec = {"swagger": "2.0", "host": "api.old.com", "basePath": "/v2",
                "schemes": ["http"], "paths": {}}
        with pytest.raises(ValueError, match="http"):
            OpenAPIToolset(spec_dict=spec, auth={"type": "bearer", "token": "T"})

    def test_https_is_preferred_when_offered(self):
        spec = {"swagger": "2.0", "host": "api.old.com", "basePath": "/v2",
                "schemes": ["http", "https"], "paths": {}}
        assert OpenAPIToolset(spec_dict=spec).base_url == "https://api.old.com/v2"

    def test_http_without_auth_is_allowed(self):
        spec = {"swagger": "2.0", "host": "api.old.com", "basePath": "/v2",
                "schemes": ["http"], "paths": {}}
        assert OpenAPIToolset(spec_dict=spec).base_url == "http://api.old.com/v2"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestCredentialedRequestsStayOnOrigin:
    """Two remaining ways a credentialed request could leave for elsewhere.

    Percent-encoding path parameters closes the model-supplied route. These
    cover the spec-supplied one -- a spec is itself untrusted input in the
    "point your agent at this OpenAPI URL" case -- and the hostless URL a
    relative `servers:` entry produces when there is no spec_url to resolve it
    against.
    """

    @staticmethod
    def _op(path="/x", base="https://api.example.com/v1"):
        return OpenAPIOperation(
            name="t", description="d", method="get", path=path,
            parameters=[], base_url=base,
            auth={"type": "bearer", "token": "SECRET-TOKEN"},
            input_schema={}, body_schema=None,
        )

    def test_an_absolute_path_from_the_spec_is_refused(self):
        op = self._op()
        op.path = "https://attacker.example/collect"
        with pytest.raises(ValueError, match="refusing to send credentialed"):
            op.build_request()

    def test_the_refusal_names_both_origins(self):
        op = self._op()
        op.path = "https://attacker.example/collect"
        with pytest.raises(ValueError) as excinfo:
            op.build_request()
        assert "attacker.example" in str(excinfo.value)
        assert "api.example.com" in str(excinfo.value)

    def test_the_tool_returns_the_refusal_rather_than_raising(self):
        """A raising tool ends the turn; a returned error lets the model react."""
        op = self._op()
        op.path = "https://attacker.example/collect"
        assert "refusing to send credentialed" in op()

    def test_a_same_host_scheme_downgrade_is_refused(self):
        """An absolute spec path may keep the host but drop https:// to
        http://; that would leak credentials in the clear, so refuse it."""
        op = self._op()
        op.path = "http://api.example.com/collect"
        with pytest.raises(ValueError, match="refusing to send credentialed"):
            op.build_request()

    def test_an_unresolvable_relative_server_says_what_to_do(self):
        """Previously a hostless URL and an opaque transport error."""
        op = self._op(path="/pets", base="/v1")
        with pytest.raises(ValueError, match="no host to send to"):
            op.build_request()

    def test_an_ordinary_request_is_unaffected(self):
        op = OpenAPIOperation(
            name="t", description="d", method="get", path="/pets/{id}",
            parameters=[{"name": "id", "in": "path"},
                        {"name": "q", "in": "query"}],
            base_url="https://api.example.com/v1", auth={},
            input_schema={}, body_schema=None,
        )
        request = op.build_request(id="42", q="x")
        assert request["url"] == "https://api.example.com/v1/pets/42"
        assert request["params"] == {"q": "x"}


class TestBodySchemasWithoutTopLevelProperties:
    """A body schema need not declare `properties` at the top level.

    Filtering arguments against the declared properties stops framework
    metadata and model hallucinations reaching a strict API. But reading only
    ``schema["properties"]`` finds nothing for two legal and common shapes --
    a free-form object, and a schema composed with allOf/oneOf/anyOf -- and an
    empty allow-set filtered out *every* argument. Those operations advertised
    no body arguments at all and then POSTed an empty body: accepted,
    discarded, reported as success.

    allOf is the standard way real specs say "this object, plus those fields",
    so this covered a large share of real-world POST/PUT operations.
    """

    @staticmethod
    def _tool(schema):
        return OpenAPIToolset(spec_dict={
            "openapi": "3.0.0",
            "servers": [{"url": "https://api.example.com"}],
            "paths": {"/pets": {"post": {
                "operationId": "createPet",
                "requestBody": {"content": {"application/json": {"schema": schema}}},
            }}},
        }).get_tools()[0]

    @pytest.mark.parametrize("schema", [
        {"type": "object"},
        {"type": "object", "additionalProperties": True},
    ], ids=["bare-object", "additionalProperties"])
    def test_a_free_form_body_still_sends_its_arguments(self, schema):
        assert self._tool(schema).build_request(name="Rex")["json"] == {"name": "Rex"}

    def test_a_free_form_body_still_excludes_framework_keys(self):
        """The filter's actual purpose must survive the free-form path."""
        request = self._tool({"type": "object"}).build_request(
            name="Rex", idempotency_key="abc-123")
        assert request["json"] == {"name": "Rex"}

    def test_an_allof_schemas_properties_are_advertised_and_sent(self):
        tool = self._tool({"allOf": [
            {"type": "object", "properties": {"name": {"type": "string"}},
             "required": ["name"]},
            {"type": "object", "properties": {"age": {"type": "integer"}}},
        ]})
        assert set(tool.input_schema["properties"]) >= {"name", "age"}
        assert tool.input_schema["required"] == ["name"]
        assert tool.build_request(name="Rex", age=3)["json"] == {"name": "Rex", "age": 3}

    def test_a_oneof_schema_advertises_the_union(self):
        tool = self._tool({"oneOf": [
            {"type": "object", "properties": {"name": {"type": "string"}}},
            {"type": "object", "properties": {"tag": {"type": "string"}}},
        ]})
        assert set(tool.input_schema["properties"]) >= {"name", "tag"}
        assert tool.build_request(name="Rex")["json"] == {"name": "Rex"}

    def test_a_oneof_branch_requirement_is_not_required_of_the_request(self):
        """A field required by only one branch is not required overall."""
        tool = self._tool({"oneOf": [
            {"type": "object", "properties": {"name": {"type": "string"}},
             "required": ["name"]},
            {"type": "object", "properties": {"tag": {"type": "string"}}},
        ]})
        assert "name" not in tool.input_schema.get("required", [])

    def test_a_nested_allof_is_flattened(self):
        tool = self._tool({"allOf": [
            {"allOf": [{"type": "object", "properties": {"deep": {"type": "string"}}}]},
        ]})
        assert "deep" in tool.input_schema["properties"]
        assert tool.build_request(deep="v")["json"] == {"deep": "v"}

    def test_a_declared_schema_still_filters_undeclared_keys(self):
        """The regression guard: declaring properties must still restrict."""
        tool = self._tool({"type": "object",
                           "properties": {"name": {"type": "string"}}})
        assert tool.build_request(name="Rex", hallucinated="x")["json"] == {"name": "Rex"}

    def test_a_closed_empty_schema_forbids_all_keys(self):
        """additionalProperties:false with no properties is closed, not free-form.

        A free-form body forwards its arguments; a closed empty object permits
        only an empty object, so model-supplied keys must be dropped rather
        than sent to a strict API that would reject them.
        """
        tool = self._tool({"type": "object", "additionalProperties": False})
        assert "json" not in tool.build_request(hallucinated="x")

    def test_a_closed_allof_branch_closes_the_whole_body(self):
        """A closed constraint composed via allOf closes the whole body."""
        tool = self._tool({"allOf": [
            {"type": "object", "properties": {"name": {"type": "string"}}},
            {"type": "object", "additionalProperties": False},
        ]})
        assert tool.build_request(name="Rex", hallucinated="x")["json"] == {"name": "Rex"}

    def test_a_self_referential_composition_does_not_hang(self):
        toolset = OpenAPIToolset(spec_dict={
            "openapi": "3.0.0",
            "servers": [{"url": "https://api.example.com"}],
            "components": {"schemas": {"Node": {
                "allOf": [{"type": "object",
                           "properties": {"child": {"$ref": "#/components/schemas/Node"}}}]}}},
            "paths": {"/n": {"post": {"operationId": "mk", "requestBody": {"content": {
                "application/json": {"schema": {"$ref": "#/components/schemas/Node"}}}}}}},
        })
        assert "child" in toolset.get_tools()[0].input_schema["properties"]
