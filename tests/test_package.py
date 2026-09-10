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