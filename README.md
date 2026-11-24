<h1 align="center">🏠🌦️ HypoClimate</h1>

<p align="center">
  <b>Climate risk of any Swiss address, in CHF, for mortgages.</b><br>
  Flood, heavy rain, hail, storm, rockfall and avalanche, plus heating and CO₂, built only on free, official Swiss open data.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-2F80ED?style=flat-square&logo=python&logoColor=white&labelColor=0B1F33" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/data-Swiss_open_government_data-D7263D?style=flat-square&labelColor=0B1F33" alt="Swiss open government data">
  <img src="https://img.shields.io/badge/regulation-FINMA_Circular_2026%2F1-2F80ED?style=flat-square&labelColor=0B1F33" alt="FINMA Circular 2026/1">
  <img src="https://img.shields.io/badge/status-prototype-D7263D?style=flat-square&labelColor=0B1F33" alt="Prototype">
</p>

<p align="center">
  <a href="#about">About</a> &nbsp;·&nbsp; <a href="#architecture">Architecture</a> &nbsp;·&nbsp; <a href="#data">Data</a> &nbsp;·&nbsp; <a href="#screens">Screens</a> &nbsp;·&nbsp; <a href="#build-plan">Build plan</a>
</p>

---

<a id="about"></a>

## 🌍 What is HypoClimate?

A user types in a Swiss address. HypoClimate asks several federal data sources about that spot and shows, in one view:

- 🌊 **Natural hazards today**: river flooding, surface runoff after heavy rain, hail, storm, rockfall and avalanches
- 🏢 **The building**: age, flats and heating system from the federal building register, plus roof solar potential
- 🔥 **Transition risk**: how exposed the building is to the move away from oil and gas heating
- 📈 **The 50-year trend**: how heavy rain changes if warming rises
- 💰 **What it means in CHF**: value discount in a flood zone, loan-to-value, CO₂ levy, heat-pump cost, solar income

**Why now:** FINMA Circular 2026/1 "Nature-related financial risks" requires banks to assess climate risks in their mortgage books. In Switzerland, physical damage to buildings is mostly covered by mandatory building insurance, so the real risks for banks and owners are **lost property value, transition costs and uninsured costs**. HypoClimate focuses on exactly these.

<a id="architecture"></a>

## 🏗️ Architecture

One Python engine does all the work. The screens, the web API and the command-line tools only call that engine and show its **one JSON answer**, so every number is calculated in one place.

```mermaid
flowchart LR
    subgraph who [WHO USES IT]
        direction TB
        adv[Mortgage advisor]:::user
        risk[Bank risk team<br/>FINMA reporting]:::user
        brk[Brokers & platforms]:::user
    end

    subgraph access [SCREENS & ACCESS]
        direction TB
        ui[Streamlit app<br/>4 screens]:::front
        api[Web API<br/>GET /score]:::front
        cli[Command line<br/>batch · disaster test]:::front
    end

    subgraph core [HYPOCLIMATE ENGINE · Python]
        direction TB
        eng[engine.py<br/>1 collect → 2 evaluate]:::core
        cfg[config.py<br/>rules & CHF assumptions]:::core
        geo[geoadmin.py<br/>federal API client]:::core
        port[portfolio.py · report.py · maps.py]:::core
    end

    subgraph data [FREE OFFICIAL SWISS OPEN DATA · geo.admin.ch]
        direction TB
        addr[swisstopo<br/>address search]:::data
        haz[FOEN · MeteoSwiss<br/>flood · runoff · hail · storm<br/>rockfall · avalanche]:::data
        gwr[FSO building register<br/>age · flats · heating]:::data
        sol[SFOE solar roofs<br/>& heat demand]:::data
        ch25[MeteoSwiss CH2025<br/>climate scenarios]:::planned
    end

    out[One JSON answer<br/>scores · hazards · CHF<br/>+ advisor & portfolio reports]:::io

    adv --> ui
    risk --> ui
    brk --> api
    ui --> eng
    api --> eng
    cli --> eng
    ui --> port --> eng
    eng --> cfg
    eng --> geo
    geo --> addr & haz & gwr & sol
    eng -. planned .-> ch25
    eng --> out

    classDef user fill:#0B1F33,stroke:#2F80ED,stroke-width:1.5px,color:#E6EDF3
    classDef front fill:#2F80ED,stroke:#0B1F33,stroke-width:1.5px,color:#FFFFFF
    classDef core fill:#D7263D,stroke:#0B1F33,stroke-width:1.5px,color:#FFFFFF
    classDef data fill:#E8F1FB,stroke:#2F80ED,stroke-width:1.5px,color:#0B1F33
    classDef planned fill:#F5F5F5,stroke:#9E9E9E,stroke-width:1.5px,stroke-dasharray:5 5,color:#555555
    classDef io fill:#0B1F33,stroke:#D7263D,stroke-width:2px,color:#E6EDF3
```

<details>
<summary><b>The parts and how they connect</b></summary>

| Part | File | Talks to | Job |
|---|---|---|---|
| Screens | `app.py` | engine, portfolio, report, maps | Address check · Bank portfolio · Method & data · Tests |
| Web API | `api.py` | engine | `GET /score` for brokers, platforms or another front end |
| Command line | `batch.py`, `disaster_test.py` | engine | Score a CSV of addresses; check real disaster places |
| Engine | `engine.py` | geoadmin, config, example data | Step 1 collects facts, step 2 turns them into scores and CHF figures |
| Rules | `config.py` | – | Every threshold and CHF assumption, in one place |
| API client | `geoadmin.py` | geo.admin.ch | Address search, hazard layers, building register, solar roofs |
| Portfolio | `portfolio.py` | engine | Scores a whole mortgage book and sums it up |
| Reports | `report.py` | – | Printable advisor report and portfolio report |
| Maps | `maps.py` | swisstopo tiles in the browser | Map with switchable federal hazard layers |
| Example data | `example_data.py`, `example_portfolio.py` | – | Offline demo; the example mortgage book is invented |

</details>

### 🔄 What happens when an advisor checks an address

```mermaid
sequenceDiagram
    autonumber
    actor A as Advisor
    participant UI as Streamlit screen
    participant E as engine.py
    participant G as geoadmin.py
    participant F as geo.admin.ch (federal APIs)
    A->>UI: Address, property value, mortgage
    UI->>E: score(address, value, mortgage)
    E->>G: geocode(address)
    G->>F: SearchServer (swisstopo)
    F-->>G: coordinates (LV95) + building ID (EGID)
    par 7 hazard layers, asked separately
        G->>F: identify: flood 100 / 300+, runoff, hail, storm, rockfall, avalanche
        F-->>G: inside zone? / value
    end
    G->>F: building register (EGID)
    F-->>G: age, floors, flats, heating
    G->>F: solar roofs near the point
    F-->>G: roof class, solar yield, heat demand
    E->>E: evaluate: scores 1-5 + CHF figures (rules in config.py)
    E-->>UI: one JSON answer
    UI-->>A: scores, map, CHF table, advisor report
```

The seven hazard layers are asked **separately and at the same time**. If one layer fails, only that hazard shows "No data" and the screen names the source that failed.

<a id="data"></a>

## 🗺️ Data sources

All data is official, free and covers all of Switzerland (geo.admin.ch, open government data).

| Data | Provider | Layer | Used for |
|---|---|---|---|
| Address search | swisstopo | SearchServer | Coordinates and building ID (EGID) |
| River flood areas 100 / 300-yr+ | FOEN | `ch.bafu.aquaprotect_100` / `_500` | Flood score |
| Surface runoff | FOEN | `ch.bafu.gefaehrdungskarte-oberflaechenabfluss` | Heavy-rain score |
| Hail size, 50-yr | MeteoSwiss | `ch.meteoschweiz.hagelgefaehrdung-korngroesse_50_jahre` | Hail score |
| Storm gusts, 50-yr | FOEN | `ch.bafu.sturm-boeenspitzen_50` | Storm score |
| Rockfall, avalanche | FOEN | `ch.bafu.silvaprotect-sturz` / `-lawinen` | Mountain hazards |
| Building register | FSO | `ch.bfs.gebaeude_wohnungs_register` | Age, flats, heating → transition score |
| Solar roofs and heat demand | SFOE | `ch.bfe.solarenergie-eignung-daecher` | Solar income, CO₂ levy |
| Base map and hazard map layers | swisstopo, FOEN, MeteoSwiss | WMTS / WMS | Maps in the browser |
| Climate scenarios CH2025 | MeteoSwiss & ETH Zurich | download | 50-year trend (planned) |

<a id="screens"></a>

## 🖥️ Screens

| Screen | For | What it shows |
|---|---|---|
| **Address check** | Mortgage advisor | Physical and transition score (1–5), hazards, building and energy, CHF figures, heavy-rain trend, map, advisor report |
| **Bank portfolio** | Bank risk team | Key figures for the whole book, map of loans, hazard levels, heating mix, highest-risk loans, report and CSV export |
| **Method & data** | Everyone, incl. FINMA | Every source and every assumption |
| **Tests** | Project team | Disaster test on real disaster places |

<a id="build-plan"></a>

## 🚧 Build plan

| Step | What is added | Status |
|---|---|---|
| 1 | Architecture, rules and assumptions (`config.py`) | ✅ done |
| 2 | Federal geodata API client | ✅ done |
| 3 | Scoring engine with example data | ⏳ next |
| 4 | Batch scoring and technical test | planned |
| 5 | Web API for front ends | planned |
| 6 | Maps with swisstopo and hazard layers | planned |
| 7 | Printable advisor report | planned |
| 8 | Mortgage-book scoring and portfolio report | planned |
| 9 | Disaster test | planned |
| 10 | Prototype screens | planned |

Install (on your laptop, in this folder): `pip install -r requirements.txt`

<a id="team"></a>

## 👥 Team

UZH seminar *FinTech & InsurTech – Digitalization of the Financial Services Industry* (HS 2026), Group 14:
Marko Caric · Adam Branny · Léonard Matteo Ménard · Alessandro Michele Caputo · Arjun Singh Bhadoria · Alikhan Kharezov
