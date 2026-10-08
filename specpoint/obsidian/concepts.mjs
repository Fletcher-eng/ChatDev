// Key terms for the Specpoint Obsidian vault.
// Each one becomes a note in "Biology/Key terms" and a node in the knowledge graph.
//   refs     : Specpoint subtopics where it is taught (links both ways)
//   later    : later Biology topics where the idea comes back
//   related  : other key terms it connects to
//   subjects : other subjects where the same idea appears, with a short reason
//   sup      : true if it is Supplement (Extended) content
export const CONCEPTS = [
  // ---------- 2.1 cell structures ----------
  {name:"Cell membrane", aliases:["membrane","cell membranes"], refs:["2.1","3.1","3.2","3.3"], later:[], sup:false,
   def:"A partially permeable layer around every cell. It controls which substances enter and leave the cell.",
   found:"Animal cells, plant cells and bacteria",
   related:["Partially permeable membrane","Diffusion","Osmosis","Active transport","Cell wall"]},
  {name:"Cytoplasm", aliases:[], refs:["2.1"], later:[5], sup:false,
   def:"The fluid inside the cell membrane where most of the cell's chemical reactions take place.",
   found:"Animal cells, plant cells and bacteria", related:["Ribosomes","Cell membrane"]},
  {name:"Nucleus", aliases:["nuclei"], refs:["2.1"], later:[17], sup:false,
   def:"Contains the genetic material, as chromosomes, which controls the activities of the cell.",
   found:"Animal and plant cells. Bacteria do not have one.", related:["Circular DNA","Animal cell","Plant cell"]},
  {name:"Ribosomes", aliases:["ribosome"], refs:["2.1"], later:[4,17], sup:false,
   def:"The site of protein synthesis.", found:"Animal cells, plant cells and bacteria", related:["Cytoplasm"]},
  {name:"Mitochondria", aliases:["mitochondrion"], refs:["2.1","3.3"], later:[12], sup:false,
   def:"The site of aerobic respiration, which releases energy for the cell.",
   found:"Animal and plant cells. Bacteria do not have them.", related:["Respiration","Active transport"]},
  {name:"Cell wall", aliases:["cell walls"], refs:["2.1","3.2"], later:[], sup:false,
   def:"A tough outer layer that strengthens the cell and keeps its shape. It is fully permeable, so it does not control what enters the cell. In plants it is made of cellulose.",
   found:"Plant cells and bacteria (not made of cellulose in bacteria)", related:["Cellulose","Turgor pressure","Cell membrane","Plant cell"]},
  {name:"Chloroplasts", aliases:["chloroplast"], refs:["2.1"], later:[6], sup:false,
   def:"Contain chlorophyll, which absorbs light energy for photosynthesis.", found:"Plant cells only", related:["Photosynthesis","Palisade mesophyll cell","Plant cell"]},
  {name:"Large permanent vacuole", aliases:["vacuole","sap vacuole"], refs:["2.1","3.2"], later:[], sup:false,
   def:"A large space filled with cell sap. When water enters it by osmosis the cell becomes turgid.",
   found:"Plant cells only", related:["Turgid","Osmosis","Plant cell"]},
  {name:"Circular DNA", aliases:["circular chromosome"], refs:["2.1"], later:[21], sup:false,
   def:"Bacteria have a single circular chromosome loose in the cytoplasm instead of a nucleus.",
   found:"Bacteria only", related:["Plasmids","Nucleus","Bacterial cell"]},
  {name:"Plasmids", aliases:["plasmid"], refs:["2.1"], later:[21], sup:false,
   def:"Small extra rings of DNA found in bacteria. They are used as vectors in genetic modification.",
   found:"Bacteria only", related:["Circular DNA","Bacterial cell"]},
  {name:"Cellulose", aliases:[], refs:["2.1"], later:[4], sup:false,
   def:"A carbohydrate (a polysaccharide made of glucose) that forms plant cell walls.", related:["Cell wall"]},

  // ---------- cell types ----------
  {name:"Animal cell", aliases:["animal cells"], refs:["2.1"], later:[], sup:false,
   def:"Has a nucleus, cytoplasm, cell membrane, mitochondria and ribosomes. It has no cell wall, no chloroplasts and no large permanent vacuole.",
   related:["Nucleus","Cytoplasm","Cell membrane","Mitochondria","Ribosomes","Plant cell"]},
  {name:"Plant cell", aliases:["plant cells"], refs:["2.1"], later:[6,8], sup:false,
   def:"Has everything an animal cell has, plus a cell wall made of cellulose, chloroplasts and a large permanent vacuole.",
   related:["Cell wall","Chloroplasts","Large permanent vacuole","Animal cell"]},
  {name:"Bacterial cell", aliases:["bacteria","bacterium"], refs:["2.1"], later:[1,10,21], sup:false,
   def:"A single celled organism with no nucleus. It has a cell wall, cell membrane, cytoplasm, ribosomes, circular DNA and plasmids.",
   related:["Circular DNA","Plasmids","Cell wall","Ribosomes"]},
  {name:"Specialised cell", aliases:["specialised","specialised cells"], refs:["2.1"], later:[], sup:false,
   def:"A cell whose structure is adapted to carry out one particular function.",
   related:["Ciliated cell","Root hair cell","Palisade mesophyll cell","Neurone","Red blood cell","Sperm and egg cells","Tissue"]},
  {name:"Ciliated cell", aliases:["ciliated cells"], refs:["2.1"], later:[10,11], sup:false,
   def:"Lines the trachea and bronchi. Its cilia beat to move mucus, with trapped dust and pathogens, away from the lungs.", related:["Specialised cell"]},
  {name:"Root hair cell", aliases:["root hair cells","root hairs"], refs:["2.1","3.2","3.3"], later:[8], sup:false,
   def:"Its long extension gives a large surface area for absorbing water by osmosis and mineral ions by active transport.",
   related:["Specialised cell","Osmosis","Active transport","Surface area"]},
  {name:"Palisade mesophyll cell", aliases:["palisade mesophyll cells","palisade cell"], refs:["2.1"], later:[6], sup:false,
   def:"Packed with chloroplasts to absorb as much light as possible for photosynthesis.", related:["Specialised cell","Chloroplasts","Photosynthesis"]},
  {name:"Neurone", aliases:["neurones","neuron"], refs:["2.1"], later:[14], sup:false,
   def:"Conducts electrical impulses. Its long fibres carry impulses over long distances.", related:["Specialised cell"]},
  {name:"Red blood cell", aliases:["red blood cells"], refs:["2.1","3.2"], later:[9], sup:false,
   def:"Transports oxygen using haemoglobin. It has no nucleus, which leaves more room for haemoglobin. In pure water it gains water by osmosis and bursts.",
   related:["Specialised cell","Osmosis"]},
  {name:"Sperm and egg cells", aliases:["sperm","egg cells","gametes"], refs:["2.1"], later:[16], sup:false,
   def:"The gametes, used for reproduction. Sperm have a flagellum to swim. Egg cells have a large food store in the cytoplasm.", related:["Specialised cell"]},

  // ---------- organisation ----------
  {name:"Tissue", aliases:["tissues"], refs:["2.1"], later:[], sup:false,
   def:"A group of cells with similar structures, working together to perform a shared function. Example: muscle tissue.", related:["Specialised cell","Organ"]},
  {name:"Organ", aliases:["organs"], refs:["2.1"], later:[], sup:false,
   def:"A structure made of a group of tissues, working together to perform specific functions. Example: the heart.", related:["Tissue","Organ system"]},
  {name:"Organ system", aliases:["organ systems"], refs:["2.1"], later:[9], sup:false,
   def:"A group of organs with related functions, working together to perform body functions. Example: the circulatory system.", related:["Organ"]},

  // ---------- 2.2 size of specimens ----------
  {name:"Magnification", aliases:["magnify"], refs:["2.2"], later:[], sup:false,
   def:"How many times bigger an image is than the real object. Magnification = image size ÷ actual size. It has no units and is written like ×400.",
   related:["Micrometre"], subjects:[["Mathematics","the same ratio and rearranging skills"]]},
  {name:"Micrometre", aliases:["micrometres","µm"], refs:["2.2"], later:[], sup:true,
   def:"A unit of length used for cells. 1 mm = 1000 µm. Change mm to µm by multiplying by 1000, and µm to mm by dividing by 1000.",
   related:["Magnification"], subjects:[["Physics","units and measurement"]]},

  // ---------- 3.1 diffusion ----------
  {name:"Diffusion", aliases:["diffuse","diffuses"], refs:["3.1","3.2"], later:[6,11], sup:false,
   def:"The net movement of particles from a region of higher concentration to a region of lower concentration, down a concentration gradient, as a result of their random movement.",
   related:["Concentration gradient","Kinetic energy","Surface area","Osmosis","Active transport","Cell membrane"],
   subjects:[["Chemistry","particles spreading out in states of matter"]]},
  {name:"Concentration gradient", aliases:["gradient"], refs:["3.1","3.3"], later:[], sup:false,
   def:"The difference in concentration between two regions. Diffusion goes down a gradient, from higher to lower concentration. Active transport goes against it.",
   related:["Diffusion","Active transport"]},
  {name:"Kinetic energy", aliases:[], refs:["3.1"], later:[], sup:false,
   def:"The energy of movement. The random movement of particles that causes diffusion comes from their kinetic energy, so diffusion needs no energy from respiration.",
   related:["Diffusion"], subjects:[["Physics","energy stores and particle motion"],["Chemistry","particle theory and temperature"]]},
  {name:"Surface area", aliases:[], refs:["3.1"], later:[11], sup:false,
   def:"A larger surface area lets more particles cross at once, so it increases the rate of diffusion.",
   related:["Diffusion","Root hair cell"], subjects:[["Mathematics","calculating area and surface area to volume ratio"]]},

  // ---------- 3.2 osmosis ----------
  {name:"Osmosis", aliases:[], refs:["3.2"], later:[8], sup:false,
   def:"The diffusion of water through a partially permeable membrane. Supplement definition: the net movement of water molecules from a region of higher water potential (a dilute solution) to a region of lower water potential (a concentrated solution), through a partially permeable membrane.",
   related:["Water potential","Partially permeable membrane","Diffusion","Turgid","Flaccid","Plasmolysis","Red blood cell","Root hair cell"]},
  {name:"Water potential", aliases:["higher water potential","lower water potential"], refs:["3.2"], later:[8], sup:true,
   def:"Describes how freely water molecules can move. A dilute solution has a higher water potential than a concentrated one. Water moves by osmosis from higher to lower water potential.",
   related:["Osmosis"]},
  {name:"Partially permeable membrane", aliases:["partially permeable"], refs:["3.2"], later:[], sup:false,
   def:"A membrane that lets some molecules through, such as water, but not others, such as large solute molecules. The cell membrane is one. Dialysis tubing is used to model it in experiments.",
   related:["Cell membrane","Osmosis"]},
  {name:"Turgid", aliases:[], refs:["3.2"], later:[8], sup:true,
   def:"Describes a plant cell that is full of water, with its contents pressing outwards on the cell wall.",
   related:["Turgor pressure","Flaccid","Large permanent vacuole","Osmosis"]},
  {name:"Turgor pressure", aliases:[], refs:["3.2"], later:[8], sup:true,
   def:"The pressure of water inside a plant cell pushing outwards on the cell wall. It supports the plant.",
   related:["Turgid","Cell wall","Flaccid"]},
  {name:"Flaccid", aliases:[], refs:["3.2"], later:[8], sup:true,
   def:"Describes a plant cell that has lost water and no longer presses on its cell wall. When cells go flaccid the plant wilts.",
   related:["Turgid","Plasmolysis","Turgor pressure"]},
  {name:"Plasmolysis", aliases:[], refs:["3.2"], later:[], sup:true,
   def:"When a plant cell loses so much water by osmosis that the cell membrane pulls away from the cell wall.",
   related:["Flaccid","Osmosis","Cell wall"]},
  {name:"Percentage change", aliases:["percentage change in mass"], refs:["3.2"], later:[], sup:false,
   def:"Percentage change = (change in mass ÷ starting mass) × 100. Used in the potato cylinder osmosis practical.",
   related:["Osmosis"], subjects:[["Mathematics","percentage change calculations"],["Chemistry","percentage yield and composition"]]},

  // ---------- 3.3 active transport ----------
  {name:"Active transport", aliases:[], refs:["3.3"], later:[8], sup:false,
   def:"The movement of particles through a cell membrane from a region of lower concentration to a region of higher concentration, against a concentration gradient, using energy from respiration.",
   related:["Concentration gradient","Protein carriers","Mitochondria","Respiration","Root hair cell","Diffusion"]},
  {name:"Protein carriers", aliases:["protein carrier","carrier proteins"], refs:["3.3"], later:[], sup:true,
   def:"Proteins in the cell membrane that move molecules or ions across it during active transport.",
   related:["Active transport","Cell membrane"]},

  // ---------- big processes that come back later ----------
  {name:"Respiration", aliases:["aerobic respiration"], refs:["2.1","3.3"], later:[12], sup:false,
   def:"The chemical reactions in cells that break down nutrient molecules and release energy. Aerobic respiration happens in mitochondria.",
   related:["Mitochondria","Active transport"]},
  {name:"Photosynthesis", aliases:[], refs:["2.1"], later:[6], sup:false,
   def:"The process by which plants make carbohydrates from raw materials using energy from light. It happens in chloroplasts.",
   related:["Chloroplasts","Palisade mesophyll cell"]}
];

// Your subjects. Codes: Cambridge IGCSE, then Pearson Edexcel International GCSE.
export const SUBJECTS = [
  {name:"Biology", cie:"0610", edx:"4BI1", color:"#0ACF83"},
  {name:"Chemistry", cie:"0620", edx:"4CH1", color:"#FF7262"},
  {name:"Physics", cie:"0625", edx:"4PH1", color:"#1ABCFE"},
  {name:"Mathematics", cie:"0580", edx:"4MA1", color:"#F24E1E"},
  {name:"English Language", cie:"0500", edx:"4EA1", color:"#FFC700"},
  {name:"English Literature", cie:"0475", edx:"4ET1", color:"#FF9EC4"},
  {name:"Design and Technology", cie:"0445", edx:null, color:"#C9C5BA"},
  {name:"Economics", cie:"0455", edx:"4EC1", color:"#3DD6C4"},
  {name:"Global Perspectives", cie:"0457", edx:null, color:"#8FD3FF"},
  {name:"Spanish", cie:"0530", edx:"4SP1", color:"#FFB443"}
];

// Groups of three or more ideas that belong together (become Graphify hyperedges).
export const GROUPS = [
  {id:"plant_only_structures", label:"Structures only plant cells have", members:["Cell wall","Chloroplasts","Large permanent vacuole"]},
  {id:"movement_in_and_out_of_cells", label:"Ways substances move in and out of cells", members:["Diffusion","Osmosis","Active transport"]},
  {id:"levels_of_organisation", label:"Levels of organisation", members:["Specialised cell","Tissue","Organ","Organ system"]},
  {id:"plant_cell_water_states", label:"What happens to plant cells in different solutions", members:["Turgid","Flaccid","Plasmolysis","Turgor pressure"]}
];
