# Muse

A local visual board in the spirit of Milanote. Infinite canvas, drag things onto
it, arrange them until the idea makes sense. No account, no cloud, no network
except when you paste a link and it fetches the preview.

Use the **Muse** shortcut on your desktop, or `app\Muse.bat` on Windows, or
`app/muse.sh` on Linux, or run it directly:

```bash
python run.py
```

`--browser` opens a browser tab instead of the desktop window, `--serve` runs the
server alone. Default port 8810, bound to 127.0.0.1 only.

## Projects

Work is split into projects, and each one is its own folder under
`Projects`, named the way you named it. A project holds its own boards,
its own images, its own search. Copy `Projects\Studio rebrand` onto a
stick and you have handed over that whole project and nothing else.

The button at the top of the sidebar shows the project you are in; click it for
the project screen. From there you can open, create, rename, show the folder in
Explorer, or delete (right-click a project card for those). Muse reopens the
project and board you were last on.

## Templates

The **+** beside "Boards" in the sidebar opens the template gallery, as does
"Start from a template" on an empty board and creating a new project. 26 of
them, filtered by category:

- **Game design:** design document (a hub board with mechanics, world,
  characters, levels, moodboard and story behind it), brainstorm, moodboard,
  mechanics, world building, character profiles, character relationships,
  story outline, level design, flow chart, storyboard, launch plan
- **Graphic design:** design brief, project plan, moodboard, concept
  presentation, storyboard, handover pack
- **Branding:** brand strategy, brand assets, logo design
- **Web and UX:** customer persona, sitemap, user flow
- **Motion:** style frames

Templates that expect pictures come with dashed placeholder frames. Drop an
image onto one and it fills that frame instead of making a new card.

Adding your own is a function in `muse/templates.py` plus a line in the
`TEMPLATES` list, using the same short builder the others use.

## Using it

**Adding things** - drag a tool from the left rail onto the canvas, or just drop
things in: images, PDFs, any file. Paste a URL and it becomes a link card with
title and thumbnail; paste text and it becomes a note.

**Cards** - note, to-do list, heading, image, link, file, column, board.
Click selects, click again (or double-click) edits, drag the corner resizes.
Images keep their aspect ratio unless you hold Shift.

**Code** - the Code tool (or double-click the card) holds a block of code with
syntax highlighting in any of ~600 languages (auto-detected, or pick one). A
Copy button lifts the whole block to your clipboard.

**Colours** - selecting a card shows 17 colours plus a custom colour wheel for
anything else. In dark mode the pastels are deepened so they still read.

**Dark or light** - the moon/sun button, top right. Dark is the default.

**Board icons** - click the little icon on a board card to give that board a
custom emoji; it shows on the card and in the sidebar. Board cards are the
"category" boxes: double-click one to open the whole board inside it.

**Formatting** - editing a note brings up a toolbar: bold, italic, underline,
strikethrough, bullet and numbered lists, links. Ctrl+B/I/U work as you expect,
Ctrl+K makes a link. Links open when you click them from outside edit mode. The
toolbar flips below a card when there is no room above, so it never covers what
you are typing.

**Quick add** - double-click any empty spot on the canvas to drop a note there.

**Lining things up** - dragging a card snaps to the edges and centres of the
cards around it, with a pink guide showing what it lined up with. Hold Alt while
dragging to place it freely.

**Moving cards to another board** - drag the selection onto any board in the
sidebar and let go. Or Ctrl+C and Ctrl+V, which works across boards and carries
the images with it (Ctrl+Shift+V if the clipboard is being awkward).

**Columns** - drag cards into a column to stack them; drag them out to free them.
The column grows and shrinks to fit.

**Arrows** - hover a card and drag from one of the four dots to another card.
The line follows both cards wherever they go. Click a line to select it, Delete
to remove it.

**Boards inside boards** - drop a Board card and double-click it to go in. The
card shows a live miniature of what is on that board. Breadcrumbs across the
top, the full tree down the left, right-click a tree row to rename, delete, or
set which board that project opens on.

**Deleting a board is not final.** It goes to the project's trash, and a Trash
button appears at the bottom of the sidebar to put it back, contents and images
intact. Deleted projects move to `Trash` rather than disappearing.

**Search** - top left, across every board. Click a hit to jump straight to it.

## Present and export

**Present** (the play button, or F5) hides everything but the board. Arrow keys
step from card to card in reading order with a smooth glide, Home fits the whole
board, Esc exits. Double-clicking a board card walks into it without leaving
present mode, so a hub board works as a slide deck with depth.

**Export** (the arrow button beside it) writes the board as **one HTML file** in
`Exports` and shows it in Explorer. Images, snips and even the current
state of live-file cards are baked in as data - no server, no account, no
internet needed at the other end. Email it to a client; it opens with a
double-click and looks like the board.

## Quick capture

With Muse running, press **Ctrl+Alt+T** from any app (Muse tries Win+Shift+T
first, but on most machines Windows already owns that; the tray icon's menu
shows the combo that actually armed). Windows' own region snip appears - drag
over anything on screen and it pins itself to whichever board you have open,
already sized and saved. If Muse's window is minimised the capture waits and
pins the moment you come back.

There is a Muse icon in the system tray while it runs: open Muse, capture a
region, or quit, from anywhere. To change the hotkey, add
`"capture_hotkey": "ctrl+shift+q"` (any ctrl/alt/shift/win + letter) to
`settings.json` and restart.

## Live files - the part Milanote cannot do

Two tools at the bottom of the rail link to *real files on this machine*
instead of copies:

**Live file** - pick a file (or paste its path onto the board). The card shows
the file as it is *now*: save over it in Photoshop or re-render it from Blender
and the card updates within a few seconds. Double-click opens it in its real
app. If the file goes missing the card says so instead of lying to you.

**Watch** - pick a folder. The card shows what is newest in it, images first,
refreshed automatically. Right-click it for the good part: **"Add new files to
this board"** - from then on, anything that lands in that folder gets its own
live card next to the watch card by itself. Point one at your render output
folder and walk away.

Right-click either card to open it, show it in Explorer, repoint it, or copy
the path. Pasting a path like `D:\renders\shot_010.png` onto the board makes a
live card directly; pasting a folder path makes a watch card.

Nothing is uploaded or copied - these cards are pointers, so they cost nothing
no matter how big the files are. The one trade-off: they show the file on
*this* machine, so they go stale if you copy the project folder to another PC.

### Keys

| | |
|---|---|
| Space + drag, middle-drag, two-finger scroll | pan |
| Ctrl + wheel, Ctrl +/- | zoom |
| Ctrl+0 | back to 100% |
| Enter | edit the selected card |
| Escape | stop editing / deselect |
| Delete | remove selection |
| Ctrl+D | duplicate |
| Ctrl+C / Ctrl+X / Ctrl+V | copy, cut, paste (works across boards) |
| Ctrl+A | select all |
| Ctrl+B / I / U, Ctrl+K | bold, italic, underline, link |
| Alt while dragging | ignore snapping |
| Ctrl+Z / Ctrl+Shift+Z | undo / redo |
| Ctrl+F | search |
| Arrows (Shift for bigger steps) | nudge |

## Where your work lives

```
Muse\
  app\                          the program
  settings.json                 the project and board to reopen
  Projects\
    Studio rebrand\             one folder per project
      project.json
      boards\
        b_7f3a91\
          board.json            the whole board, readable JSON
          board.bak.json        the save before this one
          assets\               images and files you dropped in
```

Copy the Muse folder and you have copied everything, program included. Point OneDrive
or a backup job at `Projects` and your work is covered. Nothing outside
that folder is touched.

### Nothing gets lost when you close it

Four things have to fail at once for you to lose work:

- saves fire half a second after you stop changing anything, and again every
  15 seconds if anything is still unsaved
- closing the window, switching away from it, or switching project all force a
  save first
- the desktop window holds itself open for a moment on close so the last save
  lands
- every save is written to a temp file and swapped in, so a crash mid-write
  cannot corrupt a board, and the previous version stays as `board.bak.json`

The sidebar foot says `Saved` when your work is on disk.

## Not in this version

Realtime sharing, mobile layout, and version history beyond undo. See
[DESIGN.md](DESIGN.md) for the shape of the code and what each decision was for.

## Licence

[PolyForm Noncommercial License 1.0.0](../LICENSE). Use it, change it, share
it, for any noncommercial purpose: personal work, hobby projects, study,
charities, schools, public research and government all count. Selling it, or
using it commercially, is not granted here and needs a separate agreement.

This is source-available rather than open source in the OSI sense, because
that definition requires permitting commercial use. The practical effect for
anyone not selling software is the same.

The separate `packaging/EULA.txt` applies only to the prebuilt installers
distributed from martinworks.org.
