# 🕷️💶 Flappy Money Bot (macOS)

A bot that **plays the flappy-style money game for you**. It flies the green
spider through the leopard pillars, **grabs the money stacks**, picks up the
**blue YOLO shield** and **dodges the red flags**, fully automatically.

It watches your screen and clicks for you. No game hacking, no browser
extension: it plays like a (very fast) human.

<p align="center">
  <a href="https://github.com/Greejv/flappy-bird-bot/releases/latest/download/FlappyBot-mac.zip"><b>⬇️ Download FlappyBot-mac.zip (latest release)</b></a>
</p>

<p align="center"><b>📖 New here? Follow the <a href="docs/TUTORIAL.md">illustrated step-by-step tutorial</a></b> (download → permissions → play, with pictures).</p>

---

## Quick start

1. **Download** [`FlappyBot-mac.zip`](https://github.com/Greejv/flappy-bird-bot/releases/latest/download/FlappyBot-mac.zip) and double-click it to unzip.
2. **Open the game** in your browser so it's fully visible (maximise the window).
3. **Double-click `Start Bot.command`** in the `FlappyBot` folder.
   - *"cannot be opened because it is from an unidentified developer"*?
     **Right-click → Open → Open**. On macOS 15+ you may need
     **System Settings → Privacy & Security → Open Anyway**.
   - The first start sets itself up (≈1 min, needs internet). If macOS offers
     to install the *Command Line Developer Tools* (that's Python), click
     **Install**, then double-click `Start Bot.command` again.
4. **Allow two permissions for _Terminal_** (one time only). The bot opens the right page for you:
   - **Screen Recording**, so the bot can *see* the game
   - **Accessibility**, so the bot can *click*

   Then quit Terminal (⌘Q) and double-click `Start Bot.command` again.
5. **Show the bot where the game is:** put the mouse on the **top-left corner**
   of the game, wait for the countdown, then on the **bottom-right corner**.
   It remembers this for next time.
6. **Move the mouse into the game.** The bot starts playing. 🎉

| You do | Bot does |
|---|---|
| Mouse **inside** the game | plays |
| Mouse **outside** the game | pauses |
| `Ctrl + C` in the Terminal window | quits |

> Don't move or resize the browser window while the bot runs. If you did,
> answer `n` to *"Use saved game area?"* on the next start.

### Prefer the Terminal?

```bash
cd ~/Downloads/FlappyBot
xattr -dr com.apple.quarantine .     # skip the "unidentified developer" warning
./"Start Bot.command"
```

Options (append to the command above):

| Option | What it does |
|---|---|
| `--reselect` | pick the game area again |
| `--test` | take one screenshot, save what the bot sees to `debug/check.png`, exit |
| `--debug` | keep saving annotated frames to `debug/` while playing |
| `--flag-weight 20` | avoid flags even harder (default 10) |
| `--money-weight 2` | chase money harder (default 1) |
| `--shield-weight 3` | chase the blue YOLO shield harder (default 2) |

---

## How it works

```
screen capture ─► vision ─► physics learner ─► planner ─► mouse click
   (mss)         (numpy)    (least squares)    (MPC)       (Quartz)
```

1. **Vision** (`flappybot/vision.py`). In this game the pillars and money
   **cycle through rainbow colours** and the background is a photo (it even
   has the *same red as the flags*). So instead of fixed colours, the bot
   learns the static background and looks at what **moves**:
   - **pillars**: tall moving columns attached to the top/bottom edge (+ their **gap**)
   - **money**: wide moving blob with a white paper band (any colour)
   - **red flags**: squarish, pure red (even over the red background: it spots the moving pole)
   - **blue YOLO cube**: squarish, blue. It's a **shield** that absorbs one hit, so the bot collects it
   - the **spider** itself is found by its neon green
2. **Physics learner** (`flappybot/brain.py`). The bot doesn't need to know
   the game's settings. It watches how the spider moves after each click and
   fits **gravity**, **jump strength**, **input lag** and **scroll speed**
   within the first few seconds (the status line shows `(learning)` until then).
3. **Planner**. Every frame it simulates **~6,000 possible flight plans**
   over the next 1.7 s (everything visible on screen), each of the form
   "hold this height, then that one, then that one", using the learned
   physics and only flapping when a real click is possible. It throws out
   plans that hit a pillar, the floor or the ceiling, rewards plans that fly
   through money and the shield, penalises plans that touch or even get
   close to flags, and clicks if the best plan says *flap now*. Last frame's
   best plan is carried over, so the bot commits to a route instead of
   dithering. It re-plans 30–60× per second.

### Status line

```
PLAYING   fps=  48 taps=  312  bird=YES pillars=3 money=1 flags=1  g=2.31 jump=-0.71 lag=42ms speed=0.42
```

If `bird=no` while you're playing, run with `--test` and look at
`debug/check.png` (blue = spider, magenta = pillars, green = money,
red = flags, yellow = shield).

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Capture is black / only wallpaper | Screen Recording isn't on for Terminal. Enable it, **quit Terminal**, start again. |
| Bot sees the game but never clicks | Accessibility isn't on for Terminal. Enable it, quit Terminal, start again. |
| `bird=no` | Wrong game area. Start with `--reselect`. Make sure the whole game is visible and not covered. |
| Clicks land in the wrong place | The window moved. Use `--reselect`. |
| Slow (fps < 20) | Make the browser window smaller. The bot works at any size. |
| Plays but dies sometimes | Let it learn for ~5 s first. Make sure the browser isn't lagging (close other heavy tabs). |

---

## For developers

```bash
pip install numpy scipy pillow pytest
pytest -q -s tests            # vision + full games vs. a headless game simulator
python -m tests.run_sim --seconds 120 --seed 1
```

`tests/simulator.py` is a headless replica of the game (sprites cut from a
real screenshot, a busy red/purple background, different physics than the
bot's starting guesses), so the whole pipeline (vision → learning →
planning) is tested without a Mac.

### Releases

The [Build & Release workflow](.github/workflows/build.yml) runs on every push:

1. simulator tests on Linux,
2. a real install + import smoke test on **macOS (Apple Silicon)** with the
   system Python, exactly like `Start Bot.command`,
3. builds `FlappyBot-mac.zip` (uploaded as a workflow artifact).

To publish a new download, push a version tag:

```bash
git tag v1.0.1
git push origin v1.0.1
```

The workflow attaches `FlappyBot-mac.zip` to a new GitHub Release, and the
download link at the top of this README always points to the latest one.
You can also build the zip locally with `./scripts/build_zip.sh`.

### Project layout

```
Start Bot.command      double-click launcher (sets up Python env on first run)
flappybot/vision.py    screenshot -> bird / pillars / money / flags
flappybot/brain.py     physics learner + planner + Bot
flappybot/macos.py     screen capture, clicks, permissions
flappybot/main.py      CLI: setup, game-area selection, main loop
tests/                 simulator + pytest
scripts/build_zip.sh   builds dist/FlappyBot-mac.zip
```
