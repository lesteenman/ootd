# The Chronicles of the Bardians of Thylea

A wiki and voyage map of our *Odyssey of the Dragonlords* campaign, built from the players' notes:
https://lesteenman.github.io/ootd/

The notes live in a private Obsidian vault. This repo holds only what is published from it
(`data/`) and the code that turns that into a website (`site/`).

```
data/wiki.json     every published note, written by the vault's .wiki/extract.py
data/media/        the images those notes embed, and the map
site/build.py      renders data/ into a static site
site/assets/       CSS, search, and the voyage map (map.js)
legacy/            the original hand-made map page, kept for reference
```

## Publishing

Nothing deploys automatically from the vault. The easy way: in the vault repo, run the
**Publish OotD wiki to preview** workflow (Actions tab → Run workflow). It does steps 1 and 2
below and opens the pull request of step 3. It needs the vault secret `OOTD_TOKEN` (see
"One-time setup").

By hand, from a computer with both repos checked out:

1. **Extract** in the vault, into a checkout of this repo on the `preview` branch:

   ```bash
   git -C ~/ootd checkout preview && git -C ~/ootd merge main
   ```

   ```bash
   cd ~/"obsidian-vault/Personal/DnD/Oddysey of the Dragonlords"
   python3 .wiki/extract.py ~/ootd/data
   ```

   The extractor runs the validator first and stops on errors. Notes marked
   `publish: false` and the `player` field never leave the vault.

2. **Preview**: commit and push `preview`. The *Build check* workflow renders it; when it
   passes, *Deploy site* puts it at https://lesteenman.github.io/ootd/preview/ (with a
   "Preview" banner). The preview is public too, just not linked from anywhere.

3. **Publish**: open a pull request from `preview` to `main`. Its diff is exactly what changes
   on the public site. Merging it deploys `/`.

To create the `preview` branch the first time: `git checkout -b preview origin/main && git push -u origin preview`.

## Building locally

```bash
pip install -r site/requirements.txt
```

```bash
python3 site/build.py data _site && python3 -m http.server -d _site
```

## The data format

`data/wiki.json` is versioned (`"format": 1`); `build.py` refuses formats it doesn't know.
Each note has `id`, `title`, `type` (`character`, `location`, `item`, `lore`, `quest`, `oath`,
`arc`, `day`, `session` or `index`), `section`, `aliases`, `fields` (the frontmatter, with links
as `{"id", "label"}`), `body` (Markdown, with links written as `wiki:<id>`, or `wiki:` for a
note that doesn't exist yet) and `links` (outgoing note ids). The fields per type are described
in the vault's campaign `CLAUDE.md`, under "Wiki data".

## One-time setup

1. **Pages source.** In this repo: Settings → Pages → Build and deployment → Source:
   **GitHub Actions**.
2. **Token for the publish button.** Create a fine-grained personal access token
   (GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens):
   - Repository access: *Only select repositories* → `lesteenman/ootd`
   - Permissions: **Contents: Read and write**, **Pull requests: Read and write**
   - An expiry you're happy to renew (the workflow fails with a clear error once it expires)
3. **Store it in the vault.** In `lesteenman/obsidian-vault`: Settings → Secrets and variables →
   Actions → New repository secret, named `OOTD_TOKEN`.
