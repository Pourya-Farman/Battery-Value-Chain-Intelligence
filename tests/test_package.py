from battery_value_chain import __version__
from battery_value_chain.silver.companies import build_companies
from battery_value_chain.silver.facilities import build_facilities
from battery_value_chain.silver.products import build_products
from battery_value_chain.silver.countries import build_countries
from battery_value_chain.silver.ports import build_ports
from battery_value_chain.silver.procurement import build_procurement
from battery_value_chain.silver.logistics import build_logistics
from battery_value_chain.silver.core_relationships import build_core_relationships
from battery_value_chain.silver.validate import validate_silver
from battery_value_chain.neo4j_connection import create_driver
import battery_value_chain.neo4j_connection as neo4j_connection
from battery_value_chain.neo4j_loader import _load_direct_relationships
from battery_value_chain.schema_discovery import discover_schema
from battery_value_chain.llm_query import build_query_prompt, parse_query_plan
from battery_value_chain.cypher_validator import validate_cypher
from battery_value_chain.query_service import FakeQueryPlanner, answer_question
from battery_value_chain.llm_query import QueryPlan
from battery_value_chain.llm_query import QueryPlan, build_explanation_prompt
from battery_value_chain.query_service import (
    FakeExplanationPlanner,
    FakeGeneralChatPlanner,
    FakeQueryPlanner,
    answer_question,
)
from battery_value_chain.api import create_app
from fastapi.testclient import TestClient
from battery_value_chain.openai_planner import OpenAIExplanationPlanner, OpenAIQueryPlanner


def test_package_version() -> None:
    assert __version__ == "0.1.0"


def test_build_companies_creates_traceable_canonical_ids(tmp_path) -> None:
    bronze_path = tmp_path / "companies.csv"
    silver_path = tmp_path / "silver" / "companies.csv"
    bronze_path.write_text(
        "company_id,company_name,company_type,country_code\n"
        "ERP-C-001,NorthStar Lithium Ltd,raw_material_supplier,au\n"
        "ERP-C-002,Northstar Lithium,processor,AU\n",
        encoding="utf-8",
    )

    count = build_companies(bronze_path, silver_path)

    assert count == 2
    assert silver_path.read_text(encoding="utf-8") == (
        "company_id,company_name,company_type,country_code,source_company_id\n"
        "COMP-001,NorthStar Lithium Ltd,raw_material_supplier,AU,ERP-C-001\n"
        "COMP-002,Northstar Lithium,processor,AU,ERP-C-002\n"
    )


def test_build_facilities_creates_traceable_canonical_ids(tmp_path) -> None:
    bronze_path = tmp_path / "facilities.csv"
    silver_path = tmp_path / "silver" / "facilities.csv"
    bronze_path.write_text(
        "facility_id,facility_name,facility_type,company_id,country_code\n"
        "ERP-F-001,Red Ridge Mine,mine,ERP-C-001,au\n",
        encoding="utf-8",
    )

    count = build_facilities(bronze_path, silver_path)

    assert count == 1
    assert silver_path.read_text(encoding="utf-8") == (
        "facility_id,facility_name,facility_type,country_code,"
        "source_facility_id,source_company_id\n"
        "FAC-001,Red Ridge Mine,mine,AU,ERP-F-001,ERP-C-001\n"
    )


def test_build_products_creates_traceable_canonical_ids(tmp_path) -> None:
    bronze_path = tmp_path / "products.csv"
    silver_path = tmp_path / "silver" / "products.csv"
    bronze_path.write_text(
        "product_id,product_name,product_type,owner_company_id\n"
        "ERP-P-001,Spodumene Concentrate,raw_material,ERP-C-001\n",
        encoding="utf-8",
    )

    count = build_products(bronze_path, silver_path)

    assert count == 1
    assert silver_path.read_text(encoding="utf-8") == (
        "product_id,product_name,product_type,source_product_id,"
        "source_owner_company_id\n"
        "PROD-001,Spodumene Concentrate,raw_material,ERP-P-001,ERP-C-001\n"
    )


def test_build_products_adds_procurement_only_materials(tmp_path) -> None:
    bronze_path = tmp_path / "products.csv"
    supplemental_path = tmp_path / "requirements.csv"
    silver_path = tmp_path / "silver" / "products.csv"
    bronze_path.write_text(
        "product_id,product_name,product_type,owner_company_id\n"
        "ERP-P-001,Lithium Carbonate,processed_material,ERP-C-002\n",
        encoding="utf-8",
    )
    supplemental_path.write_text(
        "requirement_id,buyer_product,required_material,quantity_per_unit_kg\n"
        "MR-001,NMC Cathode Powder,Nickel Sulphate,0.42\n",
        encoding="utf-8",
    )

    assert build_products(bronze_path, silver_path, (supplemental_path,)) == 2
    assert "PROD-002,Nickel Sulphate,external_material,,\n" in silver_path.read_text(
        encoding="utf-8"
    )


def test_build_countries_normalizes_iso_codes(tmp_path) -> None:
    bronze_path = tmp_path / "countries.csv"
    silver_path = tmp_path / "silver" / "countries.csv"
    bronze_path.write_text(
        "country_code,country_name,region\nau,Australia,Oceania\n",
        encoding="utf-8",
    )

    assert build_countries(bronze_path, silver_path) == 1
    assert silver_path.read_text(encoding="utf-8") == (
        "country_code,country_name,region\nAU,Australia,Oceania\n"
    )


def test_build_ports_normalizes_codes(tmp_path) -> None:
    bronze_path = tmp_path / "ports.csv"
    silver_path = tmp_path / "silver" / "ports.csv"
    bronze_path.write_text(
        "port_code,port_name,country_code,port_type\n"
        "port-au-fre,Port Fremantle,au,seaport\n",
        encoding="utf-8",
    )

    assert build_ports(bronze_path, silver_path) == 1
    assert silver_path.read_text(encoding="utf-8") == (
        "port_code,port_name,country_code,port_type\n"
        "PORT-AU-FRE,Port Fremantle,AU,seaport\n"
    )


def test_build_procurement_resolves_names_to_canonical_ids(tmp_path) -> None:
    contracts = tmp_path / "contracts.csv"
    requirements = tmp_path / "requirements.csv"
    companies = tmp_path / "companies.csv"
    products = tmp_path / "products.csv"
    output = tmp_path / "silver" / "relationships.csv"
    contracts.write_text(
        "contract_id,supplier_name,supplied_material,buyer_company,contract_status,annual_volume_tonnes\n"
        "PO-1,Northstar Lithium,lithium carbonate,Volta Cathode Materials,active,12\n",
        encoding="utf-8",
    )
    requirements.write_text(
        "requirement_id,buyer_product,required_material,quantity_per_unit_kg\n"
        "MR-1,NMC Cathode Powder,Lithium Carbonate,0.19\n",
        encoding="utf-8",
    )
    companies.write_text(
        "company_id,company_name\nCOMP-002,Northstar Lithium\nCOMP-003,Volta Cathode Materials\n",
        encoding="utf-8",
    )
    products.write_text(
        "product_id,product_name\nPROD-002,Lithium Carbonate\nPROD-003,NMC Cathode Powder\n",
        encoding="utf-8",
    )

    assert build_procurement(contracts, requirements, companies, products, output) == 2
    assert "SUPPLIES,COMP-002,PROD-002,PO-1,COMP-003,12\n" in output.read_text()
    assert "REQUIRES,PROD-003,PROD-002,MR-1,,0.19\n" in output.read_text()


def test_build_logistics_resolves_shipment_references(tmp_path) -> None:
    shipments = tmp_path / "shipments.csv"
    ports = tmp_path / "ports.csv"
    facilities = tmp_path / "facilities.csv"
    companies = tmp_path / "companies.csv"
    products = tmp_path / "products.csv"
    output = tmp_path / "silver" / "logistics.csv"
    shipments.write_text(
        "shipment_id,material_name,supplier_name,origin_port,destination_port,"
        "receiving_facility,planned_arrival,status\n"
        "SHIP-1,Lithium Carbonate,Northstar Lithium,PORT-AU-FRE,PORT-KR-BUS,"
        "Busan Cathode Plant,2026-09-21,PLANNED\n",
        encoding="utf-8",
    )
    ports.write_text("port_code\nPORT-AU-FRE\nPORT-KR-BUS\n", encoding="utf-8")
    facilities.write_text("facility_name,facility_id\nBusan Cathode Plant,FAC-003\n", encoding="utf-8")
    companies.write_text("company_name,company_id\nNorthstar Lithium,COMP-002\n", encoding="utf-8")
    products.write_text("product_name,product_id\nLithium Carbonate,PROD-002\n", encoding="utf-8")

    assert build_logistics(shipments, ports, facilities, companies, products, output) == 1
    assert "SHIPPED,SHIP-1,PROD-002,COMP-002,PORT-AU-FRE,PORT-KR-BUS,FAC-003,2026-09-21,planned\n" in output.read_text()


def test_build_core_relationships_links_entities(tmp_path) -> None:
    companies = tmp_path / "companies.csv"
    facilities = tmp_path / "facilities.csv"
    countries = tmp_path / "countries.csv"
    products = tmp_path / "products.csv"
    output = tmp_path / "silver" / "core.csv"
    companies.write_text(
        "company_id,company_name,company_type,country_code,source_company_id\n"
        "COMP-001,NorthStar Lithium,processor,AU,ERP-C-001\n",
        encoding="utf-8",
    )
    facilities.write_text(
        "facility_id,facility_name,facility_type,country_code,source_facility_id,source_company_id\n"
        "FAC-001,Red Ridge Plant,processor,AU,ERP-F-001,ERP-C-001\n",
        encoding="utf-8",
    )
    countries.write_text("country_code,country_name,region\nAU,Australia,Oceania\n", encoding="utf-8")
    products.write_text(
        "product_id,product_name,product_type,source_product_id,source_owner_company_id\n"
        "PROD-001,Lithium Carbonate,material,ERP-P-001,ERP-C-001\n",
        encoding="utf-8",
    )

    assert build_core_relationships(companies, facilities, countries, products, output) == 3
    contents = output.read_text(encoding="utf-8")
    assert "OWNS,COMP-001,FAC-001,ERP-F-001\n" in contents
    assert "LOCATED_IN,FAC-001,AU,ERP-F-001\n" in contents
    assert "PRODUCES,COMP-001,PROD-001,ERP-P-001\n" in contents


def test_validate_silver_rejects_orphaned_relationship(tmp_path) -> None:
    silver = tmp_path / "silver"
    silver.mkdir()
    (silver / "companies.csv").write_text(
        "company_id,company_name,source_company_id\nCOMP-001,Example,ERP-C-001\n",
        encoding="utf-8",
    )
    (silver / "facilities.csv").write_text(
        "facility_id,facility_name,source_facility_id,source_company_id,country_code\n",
        encoding="utf-8",
    )
    (silver / "countries.csv").write_text("country_code,country_name\nAU,Australia\n", encoding="utf-8")
    (silver / "products.csv").write_text(
        "product_id,product_name,source_product_id,source_owner_company_id\n",
        encoding="utf-8",
    )
    (silver / "ports.csv").write_text("port_code,port_name\nPORT-AU-FRE,Port Fremantle\n", encoding="utf-8")
    (silver / "core_relationships.csv").write_text(
        "relationship_type,source_id,target_id,source_reference\n"
        "OWNS,COMP-001,FAC-999,ERP-F-999\n",
        encoding="utf-8",
    )
    (silver / "relationships.csv").write_text(
        "relationship_type,source_id,target_id\n",
        encoding="utf-8",
    )
    (silver / "logistics_relationships.csv").write_text(
        "relationship_type,product_id,supplier_company_id,origin_port_code,destination_port_code,receiving_facility_id\n",
        encoding="utf-8",
    )

    try:
        validate_silver(silver)
    except ValueError as error:
        assert "orphaned relationship" in str(error)
    else:
        raise AssertionError("Expected orphaned relationship validation error")


def test_create_driver_requires_credentials(monkeypatch) -> None:
    monkeypatch.setattr(neo4j_connection, "load_dotenv", lambda: None)
    monkeypatch.delenv("NEO4J_URI", raising=False)
    monkeypatch.delenv("NEO4J_USERNAME", raising=False)
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)

    try:
        create_driver()
    except RuntimeError as error:
        assert "NEO4J_URI" in str(error)
    else:
        raise AssertionError("Expected missing Neo4j configuration error")


def test_loader_uses_entity_specific_relationship_keys(tmp_path) -> None:
    relationship_path = tmp_path / "core_relationships.csv"
    relationship_path.write_text(
        "relationship_type,source_id,target_id,source_reference\n"
        "OWNS,COMP-001,FAC-001,ERP-F-001\n"
        "LOCATED_IN,FAC-001,AU,ERP-F-001\n",
        encoding="utf-8",
    )

    class FakeDriver:
        def __init__(self) -> None:
            self.queries: list[str] = []

        def execute_query(self, query: str, **parameters: object) -> None:
            self.queries.append(query)

    driver = FakeDriver()

    assert _load_direct_relationships(driver, relationship_path) == 2
    assert "Company {company_id: row.source_id}" in driver.queries[0]
    assert "Facility {facility_id: row.target_id}" in driver.queries[0]
    assert "Country {country_code: row.target_id}" in driver.queries[1]


def test_discover_schema_normalizes_neo4j_metadata() -> None:
    class FakeRecord(dict):
        pass

    class FakeResult:
        def __init__(self, records: list[FakeRecord]) -> None:
            self.records = records

    class FakeDriver:
        def execute_query(self, query: str) -> FakeResult:
            if "nodeTypeProperties" in query:
                return FakeResult(
                    [
                        FakeRecord(nodeType=":Product", propertyName="product_id"),
                        FakeRecord(nodeType=":Product", propertyName="product_name"),
                        FakeRecord(nodeType=":Company", propertyName="company_id"),
                    ]
                )
            if "MATCH (source)-[relationship]" in query:
                return FakeResult(
                    [
                        FakeRecord(
                            source_label="Company",
                            relationship_type="SUPPLIES",
                            target_label="Product",
                        )
                    ]
                )
            return FakeResult(
                [
                    FakeRecord(
                        node_type="Product",
                        property_name="product_name",
                        values=["Lithium Carbonate"],
                    )
                ]
            )

    schema = discover_schema(FakeDriver())

    assert schema["nodes"] == {
        "Company": ["company_id"],
        "Product": ["product_id", "product_name"],
    }
    assert schema["relationships"] == [
        {"source": "Company", "type": "SUPPLIES", "target": "Product"}
    ]
    assert schema["known_values"] == {"Product": {"product_name": ["Lithium Carbonate"]}}


def test_build_query_prompt_includes_current_schema() -> None:
    messages = build_query_prompt(
        "Which products depend on Lithium Carbonate?",
        {"nodes": {"Product": ["product_name"]}, "relationships": []},
    )

    assert messages[0]["role"] == "system"
    assert "Product" in messages[1]["content"]
    assert "Lithium Carbonate" in messages[1]["content"]
    assert "not an exhaustive catalog" in messages[0]["content"]
    assert "Conversational framing" in messages[0]["content"]


def test_parse_query_plan_accepts_supported_response() -> None:
    plan = parse_query_plan(
        '{"status":"supported","reason":null,'
        '"cypher":"MATCH (p:Product) RETURN p LIMIT 10",'
        '"parameters":{},"suggestions":[]}'
    )

    assert plan.status == "supported"
    assert plan.cypher.endswith("LIMIT 10")


def test_parse_query_plan_rejects_cypher_for_unsupported_response() -> None:
    try:
        parse_query_plan(
            '{"status":"unsupported","reason":"No data",'
            '"cypher":"MATCH (n) RETURN n", "parameters":{}, "suggestions":[]}'
        )
    except ValueError as error:
        assert "must not include Cypher" in str(error)
    else:
        raise AssertionError("Expected unsupported plan with Cypher to fail")


def test_parse_query_plan_normalizes_null_optional_fields() -> None:
    plan = parse_query_plan(
        '{"status":"supported",'
        '"cypher":"MATCH (f:Facility) RETURN f.facility_type LIMIT 10",'
        '"parameters":null,"suggestions":null}'
    )

    assert plan.parameters == {}
    assert plan.suggestions == []


def test_validate_cypher_accepts_bounded_known_query() -> None:
    schema = {
        "nodes": {"Product": ["product_name"]},
        "relationships": [{"type": "REQUIRES"}],
    }

    validate_cypher(
        "MATCH (product:Product)-[:REQUIRES*1..5]->(dependency:Product) "
        "RETURN product, dependency LIMIT 25",
        schema,
    )


def test_validate_cypher_rejects_mutation_and_unbounded_query() -> None:
    schema = {"nodes": {"Product": []}, "relationships": []}

    for query, expected in (
        ("MATCH (n:Product) DELETE n", "DELETE"),
        ("MATCH (n:Product) RETURN n", "LIMIT"),
        ("MATCH (a:Product)-[:REQUIRES*1..]->(b:Product) RETURN b LIMIT 10", "maximum depth"),
    ):
        try:
            validate_cypher(query, schema)
        except ValueError as error:
            assert expected in str(error)
        else:
            raise AssertionError("Expected Cypher validation error")


def test_validate_cypher_rejects_invalid_relationship_endpoints() -> None:
    schema = {
        "nodes": {"Port": [], "Country": [], "Facility": []},
        "relationships": [{"source": "Facility", "type": "LOCATED_IN", "target": "Country"}],
    }

    try:
        validate_cypher(
            "MATCH (port:Port)-[:LOCATED_IN]->(country:Country) "
            "RETURN port LIMIT 10",
            schema,
        )
    except ValueError as error:
        assert "does not connect" in str(error)
    else:
        raise AssertionError("Expected invalid relationship endpoint error")


def test_answer_question_validates_and_executes_supported_plan() -> None:
    schema = {"nodes": {"Product": ["product_name"]}, "relationships": []}
    planner = FakeQueryPlanner(
        QueryPlan(
            status="supported",
            cypher="MATCH (product:Product) RETURN product LIMIT 10",
            parameters={},
        )
    )

    class FakeRecord:
        def data(self) -> dict[str, str]:
            return {"product": "Lithium Carbonate"}

    class FakeResult:
        records = [FakeRecord()]

    class FakeDriver:
        def __init__(self) -> None:
            self.cypher = ""

        def execute_query(self, cypher: str, **parameters: object) -> FakeResult:
            self.cypher = cypher
            return FakeResult()

    driver = FakeDriver()
    response = answer_question("Which products exist?", schema, planner, driver)

    assert response["status"] == "supported"
    assert response["rows"] == [{"product": "Lithium Carbonate"}]
    assert driver.cypher.endswith("LIMIT 50")


def test_answer_question_sends_rows_to_grounded_explanation_planner() -> None:
    schema = {"nodes": {"Product": ["product_name"]}, "relationships": []}
    planner = FakeQueryPlanner(
        QueryPlan(
            status="supported",
            cypher="MATCH (product:Product) RETURN product LIMIT 10",
            parameters={},
        )
    )
    explanation = FakeExplanationPlanner("Lithium Carbonate is in the graph.")

    class FakeRecord:
        def data(self) -> dict[str, str]:
            return {"product": "Lithium Carbonate"}

    class FakeResult:
        records = [FakeRecord()]

    class FakeDriver:
        def execute_query(self, cypher: str, **parameters: object) -> FakeResult:
            return FakeResult()

    response = answer_question(
        "Which products exist?", schema, planner, FakeDriver(), explanation
    )

    assert response["answer"] == "Lithium Carbonate is in the graph."
    assert "Lithium Carbonate" in explanation.messages[1]["content"]


def test_build_explanation_prompt_contains_database_evidence() -> None:
    messages = build_explanation_prompt(
        "What depends on lithium?", "MATCH (n) RETURN n LIMIT 5", {}, [{"name": "Lithium"}]
    )

    assert "What depends on lithium?" in messages[1]["content"]
    assert "Lithium" in messages[1]["content"]


def test_chat_endpoint_returns_orchestrated_response() -> None:
    schema = {"nodes": {"Product": ["product_name"]}, "relationships": []}
    planner = FakeQueryPlanner(
        QueryPlan(
            status="supported",
            cypher="MATCH (product:Product) RETURN product LIMIT 10",
            parameters={},
        )
    )
    explanation = FakeExplanationPlanner("Lithium Carbonate is in the graph.")

    class FakeRecord:
        def data(self) -> dict[str, str]:
            return {"product": "Lithium Carbonate"}

    class FakeResult:
        records = [FakeRecord()]

    class FakeDriver:
        def execute_query(self, cypher: str, **parameters: object) -> FakeResult:
            return FakeResult()

    client = TestClient(create_app(schema, planner, explanation, FakeDriver()))
    response = client.post("/chat", json={"question": "Which products exist?"})

    assert response.status_code == 200
    assert response.json()["answer"] == "Lithium Carbonate is in the graph."


def test_chat_endpoint_reports_unconfigured_services() -> None:
    client = TestClient(create_app(schema={"nodes": {}, "relationships": []}))

    response = client.post("/chat", json={"question": "What exists?"})

    assert response.status_code == 503


def test_openai_query_planner_parses_json_response() -> None:
    class FakeMessage:
        content = '{"status":"unsupported","reason":"Not in graph","parameters":{},"suggestions":[]}'

    class FakeChoice:
        message = FakeMessage()

    class FakeCompletions:
        def create(self, **kwargs: object) -> object:
            return type("Response", (), {"choices": [FakeChoice()]})()

    client = type("Client", (), {"chat": type("Chat", (), {"completions": FakeCompletions()})()})()
    planner = OpenAIQueryPlanner(client=client, model="test-model")

    plan = planner.plan(build_query_prompt("What is the weather?", {}))

    assert plan.status == "unsupported"


def test_openai_query_planner_bounds_supported_query() -> None:
    class FakeMessage:
        content = '{"status":"supported","cypher":"MATCH (n:Product) RETURN n","parameters":{},"suggestions":[]}'

    class FakeChoice:
        message = FakeMessage()

    class FakeCompletions:
        def create(self, **kwargs: object) -> object:
            return type("Response", (), {"choices": [FakeChoice()]})()

    client = type("Client", (), {"chat": type("Chat", (), {"completions": FakeCompletions()})()})()
    planner = OpenAIQueryPlanner(client=client, model="test-model")

    plan = planner.plan([])

    assert plan.cypher.endswith("LIMIT 50")


def test_openai_explanation_planner_returns_text() -> None:
    class FakeMessage:
        content = "No matching data was found."

    class FakeChoice:
        message = FakeMessage()

    class FakeCompletions:
        def create(self, **kwargs: object) -> object:
            return type("Response", (), {"choices": [FakeChoice()]})()

    client = type("Client", (), {"chat": type("Chat", (), {"completions": FakeCompletions()})()})()
    planner = OpenAIExplanationPlanner(client=client, model="test-model")

    assert planner.explain([]) == "No matching data was found."


def test_answer_question_does_not_execute_unsupported_plan() -> None:
    planner = FakeQueryPlanner(
        QueryPlan(status="unsupported", reason="Weather is not in the graph")
    )

    class FakeDriver:
        def execute_query(self, *args: object, **kwargs: object) -> None:
            raise AssertionError("Unsupported plan must not reach Neo4j")

    response = answer_question("What is the weather?", {}, planner, FakeDriver())

    assert response["status"] == "unsupported"
    assert response["rows"] == []


def test_unsupported_question_can_use_scoped_general_chat() -> None:
    planner = FakeQueryPlanner(QueryPlan(status="unsupported", reason="No contact data"))
    general = FakeGeneralChatPlanner("Use an official port authority directory.")

    class FakeDriver:
        def execute_query(self, *args: object, **kwargs: object) -> None:
            raise AssertionError("Out-of-scope question must not reach Neo4j")

    response = answer_question(
        "What is the phone number for Hamburg Gateway?",
        {},
        planner,
        FakeDriver(),
        general_chat_planner=general,
    )

    assert response["status"] == "general_answer"
    assert "not generated by executing a database query" in response["answer"]
    assert "official port authority" in response["answer"]


def test_answer_question_handles_greeting_without_planner_or_database() -> None:
    class ExplodingPlanner:
        def plan(self, messages: list[dict[str, str]]) -> QueryPlan:
            raise AssertionError("A greeting should not reach the query planner")

    class ExplodingDriver:
        def execute_query(self, *args: object, **kwargs: object) -> None:
            raise AssertionError("A greeting should not reach Neo4j")

    response = answer_question("Hi!", {}, ExplodingPlanner(), ExplodingDriver())

    assert response["status"] == "conversational"
    assert response["cypher"] is None
    assert response["answer"].startswith("Hi.")