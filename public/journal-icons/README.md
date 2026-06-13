# Journal icons

Drop a logo here named after the journal **key**, and both the web app and the iOS
app will show it instead of the monogram tile. If no file is present, the monogram
tile is used — so this folder is entirely optional.

- **Filename:** `<key>.png` (PNG, roughly square, transparent or white background)
- **Served at:** `…/journal-icons/<key>.png` — the iOS app loads the same files from
  your deployed site, so you only add logos in this one place.

| Key | Journal |
|-----|---------|
| `ajsm` | American Journal of Sports Medicine |
| `bjj` | The Bone & Joint Journal |
| `corr` | Clinical Orthopaedics & Related Research |
| `jbjs` | JBJS (American) |
| `arthro` | The Journal of Arthroplasty |
| `jot_trauma` | Journal of Orthopaedics & Traumatology |
| `jorthotr` | Journal of Orthopaedic Trauma |
| `aots` | Archives of Orthopaedic & Trauma Surgery |
| `injury` | Injury |
| `ejtes` | European Journal of Trauma & Emergency Surgery |
| `arthrotoday` | Arthroplasty Today |

(For journals you add later, the key is shown in `config/journals.json`.)

> **Rights:** journal logos are trademarked/copyrighted by their publishers. Only add
> artwork you have permission to use (your own, licensed, or publisher-approved). The
> app ships with monogram tiles precisely so no third-party logos are bundled by default.
