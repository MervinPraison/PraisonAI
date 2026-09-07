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

from praisonaiagents.tools.openapi_toolset import OpenAPIToolset

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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
