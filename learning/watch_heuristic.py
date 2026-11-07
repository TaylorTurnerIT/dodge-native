#!/usr/bin/env python3
"""Watch a hand-written heuristic (dodge.heuristics) play Dodge.

Run from the learning/ directory. Press O to show or hide the bot's own overlay
(its predictions, its plan, any map it keeps), if it draws one; Esc closes the
window. With --headless no window opens (and pygame is not needed) and the bot
plays as fast as it can decide, printing how long each game lasted."""

import argparse
import secrets

from dodge.engine import DIFFICULTIES, Engine
from dodge.heuristics import BOTS


def window_title(label, seed, episode, frames, overlay):
    shown = "overlay on" if overlay else "O for overlay"
    return f"{label} | Episode {episode} | Seed {seed} | Frame {frames:,} | {shown}"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bot", nargs="?", default="space", choices=sorted(BOTS))
    parser.add_argument("--seed", type=int, default=None,
                        help="first game's seed (random if omitted)")
    parser.add_argument("--next-seed", choices=("random", "increment"), default="random",
                        help="seed for later games: random, or one more than the last")
    parser.add_argument("--scale", type=int, default=5)
    parser.add_argument("--difficulty", choices=sorted(DIFFICULTIES), default="hard")
    parser.add_argument("--patterns", action="store_true")
    parser.add_argument("--powerups", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--normal-enemies", action=argparse.BooleanOptionalAction,
                        default=True)
    parser.add_argument("--kamikaze-enemies", action=argparse.BooleanOptionalAction,
                        default=True)
    parser.add_argument("--spawn-rate-percent", type=int, default=100)
    parser.add_argument("--fps", type=int, default=60)
    parser.add_argument("--overlay", action=argparse.BooleanOptionalAction, default=False,
                        help="start with the bot's overlay shown (O toggles it)")
    parser.add_argument("--games", type=int, default=None,
                        help="stop after this many games (default: never)")
    parser.add_argument("--max-frames", type=int, default=None,
                        help="stop after this many frames in all")
    parser.add_argument("--headless", action="store_true",
                        help="no window: play as fast as the bot can decide")
    args = parser.parse_args(argv)

    label, make_bot = BOTS[args.bot]
    seed = args.seed if args.seed is not None else secrets.randbelow(2**31 - 1)
    engine = Engine(
        seed=seed, difficulty=DIFFICULTIES[args.difficulty], patterns=args.patterns,
        powerups=args.powerups, normal_enemies=args.normal_enemies,
        kamikaze_enemies=args.kamikaze_enemies, spawn_rate_percent=args.spawn_rate_percent)

    window = clock = pygame = None
    if not args.headless:
        import pygame
        from dodge.display import GameWindow
        window = GameWindow(scale=args.scale)
        clock = pygame.time.Clock()

    bot = make_bot()
    episode, frames, total_frames = 1, 0, 0
    show_overlay = args.overlay
    if window:
        window.set_caption(window_title(label, seed, episode, frames, show_overlay))
    running = True
    while running:
        if window:
            for event in pygame.event.get():
                if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN
                                                 and event.key == pygame.K_ESCAPE):
                    running = False
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_o:
                    show_overlay = not show_overlay
                    window.set_caption(window_title(label, seed, episode, frames, show_overlay))
            if not running:
                break

        state = engine.lane_state(0)
        bot.observe(state)
        action = bot.act(state)
        if window:
            # Drawn over the frame the decision was made from, so predictions
            # start where things are now.
            overlay = bot.overlay() if show_overlay and hasattr(bot, "overlay") else None
            window.set_field(None if overlay is None else overlay.field)
            window.show(engine.frame(), overlay)
            clock.tick(args.fps)
        done = engine.step(action)
        frames += 1
        total_frames += 1
        if args.max_frames is not None and total_frames >= args.max_frames:
            print(f"{label}: stopped at {args.max_frames:,} frames")
            break
        if window and frames % 30 == 0:
            window.set_caption(window_title(label, seed, episode, frames, show_overlay))
        if done:
            print(f"{label}: seed {seed} lasted {frames:,} frames", flush=True)
            if args.games is not None and episode >= args.games:
                break
            episode += 1
            frames = 0
            seed = seed + 1 if args.next_seed == "increment" else secrets.randbelow(2**31 - 1)
            engine.reset(seed)
            bot = make_bot()
            if window:
                window.set_caption(window_title(label, seed, episode, frames, show_overlay))
    if pygame:
        pygame.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
