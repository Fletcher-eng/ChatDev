# Specpoint Obsidian vault

`Specpoint Vault/` is an Obsidian vault built from the Specpoint website's content. Everything is plain Markdown on your own computer, so it works offline.

## Open it

1. Download this folder (or the zip) to your computer.
2. In Obsidian choose **Open folder as vault** and pick `Specpoint Vault`.
3. Open `Home`. Press **Ctrl+G** (Cmd+G on a Mac) for the graph.
4. Optional plugins: **Spaced Repetition** (flashcards), **Dataview**. Turn on the **Templates** core plugin.

## What is inside

| Folder | What it holds |
| --- | --- |
| `Subjects/` | One hub per subject with Cambridge and Edexcel codes |
| `Biology/Topics/` | All 21 Biology 0610 topics, written or not yet |
| `Biology/Notes/` | Full notes per subtopic |
| `Biology/Key terms/` | One note per key idea, linked across topics and subjects |
| `Biology/Flashcards/` | `question::answer` cards for the Spaced Repetition plugin |
| `Biology/Practice/` | Exam style questions with folded mark schemes |
| `My study/`, `My flashcards/` | Your own pages: mistake book, past papers, timetable, exam dates |
| `graphify-out/` | Graphify knowledge graph: `graph.html` (works offline), `graph.json`, `GRAPH_REPORT.md` |
| `Knowledge graph.canvas` | The same graph as an Obsidian Canvas |

On the Specpoint website, **Export to Obsidian** saves your own flashcard decks and mistake book as notes you can drop into `My flashcards/` and `My study/`.

## Rebuild after the website changes

```
node specpoint/obsidian/build-vault.mjs
pip install graphifyy
python specpoint/obsidian/build-graph.py
```

Rebuilding keeps everything you write under a `## My notes` heading, and never overwrites the pages in `My study/` or `My flashcards/`.

Key terms, their links and the subjects they connect to live in `concepts.mjs`. Add a term there and rebuild to grow the graph.

## Ask Claude about it

Open a Claude Code session inside `Specpoint Vault`. `CLAUDE.md` tells Claude how the vault works, so you can say things like "quiz me on topic 3" or "mark my answer to question 2". Graph questions run locally with Graphify, for example `graphify explain "Osmosis"` or `graphify path "Mitochondria" "Root hair cell" --undirected`.
