# Graph Report - Specpoint Vault  (2026-10-08)

## Corpus Check
- Corpus is ~13,589 words - fits in a single context window. You may not need a graph.

## Summary
- 85 nodes · 330 edges · 9 communities
- Extraction: 100% EXTRACTED · 0% INFERRED · 0% AMBIGUOUS
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Diffusion, respiration and active transport
- Biology map, molecules and later topics
- Osmosis and water in cells
- Your subjects and study pages
- Cell types and nutrition
- Specialised cells and organisation
- Size of specimens and magnification
- Bacteria, DNA and biotechnology
- Cells for transport and defence

## God Nodes (most connected - your core abstractions)
1. `Biology 2 Organisation of the organism` - 47 edges
2. `Biology 3 Movement into and out of cells` - 34 edges
3. `Biology` - 33 edges
4. `Biology 2.1 Cell structure` - 30 edges
5. `Biology 3.2 Osmosis` - 18 edges
6. `Osmosis` - 15 edges
7. `Cell membrane` - 14 edges
8. `Biology 3.3 Active transport` - 13 edges
9. `Biology 8 Transport in plants` - 13 edges
10. `Diffusion` - 13 edges

## Surprising Connections (you probably didn't know these)
- `Biology 2.1 Cell structure` --references--> `Biology`  [EXTRACTED]
  Biology/Notes/Biology 2.1 Cell structure.md → Subjects/Biology.md
- `Biology 2.2 Size of specimens` --references--> `Biology`  [EXTRACTED]
  Biology/Notes/Biology 2.2 Size of specimens.md → Subjects/Biology.md
- `Biology 3.1 Diffusion` --references--> `Biology`  [EXTRACTED]
  Biology/Notes/Biology 3.1 Diffusion.md → Subjects/Biology.md
- `Biology 3.2 Osmosis` --references--> `Biology`  [EXTRACTED]
  Biology/Notes/Biology 3.2 Osmosis.md → Subjects/Biology.md
- `Biology 3.3 Active transport` --references--> `Biology`  [EXTRACTED]
  Biology/Notes/Biology 3.3 Active transport.md → Subjects/Biology.md

## Hyperedges (group relationships)
- **Levels of organisation** — biology_key_terms_specialised_cell, biology_key_terms_tissue, biology_key_terms_organ, biology_key_terms_organ_system [EXTRACTED 1.00]
- **Ways substances move in and out of cells** — biology_key_terms_diffusion, biology_key_terms_osmosis, biology_key_terms_active_transport [EXTRACTED 1.00]
- **What happens to plant cells in different solutions** — biology_key_terms_turgid, biology_key_terms_flaccid, biology_key_terms_plasmolysis, biology_key_terms_turgor_pressure [EXTRACTED 1.00]
- **Structures only plant cells have** — biology_key_terms_cell_wall, biology_key_terms_chloroplasts, biology_key_terms_large_permanent_vacuole [EXTRACTED 1.00]

## Communities (9 total, 0 thin omitted)

### Community 0 - "Diffusion, respiration and active transport"
Cohesion: 0.38
Nodes (17): Biology 3 Flashcards, Active transport, Cell membrane, Concentration gradient, Diffusion, Kinetic energy, Mitochondria, Protein carriers (+9 more)

### Community 1 - "Biology map, molecules and later topics"
Cohesion: 0.28
Nodes (13): Cytoplasm, Ribosomes, Biology 13 Excretion in humans, Biology 14 Coordination and response, Biology 15 Drugs, Biology 16 Reproduction, Biology 17 Inheritance, Biology 18 Variation and selection (+5 more)

### Community 2 - "Osmosis and water in cells"
Cohesion: 0.44
Nodes (12): Cell wall, Flaccid, Large permanent vacuole, Osmosis, Partially permeable membrane, Percentage change, Plasmolysis, Turgid (+4 more)

### Community 3 - "Your subjects and study pages"
Cohesion: 0.41
Nodes (12): Exam dates, Mistake book, Past papers tracker, Chemistry, Design and Technology, Economics, English Language, English Literature (+4 more)

### Community 4 - "Cell types and nutrition"
Cohesion: 0.43
Nodes (8): Animal cell, Chloroplasts, Nucleus, Palisade mesophyll cell, Photosynthesis, Plant cell, Biology 6 Plant nutrition, Biology 7 Human nutrition

### Community 5 - "Specialised cells and organisation"
Cohesion: 0.43
Nodes (8): Cellulose, Neurone, Organ, Organ system, Specialised cell, Sperm and egg cells, Tissue, Biology 2.1 Cell structure

### Community 6 - "Size of specimens and magnification"
Cohesion: 0.67
Nodes (6): Biology 2 Flashcards, Magnification, Micrometre, Biology 2.2 Size of specimens, Biology 2 Exam questions, Biology 2 Organisation of the organism

### Community 7 - "Bacteria, DNA and biotechnology"
Cohesion: 0.70
Nodes (5): Bacterial cell, Circular DNA, Plasmids, Biology 1 Characteristics and classification of living organisms, Biology 21 Biotechnology and genetic engineering

### Community 8 - "Cells for transport and defence"
Cohesion: 0.50
Nodes (4): Ciliated cell, Red blood cell, Biology 10 Diseases and immunity, Biology 9 Transport in animals

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Biology` connect `Biology map, molecules and later topics` to `Diffusion, respiration and active transport`, `Osmosis and water in cells`, `Your subjects and study pages`, `Cell types and nutrition`, `Specialised cells and organisation`, `Size of specimens and magnification`, `Bacteria, DNA and biotechnology`, `Cells for transport and defence`?**
  _High betweenness centrality (0.316) - this node is a cross-community bridge._
- **Why does `Biology 2 Organisation of the organism` connect `Size of specimens and magnification` to `Diffusion, respiration and active transport`, `Biology map, molecules and later topics`, `Osmosis and water in cells`, `Cell types and nutrition`, `Specialised cells and organisation`, `Bacteria, DNA and biotechnology`, `Cells for transport and defence`?**
  _High betweenness centrality (0.306) - this node is a cross-community bridge._
- **Why does `Biology 3 Movement into and out of cells` connect `Diffusion, respiration and active transport` to `Biology map, molecules and later topics`, `Osmosis and water in cells`, `Cell types and nutrition`, `Size of specimens and magnification`, `Cells for transport and defence`?**
  _High betweenness centrality (0.164) - this node is a cross-community bridge._