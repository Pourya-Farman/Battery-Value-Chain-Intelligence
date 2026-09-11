# Battery Value Chain Intelligence

A conversational graph application for exploring dependencies across a synthetic battery manufacturing value chain.

The project combines a Bronze-to-Silver data pipeline, Neo4j Aura, OpenAI, and a browser-based graph visualization. Users can ask natural-language questions, inspect the generated Cypher, see database evidence, and explore the matching graph.

## What It Demonstrates

- Multiple source-system integration
- Bronze-to-Silver data engineering
- Entity resolution and canonical IDs
- Neo4j graph modeling and loading
- Runtime schema discovery
- Natural-language questions translated into Cypher
- Cypher validation before database execution
- Grounded LLM explanations based on Neo4j results
- Multi-turn questions and hypothetical impact analysis
- Interactive graph visualization
- A clearly labeled general-LLM fallback for questions outside the graph

This is a focused portfolio prototype, not a production supply-chain platform.

## Business Scenario

The synthetic value chain represents:

```text
Lithium mine
    -> lithium processor
    -> cathode plant
    -> battery factory
    -> EV manufacturer
```

The graph also models companies, facilities, materials, products, countries, ports, shipments, procurement contracts, and product requirements.

Example questions:

- Which products depend on Lithium Carbonate?
- What is the shipment status of SHIP-0002?
- What is the facility type of Wolfsburg Vehicle Plant?
- What will happen if Hamburg Gateway is closed on September 23, 2026?
- What is the downstream effect if NMC Cathode Powder is not provided to VoltEdge 90 Battery Pack?
- Which suppliers or facilities have the largest downstream impact?

## Architecture

```text
Source-system exports
        |
        v
      Bronze
        |
        v
      Silver --------------------+
        |                         |
        v                         v
    Neo4j Aura              Schema discovery
        |                         |
        |                         v
        |                  data/schema/schema.json
        |                         |
        +-----------+-------------+
                    v
              FastAPI backend
                    |
        +-----------+-----------+
        |                       |
        v                       v
   OpenAI planner        Cypher validator
        |                       |
        +-----------+-----------+
                    v
               Neo4j Aura
                    |
                    v
          Rows + graph entities
                    |
                    v
            OpenAI explanation
                    |
                    v
       Browser chat + Cytoscape graph
```

The browser communicates with FastAPI. Neo4j Aura and OpenAI credentials stay on the server and are never sent to the browser.

## Data Pipeline

### Bronze

Bronze preserves synthetic source exports in their source-system shape:

```text
data/bronze/
  erp/
    companies.csv
    facilities.csv
    products.csv
  procurement/
    supplier_contracts.csv
    material_requirements.csv
  logistics/
    ports.csv
    shipments.csv
  reference/
    countries.csv
```

These CSV files are intentionally ignored by Git because they are local synthetic data.

### Silver

Silver creates canonical entities and graph-ready relationships:

```text
data/silver/
  companies.csv
  facilities.csv
  products.csv
  countries.csv
  ports.csv
  core_relationships.csv
  relationships.csv
  logistics_relationships.csv
```

The transformations validate required fields, normalize values, assign stable IDs, preserve source lineage, resolve names, and reject broken references.

Canonical ID examples:

```text
Company   -> COMP-001
Facility  -> FAC-001
Product   -> PROD-001
Country   -> AU
Port      -> PORT-DE-HAM
```

Procurement-only materials are represented as `external_material` products when they are not present in the ERP export.

Run the transformations from the project root:

```bash
python src/battery_value_chain/silver/companies.py
python src/battery_value_chain/silver/facilities.py
python src/battery_value_chain/silver/countries.py
python src/battery_value_chain/silver/ports.py
python src/battery_value_chain/silver/products.py
python src/battery_value_chain/silver/procurement.py
python src/battery_value_chain/silver/logistics.py
python src/battery_value_chain/silver/core_relationships.py
python src/battery_value_chain/silver/validate.py
```

## Graph Model

Nodes:

```text
Company
Facility
Product
Country
Port
Shipment
```

Relationships:

```text
Company  -[:OWNS]->           Facility
Facility -[:LOCATED_IN]->     Country
Company  -[:PRODUCES]->       Product
Company  -[:SUPPLIES]->       Product
Product  -[:REQUIRES]->       Product
Shipment -[:CARRIES]->        Product
Shipment -[:SUPPLIED_BY]->    Company
Shipment -[:ORIGINATES_AT]->  Port
Shipment -[:DESTINED_FOR]->   Port
Shipment -[:RECEIVED_AT]->    Facility
```

Some facts are stored as node properties rather than relationships. For example, a port stores `country_code`; the graph does not invent a `Port-[:LOCATED_IN]->Country` edge.

## Conversational Query Flow

```text
User question
      |
      v
Conversation history + current schema
      |
      v
OpenAI query planner
      |
      v
Structured query plan
      |
      v
Cypher validator
      |
      v
Neo4j Aura
      |
      +--> rows and graph data
      |
      v
OpenAI grounded explanation
      |
      v
Answer + Cypher + evidence + visualization
```

The planner supports:

- `supported`: generate and execute a graph query
- `clarification_needed`: ask the user for more detail
- `unsupported`: route to the general-chat fallback without querying Neo4j
- `conversational`: handle greetings and similar chat without a database query

Conversation history allows follow-ups such as:

```text
User: What if NMC Cathode Powder is not provided to VoltEdge 90 Battery Pack?
User: What is the downstream effect of that?
```

Hypothetical questions are interpreted as impact analysis. The answer distinguishes scheduled graph facts from the hypothetical consequence.

## Query Safety

Generated Cypher is never executed directly from the LLM. The flow is:

```text
LLM -> validator -> Neo4j
```

The validator checks:

- Read-only clauses
- No `CREATE`, `MERGE`, `DELETE`, `DETACH`, `SET`, `REMOVE`, `DROP`, `CALL`, or `LOAD`
- Known labels and relationships
- Correct relationship endpoint patterns
- Numeric `LIMIT` of 50 or less
- Bounded variable-length traversals
- Single statements only

Neo4j credentials should also be read-only for any public deployment. The loader uses separate write-capable credentials locally.

## Web Application

The FastAPI app serves both the backend and the static frontend:

```text
GET  /
GET  /health
GET  /schema
GET  /graph/full
POST /chat
```

The browser includes:

- Scrollable conversation panel
- Natural-language chat box
- Analyst answer
- Generated Cypher
- Evidence rows
- Full graph on initial load
- `Show full network` control
- Cytoscape graph visualization

The full graph uses explicit Neo4j metadata and displays human-readable labels. Attribute queries also show relevant properties, such as shipment status or port country code.

## Local Setup

Requirements:

- Python 3.11 or newer
- A Neo4j Aura instance
- An OpenAI API key

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Create local configuration:

```bash
cp .env.example .env
```

Set the real values in `.env`:

```env
NEO4J_URI=neo4j+s://your-instance.databases.neo4j.io
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your-aura-password
OPENAI_API_KEY=your-openai-api-key
OPENAI_MODEL=gpt-4o-mini
```

Never commit `.env`, Neo4j passwords, or OpenAI keys. `.env.example` is safe to commit because it contains placeholders only.

Verify the Aura connection:

```bash
python src/battery_value_chain/neo4j_connection.py
```

Load the Silver graph:

```bash
python src/battery_value_chain/neo4j_loader.py
```

Refresh the schema registry after graph changes:

```bash
python src/battery_value_chain/schema_discovery.py
```

Run the website:

```bash
python -m uvicorn battery_value_chain.api:app --reload
```

Open http://127.0.0.1:8000.

## Testing

Run the test suite:

```bash
python -m pytest -q
```

Run a syntax check:

```bash
python -m compileall src
```

Tests use fake planners and drivers where possible, so they do not consume OpenAI credit or require a live Neo4j connection. Live smoke tests can be run manually after `.env` is configured.

## Render Deployment

Create a Render Web Service connected to the GitHub repository.

Build Command:

```bash
pip install -e ".[dev]"
```

Start Command:

```bash
python -m uvicorn battery_value_chain.api:app --host 0.0.0.0 --port $PORT
```

Configure these Render environment variables:

```text
NEO4J_URI
NEO4J_USERNAME
NEO4J_PASSWORD
OPENAI_API_KEY
OPENAI_MODEL=gpt-4o-mini
```

Render provides `$PORT` automatically. Do not upload `.env`; configure secrets in the Render dashboard.

## Project Layout

```text
.
├── data/
│   ├── bronze/                 # Ignored raw synthetic CSV exports
│   ├── silver/                 # Ignored generated graph-ready CSVs
│   └── schema/schema.json      # Discovered schema registry
├── docs/canonical-model.md     # Canonical entity and ID model
├── frontend/
│   ├── index.html              # Chat and graph page
│   ├── app.js                  # API calls and Cytoscape rendering
│   └── styles.css              # Responsive visual design
├── src/battery_value_chain/
│   ├── api.py                  # FastAPI application
│   ├── cypher_validator.py     # Query safety boundary
│   ├── llm_query.py            # Prompts and query-plan parsing
│   ├── neo4j_connection.py     # Aura driver setup
│   ├── neo4j_loader.py         # Silver-to-Neo4j loader
│   ├── openai_planner.py       # OpenAI planner implementations
│   ├── query_service.py        # Query orchestration and serialization
│   ├── schema_discovery.py     # Runtime schema registry generation
│   └── silver/                 # Bronze-to-Silver transforms
├── tests/test_package.py       # Unit and API tests
├── .env.example                # Safe environment template
├── pyproject.toml              # Package and dependency configuration
└── .gitignore
```

## Current Limitations

- The source data is synthetic and intentionally small.
- The general-chat fallback is not grounded in Neo4j and is labeled accordingly.
- The LLM can still generate an imperfect query; validation and bounded retries prevent unsafe execution but cannot guarantee semantic perfection.
- The full graph is designed for this prototype-sized dataset, not a large production network.
- Authentication, rate limiting, audit storage, and a dedicated read-only Aura user should be added before public production use.

## License

This project is intended to use the MIT License. Add the standard `LICENSE` file before describing the repository as formally licensed open source.
