// Builds the Specpoint Obsidian vault from the website's content.
//   node specpoint/obsidian/build-vault.mjs [vault folder]
// Safe to run again: anything you write under "## My notes" in a note is kept.
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { CONCEPTS, SUBJECTS, GROUPS, GP_CONCEPTS, GP_GROUPS } from "./concepts.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const VAULT = path.resolve(process.argv[2] || path.join(HERE, "Specpoint Vault"));
const SITE = path.join(HERE, "..", "index.html");
const MY_NOTES = "## My notes";

/* ---------- load Specpoint content straight from the website ---------- */
function loadSite(){
  const html = fs.readFileSync(SITE, "utf8");
  const js = html.slice(html.indexOf("<script>") + 8, html.lastIndexOf("</script>"));
  const content = js.slice(js.indexOf("/* ================= CONTENT"), js.indexOf("/* ================= STORAGE"));
  return vm.runInNewContext(content + ";({BIO_TOPICS, TOPICS, GP_LIST, GP_TOPICS})", {});
}
const { BIO_TOPICS, TOPICS, GP_LIST, GP_TOPICS } = loadSite();

/* ---------- subjects the website has notes for ---------- */
const SITE_SUBJECTS = [
  {name:"Biology", short:"Biology", folder:"Biology", tag:"biology", code:"0610", unit:"Topic", list:BIO_TOPICS, topics:TOPICS, concepts:CONCEPTS,
   syllabus:"checked against the Cambridge 0610 syllabus", keyIndexNote:"Terms marked **S** are Supplement (Extended) content."},
  {name:"Global Perspectives", short:"GP", folder:"Global Perspectives", tag:"gp", code:"0457", unit:"Unit", list:GP_LIST, topics:GP_TOPICS, concepts:GP_CONCEPTS,
   syllabus:"based on the Cambridge 0457 skills", keyIndexNote:"Learn these words exactly. Examiners reward the right terms."}
];
const SUBJ = Object.fromEntries(SITE_SUBJECTS.map(S=>[S.name, S]));

/* ---------- names ---------- */
const topicTitle = (S, n) => `${S.short} ${n} ${S.list[n-1]}`;
const subTitle = (S, s) => `${S.short} ${s.ref} ${s.title}`;
const cardsTitle = (S, n) => `${S.short} ${n} Flashcards`;
const practiceTitle = (S, n) => `${S.short} ${n} Exam questions`;
const memoriseTitle = (S, n) => `${S.short} ${n} Memorise`;
const indexTitle = S => `${S.name} key terms`;
const L = t => `[[${t}]]`;
const ALL_CONCEPTS = SITE_SUBJECTS.flatMap(S=>S.concepts.map(c=>({...c, subject:S.name})));
const byName = new Map(), byAlias = new Map();
for(const c of ALL_CONCEPTS){ byName.set(c.name.toLowerCase(), c); for(const a of [c.name, ...c.aliases]) byAlias.set(a.toLowerCase(), c); }
const findConcept = text => byAlias.get(text.trim().toLowerCase().replace(/[.,]$/,""));
const topicOfRef = ref => parseInt(ref);

/* ---------- files and the link graph ---------- */
const NOTES = new Map(); // title -> {rel, type, links:Set}
const linksIn = body => new Set([...body.replace(/`[^`\n]*`/g,"").matchAll(/\[\[([^\]|\\#]+)/g)].map(m=>m[1].trim()));
function note(rel, title, type, body){
  NOTES.set(title, {rel, type, links:linksIn(body)});
  const file = path.join(VAULT, rel);
  fs.mkdirSync(path.dirname(file), {recursive:true});
  let out = body.endsWith("\n") ? body : body + "\n";
  if(fs.existsSync(file) && out.includes(MY_NOTES)){
    const old = fs.readFileSync(file, "utf8"), i = old.indexOf(MY_NOTES);
    if(i >= 0) out = out.slice(0, out.indexOf(MY_NOTES)) + old.slice(i);
  }
  fs.writeFileSync(file, out);
}
const raw = (rel, text) => {
  const f = path.join(VAULT, rel); fs.mkdirSync(path.dirname(f), {recursive:true});
  if(!fs.existsSync(f)) fs.writeFileSync(f, text);
  if(!rel.startsWith("Templates/")) NOTES.set(path.basename(rel, ".md"), {rel, type:"study", links:linksIn(fs.readFileSync(f, "utf8"))});
};
const fm = obj => "---\n" + Object.entries(obj).map(([k,v])=>`${k}: ${Array.isArray(v) ? "["+v.map(x=>JSON.stringify(x)).join(", ")+"]" : typeof v==="string" ? JSON.stringify(v) : v}`).join("\n") + "\n---\n";
const myNotes = hint => `\n${MY_NOTES}\n\n${hint || "Write your own notes here. Rebuilding the vault never touches this section."}\n`;

/* ---------- tiny HTML to Markdown converter for Specpoint notes ---------- */
function parse(html){
  const root = {tag:"root", attrs:{}, children:[]}, stack = [root];
  const re = /<(\/?)([a-zA-Z0-9]+)([^>]*?)(\/?)>|([^<]+)/g; let m;
  while((m = re.exec(html))){
    if(m[5] !== undefined){ stack[stack.length-1].children.push(m[5]); continue; }
    const [, close, tag, attrStr, selfClose] = m;
    if(close){ while(stack.length > 1 && stack.pop().tag !== tag.toLowerCase()); continue; }
    const attrs = {}; for(const a of attrStr.matchAll(/([a-zA-Z-]+)="([^"]*)"/g)) attrs[a[1]] = a[2];
    const node = {tag:tag.toLowerCase(), attrs, children:[]};
    stack[stack.length-1].children.push(node);
    if(!selfClose && !["br","img","input","hr"].includes(node.tag)) stack.push(node);
  }
  return root;
}
const cls = n => (n.attrs && n.attrs.class || "").split(/\s+/);
const decode = s => s.replace(/&amp;/g,"&").replace(/&lt;/g,"<").replace(/&gt;/g,">").replace(/&quot;/g,'"').replace(/&#39;/g,"'");
const textOf = n => typeof n === "string" ? decode(n) : n.children.map(textOf).join("");
function linkFor(text, used){
  const c = findConcept(text); if(!c) return null;
  used.add(c.name);
  return c.name.toLowerCase() === text.trim().toLowerCase() ? `[[${c.name}]]` : `[[${c.name}|${text.trim()}]]`;
}
function inline(n, used){
  if(typeof n === "string") return decode(n).replace(/\s+/g," ");
  const kids = () => n.children.map(c=>inline(c, used)).join("");
  const k = cls(n);
  if(k.includes("kt")){ const t = textOf(n).trim(); return linkFor(t, used) || `==${t}==`; }
  if(k.includes("sup")) return "**(Supplement)**";
  if(n.tag === "strong" || n.tag === "b"){ const t = kids().trim(); return t ? `**${t}**` : ""; }
  if(n.tag === "em") return `*${kids().trim()}*`;
  return kids();
}
const clean = s => s.replace(/[ \t]+/g," ").replace(/ +([.,:;)])/g,"$1").trim();
function block(n, used){
  if(typeof n === "string") return n.trim() ? clean(inline(n, used)) + "\n\n" : "";
  const k = cls(n), kids = () => n.children.map(c=>block(c, used)).join("");
  if(n.attrs["data-widget"]){
    const what = {cellmap:"Cell explorer: tap each part of an animal, plant and bacterial cell", magcalc:"Magnification calculator", osmosis:"Osmosis lab: drag a slider and watch plant and red blood cells change"}[n.attrs["data-widget"]] || "Interactive diagram";
    return `> [!example] Interactive on Specpoint\n> ${what}. Open this topic on the Specpoint website to use it.\n\n`;
  }
  switch(n.tag){
    case "p": return clean(n.children.map(c=>inline(c, used)).join("")) + "\n\n";
    case "h3": return `### ${clean(n.children.map(c=>inline(c, used)).join(""))}\n\n`;
    case "ul": return n.children.filter(c=>c.tag==="li").map(li=>`- ${clean(inline(li, used))}`).join("\n") + "\n\n";
    case "ol": return n.children.filter(c=>c.tag==="li").map((li,i)=>`${i+1}. ${clean(inline(li, used))}`).join("\n") + "\n\n";
  }
  if(k.includes("tbl")){
    const rows = []; const walk = x => { if(typeof x === "string") return; if(x.tag === "tr") rows.push(x.children.filter(c=>c.tag==="td"||c.tag==="th")); else x.children.forEach(walk); };
    walk(n);
    const cell = c => { const t = clean(textOf(c)); const lk = linkFor(t, used); return (lk || clean(inline(c, used))).replace(/\|/g,"\\|"); };
    const [head, ...body] = rows;
    return [`| ${head.map(cell).join(" | ")} |`, `| ${head.map(()=>"---").join(" | ")} |`, ...body.map(r=>`| ${r.map(cell).join(" | ")} |`)].join("\n") + "\n\n";
  }
  if(k.includes("box")){
    const [first, ...rest] = n.children.filter(c=>typeof c !== "string" || c.trim());
    const title = textOf(first).trim(), body = clean(rest.map(c=>inline(c, used)).join(""));
    return `> [!${k.includes("trap") ? "warning" : "tip"}] ${title}\n> ${body}\n\n`;
  }
  if(k.includes("formula")){
    const lines = n.children.filter(c=>typeof c !== "string").map(c=>clean(textOf(c)));
    return `> [!info] Formula\n${lines.map(l=>`> ${l}`).join("\n")}\n\n`;
  }
  if(k.includes("work")){
    const parts = n.children.filter(c=>typeof c !== "string");
    const title = textOf(parts[0]).trim();
    const inner = parts.slice(1).map(c=>block(c, used)).join("").trim().split("\n").map(l=>`> ${l}`).join("\n");
    return `> [!example] ${title}\n${inner}\n\n`;
  }
  if(k.includes("flow")){
    const steps = n.children.filter(c=>typeof c !== "string" && c.tag==="span").map(c=>{ const t = textOf(c).trim(); return linkFor(t, used) || t; });
    return `**${steps.join(" → ")}**\n\n`;
  }
  return kids();
}
const toMarkdown = (html, used) => block(parse(html.replace(/<p>Tap any part[^<]*<\/p>/, "")), used).replace(/\n{3,}/g,"\n\n").trim() + "\n";

/* ---------- deterministic option order for multiple choice ---------- */
const order = (q, i) => { const all = [q.a, ...q.w]; const r = i % all.length; return all.slice(r).concat(all.slice(0, r)); };
const LETTERS = "ABCD";
const mcBlock = (q, i, heading) => {
  const opts = order(q, i);
  return `### ${heading}\n${q.q}\n\n${opts.map((o,j)=>`${LETTERS[j]}. ${o}`).join("\n")}\n\n> [!success]- Answer\n> **${LETTERS[opts.indexOf(q.a)]}. ${q.a}**${q.t ? `\n> ${q.t}` : ""}\n`;
};

/* ================= BUILD ================= */
fs.mkdirSync(VAULT, {recursive:true});

function buildSubject(S){
  const written = Object.keys(S.topics).map(Number);
  const F = S.folder, tags = t => [S.tag, t];
  const conceptsInTopic = n => S.concepts.filter(c=>c.refs.some(r=>topicOfRef(r)===n));
  const conceptsLeadingTo = n => S.concepts.filter(c=>c.later.includes(n));
  const fmBase = {subject:S.name, syllabus:`Cambridge IGCSE ${S.code}`};

  /* subtopic notes */
  for(const n of written){
    for(const s of S.topics[n].subs){
      const used = new Set();
      const md = toMarkdown(s.html, used);
      const sup = /\(Supplement\)/.test(md);
      S.concepts.filter(c=>c.refs.includes(s.ref)).forEach(c=>used.add(c.name));
      let body = fm({type:"notes", ...fmBase, topic:n, subtopic:s.ref, supplement:sup, source:"Specpoint", tags:tags("notes")});
      body += `# ${s.ref} ${s.title}\n\nPart of ${L(topicTitle(S,n))} in ${L(S.name)}. Written by the Specpoint team and ${S.syllabus}.\n\n`;
      body += md + "\n";
      if(s.check) body += `> [!question] Quick check\n> ${s.check.q}\n>\n${order(s.check, 1).map((o,j)=>`> ${LETTERS[j]}. ${o}`).join("\n")}\n>\n> > [!success]- Answer\n> > **${s.check.a}**. ${s.check.t}\n\n`;
      body += `## Key terms in this note\n\n${[...used].sort().map(t=>`- ${L(t)}`).join("\n")}\n\n`;
      body += `## Practise\n\n${S.topics[n].memorise ? `- ${L(memoriseTitle(S,n))}\n` : ""}- ${L(cardsTitle(S,n))}\n- ${L(practiceTitle(S,n))}\n`;
      body += myNotes();
      note(`${F}/Notes/${subTitle(S,s)}.md`, subTitle(S,s), "notes", body);
    }
  }

  /* memorise sheets: acronyms and lists, with self test and flashcards */
  for(const n of written){
    const T = S.topics[n]; if(!T.memorise) continue;
    let body = fm({type:"memorise", ...fmBase, topic:n, tags:tags("memorise")});
    body += `# ${S.unit} ${n} memorise\n\nFor ${L(topicTitle(S,n))}. Learn each list, then cover the words and test yourself. Every line with two colons is also a flashcard for the Spaced Repetition plugin.\n\n#flashcards/${S.tag}/memorise\n\n`;
    for(const set of T.memorise){
      body += `## ${set.name}\n\n*${set.what}*\n\n**${set.items.map(x=>x[0]).join(" ")}**\n\n| Letter | Stands for | Meaning |\n| --- | --- | --- |\n${set.items.map(x=>`| **${x[0]}** | ${x[1]} | ${x[2]} |`).join("\n")}\n\n`;
      body += `> [!question]- Test yourself: what does each letter stand for?\n${set.items.map(x=>`> **${x[0]}**: ${x[1]}`).join("\n")}\n\n`;
      body += `What does ${set.name} stand for?::${set.items.map(x=>x[1]).join(", ")}\n\n`;
      set.items.forEach((x,i)=>{ const same = set.items.filter(y=>y[0]===x[0]).length, nth = set.items.slice(0,i+1).filter(y=>y[0]===x[0]).length;
        body += `${set.name}: the ${same>1?["first","second","third","fourth"][nth-1]+" ":""}${x[0]}::${x[1]} (${x[2]})\n\n`; });
      if(set.order) body += `### Example paragraph in ${set.name} order\n\n**Question:** ${set.order.q}\n\n${set.order.parts.map((p,i)=>`${i+1}. **${set.items[i][1]}:** ${p}`).join("\n")}\n\n`;
    }
    body += `Back to ${L(topicTitle(S,n))}\n`;
    note(`${F}/Memorise/${memoriseTitle(S,n)}.md`, memoriseTitle(S,n), "memorise", body);
  }

  /* flashcards (Spaced Repetition plugin format) */
  for(const n of written){
    const T = S.topics[n];
    let body = fm({type:"flashcards", ...fmBase, topic:n, tags:tags("flashcards")});
    body += `# ${S.unit} ${n} flashcards\n\n#flashcards/${S.tag}/${S.unit.toLowerCase()}${n}\n\nEach line is one card: question, then two colons, then the answer. Install the **Spaced Repetition** community plugin to review them, or just cover the answers.\n\n`;
    body += T.cards.map(([f,b])=>`${f}::${b}`).join("\n\n") + "\n\n";
    body += `Back to ${L(topicTitle(S,n))}\n`;
    note(`${F}/Flashcards/${cardsTitle(S,n)}.md`, cardsTitle(S,n), "flashcards", body);
  }

  /* practice questions */
  for(const n of written){
    const T = S.topics[n];
    let body = fm({type:"practice", ...fmBase, topic:n, tags:tags("practice")});
    body += `# ${S.unit} ${n} exam questions\n\nFor ${L(topicTitle(S,n))}. Write your answer under each question, then open the mark scheme and tick the points you made. These are original Specpoint questions in the Cambridge style, not official past paper questions.\n\n## Written questions\n\n`;
    T.exam.forEach((q,i)=>{
      body += `### Question ${i+1} · ${q.ref}${q.sup?" · Supplement":""} · [${q.marks} mark${q.marks>1?"s":""}]\n${q.q}\n\n**My answer:**\n\n\n> [!check]- Mark scheme\n${q.ms.map(m=>`> - [ ] ${m}`).join("\n")}${q.note?`\n>\n> *${q.note}*`:""}\n\n`;
    });
    const mcs = T.boss.qs.filter(q=>q.num===undefined), nums = T.boss.qs.filter(q=>q.num!==undefined);
    body += `## Multiple choice\n\n` + mcs.map((q,i)=>mcBlock(q, i, `MC ${i+1}`)).join("\n") + "\n";
    if(nums.length) body += `## Quick calculations\n\n` + nums.map((q,i)=>`### Calculation ${i+1}\n${q.q}\n\n> [!success]- Answer\n> **${q.num} ${q.unit}**. ${q.t}\n`).join("\n") + "\n";
    body += myNotes("Note which questions caught you out, then add them to [[Mistake book]].");
    note(`${F}/Practice/${practiceTitle(S,n)}.md`, practiceTitle(S,n), "practice", body);
  }

  /* topic hubs */
  for(let n = 1; n <= S.list.length; n++){
    const T = S.topics[n], here = conceptsInTopic(n), lead = conceptsLeadingTo(n).filter(c=>!here.includes(c));
    let body = fm({type:"topic", ...fmBase, topic:n, status: T ? "written" : "not written yet", tags:tags("topic")});
    body += `# ${S.unit} ${n}: ${S.list[n-1]}\n\nPart of ${L(S.name)} · Cambridge IGCSE ${S.code}${n>1?` · Previous: ${L(topicTitle(S,n-1))}`:""}${n<S.list.length?` · Next: ${L(topicTitle(S,n+1))}`:""}\n\n`;
    if(T){
      body += `## Notes\n\n${T.subs.map(s=>`- ${L(subTitle(S,s))}`).join("\n")}\n\n## Practise\n\n${T.memorise?`- ${L(memoriseTitle(S,n))} (${T.memorise.map(m=>m.name).join(", ")})\n`:""}- ${L(cardsTitle(S,n))} (${T.cards.length} cards)\n- ${L(practiceTitle(S,n))} (${T.exam.length} written questions, ${T.boss.qs.length} quick questions)\n\n`;
      body += `## Key terms\n\n${here.map(c=>L(c.name)).join(" · ")}\n\n`;
      const later = new Map(); here.forEach(c=>c.later.forEach(t=>{ if(t!==n){ if(!later.has(t)) later.set(t, []); later.get(t).push(c.name); } }));
      if(later.size) body += `## Where these ideas come back\n\n${[...later.entries()].sort((a,b)=>a[0]-b[0]).map(([t,cs])=>`- ${L(topicTitle(S,t))} through ${cs.map(L).join(", ")}`).join("\n")}\n\n`;
    } else {
      body += `> [!note] Not written yet\n> Specpoint notes for this topic are on the way. Start your own notes below using the Topic note template.\n\n`;
    }
    if(lead.length) body += `## Ideas you already know that lead here\n\n${lead.map(c=>`- ${L(c.name)}`).join("\n")}\n\n`;
    body += myNotes();
    note(`${F}/Topics/${topicTitle(S,n)}.md`, topicTitle(S,n), "topic", body);
  }

  /* key term notes */
  for(const c of S.concepts){
    let body = fm({type:"key term", subject:S.name, supplement:c.sup, aliases:c.aliases, tags:[S.tag,"keyterm"].concat(c.sup?["supplement"]:[])});
    body += `# ${c.name}\n\n> [!abstract] Definition${c.sup?" (Supplement)":""}\n> ${c.def}\n\n`;
    if(c.found) body += `**Found in:** ${c.found}\n\n`;
    const subs = written.flatMap(n=>S.topics[n].subs).filter(s=>c.refs.includes(s.ref));
    body += `## Where it is taught\n\n${subs.map(s=>`- ${L(subTitle(S,s))}`).join("\n")}\n\n`;
    if(c.later.length) body += `## Comes back in\n\n${c.later.map(t=>`- ${L(topicTitle(S,t))}`).join("\n")}\n\n`;
    const rel = c.related.filter(r=>byName.has(r.toLowerCase()));
    const back = S.concepts.filter(o=>o!==c && o.related.includes(c.name) && !rel.includes(o.name)).map(o=>o.name);
    if(rel.length || back.length) body += `## Linked ideas\n\n${[...rel, ...back].map(r=>`- ${L(r)}`).join("\n")}\n\n`;
    if(c.subjects && c.subjects.length) body += `## In other subjects\n\n${c.subjects.map(([s,why])=>`- ${L(s)}: ${why}`).join("\n")}\n\n`;
    body += myNotes("Add your own examples, memory tricks or diagrams here.");
    note(`${F}/Key terms/${c.name}.md`, c.name, "key term", body);
  }

  /* key term index */
  {
    let body = fm({type:"index", subject:S.name, tags:tags("index")});
    body += `# ${indexTitle(S)}\n\nEvery key term in the Specpoint ${S.name} notes. ${S.keyIndexNote}\n\n`;
    const letters = [...new Set(S.concepts.map(c=>c.name[0].toUpperCase()))].sort();
    for(const l of letters) body += `### ${l}\n${S.concepts.filter(c=>c.name[0].toUpperCase()===l).sort((a,b)=>a.name.localeCompare(b.name)).map(c=>`- ${L(c.name)}${c.sup?" **S**":""}: ${c.def.split(". ")[0].replace(/\.$/,"")}.`).join("\n")}\n\n`;
    body += `Back to ${L(S.name)}\n`;
    note(`${F}/${indexTitle(S)}.md`, indexTitle(S), "index", body);
  }
}
SITE_SUBJECTS.forEach(buildSubject);

/* subject hubs */
for(const s of SUBJECTS){
  const S = SUBJ[s.name];
  const shared = ALL_CONCEPTS.filter(c=>c.subject!==s.name && (c.subjects||[]).some(([n])=>n===s.name));
  let body = fm({type:"subject", cambridge:s.cie, edexcel:s.edx || "not offered", board:"", tier:"", tags:["subject"]});
  body += `# ${s.name}\n\nCambridge IGCSE ${s.cie}${s.edx?` · Pearson Edexcel International GCSE ${s.edx}`:" · Cambridge only"}\n\n> [!tip] Fill in your board\n> Set **board** and **tier** in the properties at the top of this note, so you always know which syllabus to follow.\n\n`;
  if(S){
    const written = Object.keys(S.topics).map(Number);
    body += `## ${S.unit}s\n\n${S.list.map((t,i)=>`${i+1}. ${L(topicTitle(S,i+1))}${S.topics[i+1]?" ✓":""}`).join("\n")}\n\n✓ means Specpoint notes are written.\n\n`;
    body += `## Study tools\n\n- ${L(indexTitle(S))}\n${written.map(n=>`${S.topics[n].memorise?`- ${L(memoriseTitle(S,n))}\n`:""}- ${L(cardsTitle(S,n))}\n- ${L(practiceTitle(S,n))}`).join("\n")}\n\n`;
  } else {
    body += `## Topics\n\nSpecpoint notes for ${s.name} are on the way. Make a note for each topic as you go with the Topic note template, and link it here like \`[[${s.name} 1 Topic name]]\`.\n\n`;
  }
  if(shared.length) body += `## Ideas shared with other subjects\n\n${shared.map(c=>`- ${L(c.name)} (${c.subject}): ${c.subjects.find(([n])=>n===s.name)[1]}`).join("\n")}\n\n`;
  body += `## Past papers and mistakes\n\n- ${L("Past papers tracker")}\n- ${L("Mistake book")}\n`;
  body += myNotes();
  note(`Subjects/${s.name}.md`, s.name, "subject", body);
}

/* my study pages: created once, then they are yours */
const subjRows = SUBJECTS.map(s=>`| ${L(s.name)} |  |  |  |  |`).join("\n");
raw("My study/Mistake book.md", `${fm({type:"study", tags:["study"]})}# Mistake book\n\nEvery question you get wrong goes here. Redo it a few days later. When you get it right, tick it off.\n\nMistakes exported from the Specpoint website can be dropped into this folder too.\n\n| Date | Subject | Question | What went wrong | Fixed |\n| --- | --- | --- | --- | --- |\n|  |  |  |  | [ ] |\n`);
raw("My study/Past papers tracker.md", `${fm({type:"study", tags:["study"]})}# Past papers tracker\n\nLog every past paper you do. Official papers come from Cambridge and Pearson, or from your teacher.\n\n| Subject | Paper | Session | Score | Notes |\n| --- | --- | --- | --- | --- |\n${subjRows}\n`);
raw("My study/Revision timetable.md", `${fm({type:"study", tags:["study"]})}# Revision timetable\n\nPlan one week at a time. Short sessions every day beat one long one.\n\n| | Mon | Tue | Wed | Thu | Fri | Sat | Sun |\n| --- | --- | --- | --- | --- | --- | --- | --- |\n| Session 1 |  |  |  |  |  |  |  |\n| Session 2 |  |  |  |  |  |  |  |\n| Flashcards |  |  |  |  |  |  |  |\n`);
raw("My study/Exam dates.md", `${fm({type:"study", tags:["study"]})}# Exam dates\n\n| Subject | Paper | Date | Time |\n| --- | --- | --- | --- |\n${SUBJECTS.map(s=>`| ${L(s.name)} |  |  |  |`).join("\n")}\n`);
raw("My flashcards/About my flashcards.md", `# My flashcards\n\nPut your own flashcard decks in this folder. Start one from the **Flashcard deck** template.\n\nWrite each card on its own line as \`question::answer\`, and keep the \`#flashcards\` tag at the top so the Spaced Repetition plugin finds it. Decks exported from the Specpoint website use the same format, so you can drop them straight in.\n\nBack to [[Home]]\n`);
raw("Templates/Topic note.md", `---\ntype: topic\nsubject: \nboard: \ntags: [topic]\n---\n# {{title}}\n\nPart of [[Subject name]]\n\n## Key ideas\n\n## Key terms\n\n## Examiner tips\n\n${MY_NOTES}\n\n`);
raw("Templates/Key term.md", `---\ntype: key term\nsubject: \ntags: [keyterm]\n---\n# {{title}}\n\n> [!abstract] Definition\n> \n\n## Where it is taught\n\n## Linked ideas\n\n${MY_NOTES}\n\n`);
raw("Templates/Flashcard deck.md", `---\ntype: flashcards\nsubject: \n---\n# {{title}}\n\n#flashcards\n\nQuestion::Answer\n`);
raw("Templates/Mistake.md", `---\ntype: mistake\ndate: {{date}}\nsubject: \nfixed: false\n---\n# {{title}}\n\n**Question:**\n\n**What I wrote:**\n\n**The right answer:**\n\n**Why I got it wrong:**\n`);

/* home and Claude guide (always refreshed) */
note("Home.md", "Home", "home", `${fm({type:"home", tags:["home"]})}# Specpoint study vault

Everything you need for your IGCSEs, in one place, on your own computer. It works offline.

## Subjects

${SUBJECTS.map(s=>`- ${L(s.name)}`).join("\n")}

## Study tools

${SITE_SUBJECTS.map(S=>`- ${L(indexTitle(S))}`).join("\n")}
- ${L("GP 1 Memorise")} (SEEEL and PEEL)
- ${L("Mistake book")}
- ${L("Past papers tracker")}
- ${L("Revision timetable")}
- ${L("Exam dates")}

## How to revise one topic

1. Read the notes and fill in **My notes** in your own words.
2. Test yourself with the flashcards.
3. Do the exam questions, then mark them with the mark scheme.
4. Put anything you got wrong in the ${L("Mistake book")}.

## Use the graph

Open the graph with **Ctrl+G** (Cmd+G on a Mac). Each dot is a note and each line is a link. Big dots are ideas that connect to lots of topics, which makes them the most important to understand. Colours: green for topics and units, blue for notes, yellow for key terms, light blue for flashcards, practice and memorise sheets, orange for subjects, pink for your study pages.

There is also a knowledge graph built with Graphify in the \`graphify-out\` folder. Open \`graph.html\` in your browser, or read \`GRAPH_REPORT.md\` to see which ideas link the most topics.

## Plugins worth adding

- **Spaced Repetition**: turns every \`question::answer\` line into a flashcard.
- **Dataview** (optional): makes live lists from note properties.

Turn on the **Templates** core plugin too. The template folder is already set to \`Templates\`.
`);

note("CLAUDE.md", "CLAUDE", "guide", `# Guide for Claude

This is the Specpoint study vault of an IGCSE student (Year 10, Cambridge and Edexcel boards depending on the subject). Help them learn. Keep everything at IGCSE level and in plain, encouraging language. Do not use dashes as punctuation in anything you write here.

## Layout

- \`Home.md\`: start page.
- \`Subjects/\`: one hub note per subject with syllabus codes. The student fills in \`board\` and \`tier\`.
- One folder per subject with Specpoint notes: \`Biology/\` (0610) and \`Global Perspectives/\` (0457). Inside each:
  - \`Topics/\`: one note per topic or unit. \`status\` says whether Specpoint notes exist.
  - \`Notes/\`: full notes per section, like \`Biology 3.2 Osmosis\` or \`GP 1.1 SEEEL paragraphs\`.
  - \`Key terms/\`: one note per key idea with its definition and links. These are the hubs of the graph.
  - \`Flashcards/\`: cards as \`question::answer\` lines (Spaced Repetition plugin format).
  - \`Practice/\`: exam style questions with mark schemes inside folded \`[!check]\` callouts.
  - \`Memorise/\` (GP): acronyms like SEEEL (Statement, Evidence, Explain, Evaluate, Link), PEEL, CRAAP and PESTLE, with self tests.
- \`My study/\` and \`My flashcards/\`: the student's own pages.
- \`graphify-out/\`: Graphify knowledge graph (\`graph.json\`, \`GRAPH_REPORT.md\`, \`graph.html\`).

## Rules

- Never edit text below a \`## My notes\` heading unless the student asks. That is their writing.
- Notes outside \`My notes\` are generated by \`specpoint/obsidian/build-vault.mjs\` from the Specpoint website. Fix content there, not here, or the fix is lost on the next rebuild.
- Link ideas with \`[[wikilinks]]\` to existing key term notes so the graph stays connected.
- Stick to the syllabus. If you are unsure whether something is on the syllabus, say so.

## Good ways to help

- Quiz the student from any \`Flashcards\`, \`Practice\` or \`Memorise\` folder. Ask one question at a time and wait for their answer before showing the mark scheme.
- For GP acronyms, give the letter and ask what it stands for, in order, then mix the order up once they know it.
- When they write a GP paragraph, check it has every SEEEL part and say which part is missing or weak.
- Mark their written answers strictly against the mark scheme points.
- Log what they get wrong in \`My study/Mistake book.md\`.
- Use the graph to explain links between topics: \`graphify explain "Osmosis"\` or \`graphify path "Mitochondria" "Root hair cell" --undirected\` (run from this folder, uses \`graphify-out/graph.json\`, no internet needed).
- Help them write their own notes for topics marked \`not written yet\`, using \`Templates/Topic note.md\`.
`);

/* Obsidian settings */
const rgb = hex => parseInt(hex.slice(1), 16);
const obs = (f, obj) => { const p = path.join(VAULT, ".obsidian", f); fs.mkdirSync(path.dirname(p), {recursive:true}); fs.writeFileSync(p, JSON.stringify(obj, null, 2)); };
obs("graph.json", {
  "collapse-filter": false, "search": "-path:Templates -path:graphify-out -file:CLAUDE", "showTags": false, "showAttachments": false, "hideUnresolved": true, "showOrphans": true,
  "collapse-color-groups": false,
  "colorGroups": [
    {"query": "path:\"Key terms\"", "color": {"a": 1, "rgb": rgb("#FFC700")}},
    {"query": "path:Notes", "color": {"a": 1, "rgb": rgb("#3452F0")}},
    {"query": "path:Topics", "color": {"a": 1, "rgb": rgb("#0ACF83")}},
    {"query": "path:Flashcards OR path:Practice OR path:Memorise", "color": {"a": 1, "rgb": rgb("#8FD3FF")}},
    {"query": "path:Subjects", "color": {"a": 1, "rgb": rgb("#F24E1E")}},
    {"query": "path:\"My study\" OR path:\"My flashcards\"", "color": {"a": 1, "rgb": rgb("#FF9EC4")}}
  ],
  "collapse-display": false, "showArrow": false, "textFadeMultiplier": 0, "nodeSizeMultiplier": 1.2, "lineSizeMultiplier": 1,
  "collapse-forces": false, "centerStrength": 0.5, "repelStrength": 12, "linkStrength": 1, "linkDistance": 220, "scale": 1, "close": false
});
obs("templates.json", {"folder": "Templates"});
obs("app.json", {"alwaysUpdateLinks": true, "newFileLocation": "folder", "newFileFolderPath": "My study", "attachmentFolderPath": "Attachments"});

/* ---------- check links and write the Graphify extraction ---------- */
const missing = [];
for(const [t, n] of NOTES) if(t !== "CLAUDE") for(const l of n.links) if(!NOTES.has(l)) missing.push(`${t} -> ${l}`);
if(missing.length){ console.error("Unresolved links:\n" + missing.join("\n")); process.exitCode = 1; }

const nid = rel => rel.replace(/\.md$/,"").split("/").map(seg=>seg.toLowerCase().replace(/[^a-z0-9]+/g,"_").replace(/^_|_$/g,"")).join("_");
const skip = new Set(["CLAUDE", "Home", "About my flashcards", "Revision timetable", ...SITE_SUBJECTS.map(indexTitle)]); // navigation pages stay out of the knowledge graph
const nodes = [], edges = [], seen = new Set();
for(const [title, n] of NOTES){
  if(skip.has(title)) continue;
  nodes.push({id:nid(n.rel), label:title, file_type: n.type==="key term" ? "concept" : "document", source_file:path.join(VAULT, n.rel), source_location:null, source_url:null, captured_at:null, author:"Specpoint team", contributor:null, note_type:n.type});
}
const conceptRel = new Set(ALL_CONCEPTS.flatMap(c=>c.related.map(r=>[c.name, r].sort().join("|"))));
for(const [title, n] of NOTES){
  if(skip.has(title)) continue;
  for(const l of n.links){
    const m = NOTES.get(l); if(!m || skip.has(l) || l===title) continue;
    const key = [title, l].sort().join("|"); if(seen.has(key)) continue; seen.add(key);
    edges.push({source:nid(n.rel), target:nid(m.rel), relation: conceptRel.has(key) ? "conceptually_related_to" : "references", confidence:"EXTRACTED", confidence_score:1.0, source_file:path.join(VAULT, n.rel), source_location:null, weight:1.0});
  }
}
const hyperedges = [...GROUPS, ...GP_GROUPS].map(g=>({id:g.id, label:g.label, nodes:g.members.map(m=>nid(NOTES.get(m).rel)), relation:"form", confidence:"EXTRACTED", confidence_score:1.0, source_file:path.join(VAULT, NOTES.get(g.members[0]).rel)}));
fs.mkdirSync(path.join(VAULT, "graphify-out"), {recursive:true});
fs.writeFileSync(path.join(VAULT, "graphify-out", ".graphify_extract.json"), JSON.stringify({nodes, edges, hyperedges, input_tokens:0, output_tokens:0}, null, 2));

console.log(`Vault: ${VAULT}\nNotes: ${NOTES.size} · links: ${[...NOTES.values()].reduce((t,n)=>t+n.links.size,0)} · unresolved: ${missing.length}\nGraphify extraction: ${nodes.length} nodes, ${edges.length} edges, ${hyperedges.length} groups`);
