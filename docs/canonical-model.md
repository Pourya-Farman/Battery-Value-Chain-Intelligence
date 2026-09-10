# Canonical model

This document defines the stable entities that the Silver layer will produce.

## Entity types

| Entity | Stable ID format | Example |
| --- | --- | --- |
| Company | `COMP-###` | `COMP-001` |
| Facility | `FAC-###` | `FAC-001` |
| Product or material | `PROD-###` | `PROD-002` |
| Country | ISO 3166-1 alpha-2 code | `AU` |
| Port | Source port code | `PORT-AU-FRE` |

## Initial canonical records

| Canonical ID | Name | Type |
| --- | --- | --- |
| `COMP-001` | NorthStar Lithium Ltd | raw material supplier |
| `COMP-002` | Northstar Lithium | processor |
| `COMP-003` | Volta Cathode Materials | component manufacturer |
| `COMP-004` | Helios Battery Systems | battery manufacturer |
| `COMP-005` | Electra Motors | EV manufacturer |
| `COMP-006` | Pacific Nickel Co | raw material supplier |
| `FAC-001` | Red Ridge Mine | mine |
| `FAC-002` | Red Ridge Processing Plant | processor |
| `FAC-003` | Busan Cathode Plant | cathode plant |
| `FAC-004` | North Harbor Cell Factory | battery factory |
| `FAC-005` | Wolfsburg Vehicle Plant | EV factory |
| `FAC-006` | Surabaya Nickel Refinery | refinery |

## Important resolution rule

Names are evidence for matching, not proof of identity. `NorthStar Lithium Ltd` and `Northstar Lithium` look similar, but the Bronze data assigns them different companies, facilities, and roles. They must remain separate canonical companies until a trusted cross-system identifier or business rule says otherwise.

Case and punctuation differences can be normalized safely. For example, `NORTHSTAR LITHIUM` and `Northstar Lithium` can be compared using a normalized key, but a name match must still be checked against type, country, facility, and source context.

## Relationships to produce later

```text
Company -[:OWNS]-> Facility
Facility -[:LOCATED_IN]-> Country
Company -[:PRODUCES]-> Product
Company -[:SUPPLIES]-> Company
Product -[:REQUIRES]-> Product
Shipment -[:ORIGINATES_AT]-> Port
Shipment -[:DESTINED_FOR]-> Facility
```